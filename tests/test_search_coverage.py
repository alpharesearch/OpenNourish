"""Branch-by-branch coverage for ``opennourish/search/routes.py``.

The older suite (``tests/test_search.py``) exercises the happy paths.  These
tests walk the remaining seams of ``search()``, ``add_item()`` and
``get_portions()``, with particular attention to the guards that came with the
recent security fixes:

* ``_portion_matches_item`` — a portion may only be attached to its own item,
* the recipe self-nesting check runs before the portion guards,
* friend diary copy requires an *accepted* ``Friendship``,
* every ownership rejection covers both the "living other user" and the
  "deleted owner" flash.
"""

from datetime import date
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from flask import url_for
from sqlalchemy import text

from models import (
    db,
    DailyLog,
    Food,
    FoodCategory,
    FoodNutrient,
    Friendship,
    MyFood,
    MyMeal,
    MyMealItem,
    Nutrient,
    Recipe,
    RecipeIngredient,
    UnifiedPortion,
    User,
)
from opennourish.search.routes import (
    ManualPagination,
    _as_optional_int,
    _portion_matches_item,
)

LOG_DATE = date(2025, 5, 6)
LOG_DATE_STR = LOG_DATE.isoformat()
OTHER_LOG_DATE_STR = date(2025, 5, 5).isoformat()

# The pinned nutrient ids ``add_item`` reads when copying a USDA food to My Foods.
NUTRIENT_IDS = [
    1003,
    1004,
    1005,
    1008,
    1079,
    1087,
    1089,
    1092,
    1093,
    1110,
    1235,
    1253,
    1257,
    1258,
    2000,
]

USDA_UPC = "123456789012"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _flashes(client):
    """Flash messages currently queued in the session."""
    with client.session_transaction() as sess:
        return [message for _category, message in sess.get("_flashes", [])]


def _path(response_or_url):
    """Path component of a redirect target (SERVER_NAME makes url_for absolute)."""
    location = getattr(response_or_url, "location", response_or_url)
    return urlsplit(location).path


def _url(app, endpoint, **values):
    with app.app_context():
        return url_for(endpoint, **values)


def _add_item(client, **data):
    """POST /search/add_item with a referrer so referrer redirects are testable."""
    data.setdefault("amount", 1)
    return client.post(
        "/search/add_item", data=data, headers={"Referer": "http://localhost/search/"}
    )


@pytest.fixture
def env(auth_client):
    """A user with one of every item type, plus a friend, a stranger and a ghost."""
    app = auth_client.application
    with app.app_context():
        me = User.query.filter_by(username="testuser").one()

        other = User(username="search_other", email="search_other@example.com")
        other.set_password("pw")
        friend = User(username="search_friend", email="search_friend@example.com")
        friend.set_password("pw")
        ghost = User(username="search_ghost", email="search_ghost@example.com")
        ghost.set_password("pw")
        db.session.add_all([other, friend, ghost])
        db.session.flush()
        db.session.add_all(
            [
                Friendship(
                    requester_id=me.id, receiver_id=friend.id, status="accepted"
                ),
                # A pending request is *not* read access.
                Friendship(requester_id=me.id, receiver_id=other.id, status="pending"),
            ]
        )

        category = FoodCategory(user_id=me.id, description="Search Category")
        global_category = FoodCategory(description="Global Category")
        db.session.add_all([category, global_category])
        db.session.flush()

        db.session.add_all(
            [
                Nutrient(id=nid, name=f"nutrient-{nid}", unit_name="g")
                for nid in NUTRIENT_IDS
            ]
        )
        apple = Food(
            fdc_id=700001,
            description="Search Apple Sauce",
            upc=USDA_UPC,
            ingredients="apples",
        )
        banana = Food(fdc_id=700002, description="Search Banana Split")
        db.session.add_all([apple, banana])
        db.session.add_all(
            [
                FoodNutrient(fdc_id=700001, nutrient_id=1008, amount=100.0),
                FoodNutrient(fdc_id=700001, nutrient_id=1003, amount=1.0),
                FoodNutrient(fdc_id=700001, nutrient_id=1005, amount=20.0),
                FoodNutrient(fdc_id=700001, nutrient_id=1004, amount=0.5),
            ]
        )

        my_food = MyFood(
            user_id=me.id,
            description="Search Own Food",
            calories_per_100g=200,
            food_category_id=category.id,
        )
        own_recipe = Recipe(
            user_id=me.id, name="Search Own Recipe", instructions="mix", servings=2
        )
        sub_recipe = Recipe(user_id=me.id, name="Search Sub Recipe", instructions="mix")
        target_recipe = Recipe(
            user_id=me.id, name="Search Target Recipe", instructions="mix"
        )
        other_recipe = Recipe(
            user_id=other.id, name="Search Foreign Recipe", instructions="mix"
        )
        public_recipe = Recipe(
            user_id=other.id,
            name="Search Public Recipe",
            instructions="mix",
            is_public=True,
        )
        friend_food = MyFood(
            user_id=friend.id, description="Search Friend Food", calories_per_100g=10
        )
        friend_recipe = Recipe(
            user_id=friend.id, name="Search Friend Recipe", instructions="mix"
        )
        other_food = MyFood(
            user_id=other.id, description="Search Foreign Food", calories_per_100g=10
        )
        meal = MyMeal(user_id=me.id, name="Search Own Meal", usage_count=0)
        target_meal = MyMeal(user_id=me.id, name="Search Target Meal")
        other_meal = MyMeal(user_id=other.id, name="Search Foreign Meal")
        db.session.add_all(
            [
                my_food,
                own_recipe,
                sub_recipe,
                target_recipe,
                other_recipe,
                public_recipe,
                friend_food,
                friend_recipe,
                other_food,
                meal,
                target_meal,
                other_meal,
            ]
        )
        db.session.flush()

        db.session.add_all(
            [
                MyMealItem(my_meal_id=meal.id, fdc_id=700001, amount_grams=50),
                MyMealItem(my_meal_id=meal.id, my_food_id=my_food.id, amount_grams=30),
            ]
        )

        food_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=100.0,
            seq_num=1,
        )
        recipe_portion = UnifiedPortion(
            recipe_id=own_recipe.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=150.0,
            seq_num=1,
        )
        sub_portion = UnifiedPortion(
            recipe_id=sub_recipe.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=80.0,
            seq_num=1,
        )
        other_food_portion = UnifiedPortion(
            my_food_id=other_food.id, gram_weight=60.0, portion_description="wedge"
        )
        other_recipe_portion = UnifiedPortion(
            recipe_id=other_recipe.id, gram_weight=70.0, portion_description="wedge"
        )
        friend_food_portion = UnifiedPortion(
            my_food_id=friend_food.id, gram_weight=25.0, portion_description="bit"
        )
        db.session.add_all(
            [
                food_portion,
                recipe_portion,
                sub_portion,
                other_food_portion,
                other_recipe_portion,
                friend_food_portion,
            ]
        )

        # Rows whose owner will be removed from the database.
        ghost_food = MyFood(
            user_id=ghost.id, description="Search Ghost Food", calories_per_100g=10
        )
        ghost_recipe = Recipe(
            user_id=ghost.id, name="Search Ghost Recipe", instructions="mix"
        )
        ghost_meal = MyMeal(user_id=ghost.id, name="Search Ghost Meal")
        db.session.add_all([ghost_food, ghost_recipe, ghost_meal])
        db.session.flush()
        db.session.add_all(
            [
                UnifiedPortion(my_food_id=ghost_food.id, gram_weight=11.0),
                UnifiedPortion(recipe_id=ghost_recipe.id, gram_weight=12.0),
            ]
        )
        db.session.commit()

        db.session.delete(ghost)
        db.session.commit()

        db.session.refresh(me)

        namespace = SimpleNamespace(
            app=app,
            client=auth_client,
            me=me.id,
            other=other.id,
            friend=friend.id,
            category=category.id,
            global_category=global_category.id,
            apple=700001,
            banana=700002,
            my_food=my_food.id,
            my_food_portion=food_portion.id,
            own_recipe=own_recipe.id,
            own_recipe_portion=recipe_portion.id,
            sub_recipe=sub_recipe.id,
            sub_recipe_portion=sub_portion.id,
            target_recipe=target_recipe.id,
            other_recipe=other_recipe.id,
            other_recipe_portion=other_recipe_portion.id,
            public_recipe=public_recipe.id,
            other_food=other_food.id,
            other_food_portion=other_food_portion.id,
            friend_food=friend_food.id,
            friend_food_portion=friend_food_portion.id,
            friend_recipe=friend_recipe.id,
            meal=meal.id,
            target_meal=target_meal.id,
            other_meal=other_meal.id,
            ghost_food=ghost_food.id,
            ghost_food_portion=UnifiedPortion.query.filter_by(my_food_id=ghost_food.id)
            .first()
            .id,
            ghost_recipe=ghost_recipe.id,
            ghost_recipe_portion=UnifiedPortion.query.filter_by(
                recipe_id=ghost_recipe.id
            )
            .first()
            .id,
            ghost_meal=ghost_meal.id,
        )
    return namespace


# --------------------------------------------------------------------------- #
# module helpers
# --------------------------------------------------------------------------- #
def test_as_optional_int_handles_junk():
    assert _as_optional_int("12") == 12
    assert _as_optional_int(7) == 7
    assert _as_optional_int(None) is None
    assert _as_optional_int("not-a-number") is None


def test_portion_matches_item_requires_same_parent():
    usda = SimpleNamespace(id=1, fdc_id=5, my_food_id=None, recipe_id=None)
    my_food = SimpleNamespace(id=2, fdc_id=None, my_food_id=5, recipe_id=None)
    recipe = SimpleNamespace(id=3, fdc_id=None, my_food_id=None, recipe_id=5)

    assert _portion_matches_item(usda, "usda", "5")
    assert _portion_matches_item(my_food, "my_food", 5)
    assert _portion_matches_item(recipe, "recipe", "5")

    assert not _portion_matches_item(usda, "my_food", "5")
    assert not _portion_matches_item(my_food, "recipe", "5")
    assert not _portion_matches_item(recipe, "usda", "5")
    # A portion of a different row never matches, even for the right type.
    assert not _portion_matches_item(SimpleNamespace(id=4, fdc_id=6), "usda", "5")


def test_portion_matches_item_is_permissive_for_unknown_shapes():
    # A virtual (unsaved) portion has no id yet and is trusted by the caller.
    virtual = SimpleNamespace(id=None, fdc_id=99, my_food_id=99, recipe_id=99)
    assert _portion_matches_item(virtual, "usda", "5")
    assert _portion_matches_item(None, "my_food", "5")
    # Food types outside the three item sources are not portion-parented.
    assert _portion_matches_item(SimpleNamespace(id=1, fdc_id=None), "diary_meal", "5")


def test_manual_pagination_degenerate_and_gap_cases():
    empty = ManualPagination(page=1, per_page=0, total=0, items=[])
    assert empty.pages == 0
    assert not empty.has_next
    assert not empty.has_prev
    assert empty.next_num is None
    assert empty.prev_num is None
    assert list(empty.iter_pages()) == []

    wide = ManualPagination(page=6, per_page=1, total=12, items=[])
    assert wide.next_num == 7
    assert wide.prev_num == 5
    pages = list(wide.iter_pages())
    assert None in pages  # ellipsis gap rendered by the template
    assert pages[0] == 1 and pages[-1] == 12


# --------------------------------------------------------------------------- #
# search() — GET
# --------------------------------------------------------------------------- #
def test_search_wildcard_lists_all_sources(env):
    response = env.client.get("/search/?search_term=*&per_page=50")
    assert response.status_code == 200
    assert b"Search Apple Sauce" in response.data
    assert b"Search Own Food" in response.data
    assert b"Search Own Recipe" in response.data
    assert b"Search Own Meal" in response.data


def test_search_friend_and_public_scopes(env):
    response = env.client.get(
        "/search/?search_term=Search&search_friends=true&search_public=true"
        "&search_my_foods=true&search_recipes=true&per_page=50"
    )
    assert response.status_code == 200
    assert b"Search Friend Food" in response.data
    assert b"Search Friend Recipe" in response.data
    assert b"Search Public Recipe" in response.data


def test_search_without_friend_scope_hides_friend_content(env):
    response = env.client.get(
        "/search/?search_term=Search&search_my_foods=true&search_recipes=true"
        "&search_public=false&per_page=50"
    )
    assert response.status_code == 200
    assert b"Search Friend Food" not in response.data
    assert b"Search Friend Recipe" not in response.data


def test_search_usda_by_upc(env):
    response = env.client.get(f"/search/?search_term={USDA_UPC}&search_usda=true")
    assert response.status_code == 200
    assert b"Search Apple Sauce" in response.data


def test_search_usda_category_filter(env):
    with env.app.app_context():
        db.session.add(Food(fdc_id=700003, description="Search Categorized"))
        db.session.flush()
        food = db.session.get(Food, 700003)
        food.food_category_id = env.global_category
        db.session.commit()

    response = env.client.get(
        f"/search/?search_term=Search&search_usda=true&food_category_id={env.global_category}"
    )
    assert response.status_code == 200
    assert b"Search Categorized" in response.data
    assert b"Search Apple Sauce" not in response.data


def test_search_usda_relevance_and_length_ordering(env):
    with env.app.app_context():
        db.session.add_all(
            [
                Food(fdc_id=700010, description="Researched Notes"),  # relevance 4
                Food(fdc_id=700011, description="Research"),  # relevance 3
            ]
        )
        db.session.commit()

    response = env.client.get("/search/?search_term=research&search_usda=true")
    assert response.status_code == 200
    body = response.data.decode()
    assert "<strong>Research</strong>" in body
    assert "<strong>Researched Notes</strong>" in body
    assert body.index("<strong>Research</strong>") < body.index(
        "<strong>Researched Notes</strong>"
    )


def test_search_usda_page_beyond_results(env):
    response = env.client.get(
        "/search/?search_term=Search&search_usda=true&per_page=1&usda_page=9"
    )
    assert response.status_code == 200
    assert b"Search Apple Sauce" not in response.data


def test_search_usda_truncates_oversized_result_set(env):
    """More than 5000 matches are cut off before the portion-count lookup."""
    with env.app.app_context():
        db.session.bulk_insert_mappings(
            Food,
            [
                {"fdc_id": 800000 + i, "description": f"Bulk Search Item {i}"}
                for i in range(5001)
            ],
        )
        db.session.commit()

    response = env.client.get(
        "/search/?search_term=Bulk+Search+Item&search_usda=true&per_page=2"
    )
    assert response.status_code == 200
    assert b"Bulk Search Item" in response.data


def test_search_user_sources_honour_category_filter(env):
    with env.app.app_context():
        db.session.add_all(
            [
                MyFood(
                    user_id=env.me,
                    description="Search Uncategorized Food",
                    calories_per_100g=1,
                ),
                Recipe(
                    user_id=env.me,
                    name="Search Uncategorized Recipe",
                    instructions="x",
                    upc=USDA_UPC,
                ),
            ]
        )
        db.session.commit()

    response = env.client.get(
        "/search/?search_term=Search&search_my_foods=true&search_recipes=true"
        f"&food_category_id={env.category}"
    )
    assert response.status_code == 200
    assert b"Search Own Food" in response.data
    assert b"Search Uncategorized Food" not in response.data
    assert b"Search Own Recipe" not in response.data


def test_search_recipe_by_upc(env):
    with env.app.app_context():
        db.session.add(
            Recipe(
                user_id=env.me,
                name="Search Barcoded Recipe",
                instructions="x",
                upc=USDA_UPC,
            )
        )
        db.session.commit()

    response = env.client.get(
        f"/search/?search_term={USDA_UPC}&search_recipes=true&search_my_foods=false"
        "&search_usda=false&search_my_meals=false"
    )
    assert response.status_code == 200
    assert b"Search Barcoded Recipe" in response.data


def test_search_popular_public_recipes_without_term(env):
    with env.app.app_context():
        db.session.add_all(
            [
                DailyLog(
                    user_id=env.me,
                    log_date=LOG_DATE,
                    recipe_id=env.public_recipe,
                    amount_grams=10,
                ),
                DailyLog(
                    user_id=env.me,
                    log_date=LOG_DATE,
                    recipe_id=env.public_recipe,
                    amount_grams=10,
                ),
            ]
        )
        db.session.commit()

    response = env.client.get("/search/?search_recipes=true&search_public=true")
    assert response.status_code == 200
    assert b"Search Public Recipe" in response.data


def test_search_frequent_usda_items_get_gram_portions(env):
    with env.app.app_context():
        db.session.add(
            DailyLog(
                user_id=env.me, log_date=LOG_DATE, fdc_id=env.apple, amount_grams=40
            )
        )
        db.session.commit()

    response = env.client.get("/search/?search_usda=true&search_my_foods=false")
    assert response.status_code == 200
    assert b"Search Apple Sauce" in response.data

    with env.app.app_context():
        gram = UnifiedPortion.query.filter_by(fdc_id=env.apple, gram_weight=1.0).all()
        assert len(gram) == 1
        assert gram[0].was_imported is True


def test_search_frequent_usda_page_without_logs(env):
    response = env.client.get("/search/?search_usda=true&search_my_foods=false")
    assert response.status_code == 200
    assert b"Search Apple Sauce" not in response.data


def test_search_my_meals_by_name_and_usage(env):
    with env.app.app_context():
        db.session.add(
            MyMeal(user_id=env.me, name="Search Frequent Meal", usage_count=3)
        )
        db.session.commit()

    named = env.client.get("/search/?search_term=Meal&search_my_meals=true")
    assert named.status_code == 200
    assert b"Search Frequent Meal" in named.data
    assert b"Search Target Meal" in named.data

    frequent = env.client.get("/search/?search_my_meals=true")
    assert frequent.status_code == 200
    assert b"Search Frequent Meal" in frequent.data


def test_search_rematch_context_loads_ingredient(env):
    with env.app.app_context():
        placeholder = MyFood(
            user_id=env.me, description="Search Placeholder Flour", is_placeholder=True
        )
        db.session.add(placeholder)
        db.session.flush()
        portion = UnifiedPortion(
            my_food_id=placeholder.id,
            amount=2,
            measure_unit_description="cup",
            gram_weight=1.0,
        )
        db.session.add(portion)
        db.session.flush()
        ingredient = RecipeIngredient(
            recipe_id=env.own_recipe,
            my_food_id=placeholder.id,
            portion_id_fk=portion.id,
            amount_grams=2.0,
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

    response = env.client.get(
        f"/search/?target=rematch_ingredient&ingredient_id_to_replace={ingredient_id}"
        f"&recipe_id={env.own_recipe}&search_term=Flour"
    )
    assert response.status_code == 200
    assert b"Rematching Ingredient" in response.data
    assert b"Search Placeholder Flour" in response.data


def test_search_rematch_context_with_unknown_ingredient(env):
    response = env.client.get(
        "/search/?target=rematch_ingredient&ingredient_id_to_replace=424242"
    )
    assert response.status_code == 200
    assert b"Rematching Ingredient" not in response.data


def test_search_return_urls_for_every_target(env):
    diary = env.client.get(f"/search/?target=diary&log_date={LOG_DATE_STR}")
    assert (
        _url(env.app, "diary.diary", log_date_str=LOG_DATE_STR) in diary.data.decode()
    )

    recipe = env.client.get(f"/search/?target=recipe&recipe_id={env.target_recipe}")
    assert (
        _url(env.app, "recipes.edit_recipe", recipe_id=env.target_recipe)
        in recipe.data.decode()
    )

    meal = env.client.get(f"/search/?target=meal&recipe_id={env.target_meal}")
    assert (
        _url(env.app, "diary.edit_meal", meal_id=env.target_meal) in meal.data.decode()
    )


# --------------------------------------------------------------------------- #
# add_item() — portion plumbing and guards
# --------------------------------------------------------------------------- #
def test_add_item_rejects_non_numeric_portion_id(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id="not-a-number",
    )
    assert response.status_code == 302
    assert _path(response) == "/search/"
    assert "Invalid portion ID." in _flashes(env.client)


def test_add_item_virtual_portion_sentinel_is_not_resolved(env):
    """``portion_id == -1`` cannot be loaded, so the request is refused."""
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=-1,
    )
    assert response.status_code == 302
    assert "Invalid portion selected." in _flashes(env.client)
    with env.app.app_context():
        assert DailyLog.query.filter_by(my_food_id=env.my_food).count() == 0


def test_add_my_food_without_portion_id_is_rejected(env):
    """The MyFood default-portion fallback is undone, so nothing is logged."""
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
    )
    assert response.status_code == 302
    assert "Invalid portion selected." in _flashes(env.client)


def test_add_recipe_without_portion_id_requires_portion(env):
    response = _add_item(
        env.client,
        food_id=env.own_recipe,
        food_type="recipe",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
    )
    assert response.status_code == 302
    assert "A valid portion is required." in _flashes(env.client)
    assert _path(response) == "/search/"


def test_add_usda_food_without_portion_creates_gram_portion(env):
    response = _add_item(
        env.client,
        food_id=env.banana,
        food_type="usda",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Snack",
        amount=3,
    )
    assert response.status_code == 302
    assert "Search Banana Split added to your diary." in _flashes(env.client)

    with env.app.app_context():
        log = DailyLog.query.filter_by(fdc_id=env.banana).one()
        assert log.amount_grams == pytest.approx(3.0)
        assert log.serving_type == " g"
        portion = UnifiedPortion.query.filter_by(fdc_id=env.banana).one()
        assert portion.gram_weight == 1.0
        assert portion.was_imported is True


def test_add_usda_food_when_default_portion_cannot_be_found(env):
    """A trigger sabotages the 1 g insert, so the fallback lookup comes up empty."""
    with env.app.app_context():
        db.session.execute(
            text(
                "CREATE TRIGGER break_gram_portion AFTER INSERT ON portions "
                "BEGIN UPDATE portions SET gram_weight = 5.0 WHERE id = NEW.id; END"
            )
        )
        db.session.commit()

    response = _add_item(
        env.client,
        food_id=env.banana,
        food_type="usda",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Snack",
    )
    assert response.status_code == 302
    assert _path(response) == "/search/"
    assert (
        "Could not find or create a default 1-gram portion for USDA food."
        in _flashes(env.client)
    )


def test_portion_of_another_recipe_is_rejected(env):
    """The portion-ownership guard: a sub-recipe's portion cannot fund the parent."""
    response = _add_item(
        env.client,
        food_id=env.own_recipe,
        food_type="recipe",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
        portion_id=env.sub_recipe_portion,
    )
    assert response.status_code == 302
    assert "The selected portion does not belong to this item." in _flashes(env.client)
    with env.app.app_context():
        assert DailyLog.query.filter_by(recipe_id=env.own_recipe).count() == 0


def test_portion_of_another_my_food_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=env.friend_food_portion,
    )
    assert response.status_code == 302
    assert "The selected portion does not belong to this item." in _flashes(env.client)


def test_portion_of_another_usda_food_is_rejected(env):
    with env.app.app_context():
        portion = UnifiedPortion(fdc_id=env.apple, gram_weight=9.0)
        db.session.add(portion)
        db.session.commit()
        apple_portion_id = portion.id

    response = _add_item(
        env.client,
        food_id=env.banana,
        food_type="usda",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Snack",
        portion_id=apple_portion_id,
    )
    assert response.status_code == 302
    assert "The selected portion does not belong to this item." in _flashes(env.client)


# --------------------------------------------------------------------------- #
# add_item() — target: diary
# --------------------------------------------------------------------------- #
def test_add_my_food_to_diary(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=env.my_food_portion,
        amount=2,
    )
    assert response.status_code == 302
    assert "Search Own Food added to your diary." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.diary", log_date_str=LOG_DATE_STR)

    with env.app.app_context():
        log = DailyLog.query.filter_by(my_food_id=env.my_food).one()
        assert log.amount_grams == pytest.approx(200.0)
        assert log.serving_type == " serving"
        assert log.portion_id_fk == env.my_food_portion
        assert log.meal_name == "Breakfast"


def test_add_my_food_to_diary_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=env.my_food_portion,
        return_url="/search/",
    )
    assert _path(response) == "/search/"


def test_add_diary_without_log_date_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="diary",
        meal_name="Breakfast",
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Log date is required for diary entries." in _flashes(env.client)
    assert "target=diary" in response.location


def test_add_other_users_my_food_to_diary_is_rejected(env):
    """A living user's private food cannot be logged, even with their portion id."""
    response = _add_item(
        env.client,
        food_id=env.other_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=env.other_food_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.diary", log_date_str=LOG_DATE_STR)
    with env.app.app_context():
        assert DailyLog.query.filter_by(my_food_id=env.other_food).count() == 0


def test_add_deleted_users_my_food_to_diary_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_food,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=env.ghost_food_portion,
    )
    assert response.status_code == 302
    flashes = _flashes(env.client)
    assert "This food belongs to a deleted user and cannot be added." in flashes
    assert "You can only add your own foods, recipes and meals." not in flashes


def test_add_missing_my_food_to_diary(env):
    with env.app.app_context():
        # An orphan portion that still claims the missing parent id clears the
        # ownership guard, so the request reaches the lookup itself.
        stray = UnifiedPortion(my_food_id=987654, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=987654,
        food_type="my_food",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "My Food not found." in _flashes(env.client)


def test_add_missing_usda_food_to_diary(env):
    response = _add_item(
        env.client,
        food_id=999999,
        food_type="usda",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Snack",
    )
    assert response.status_code == 302
    assert "USDA Food not found." in _flashes(env.client)


def test_add_other_users_recipe_to_diary_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_recipe,
        food_type="recipe",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
        portion_id=env.other_recipe_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.diary", log_date_str=LOG_DATE_STR)
    with env.app.app_context():
        assert DailyLog.query.filter_by(recipe_id=env.other_recipe).count() == 0


def test_add_deleted_users_recipe_to_diary_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_recipe,
        food_type="recipe",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
        portion_id=env.ghost_recipe_portion,
    )
    assert response.status_code == 302
    assert "This recipe belongs to a deleted user and cannot be added." in _flashes(
        env.client
    )


def test_add_missing_recipe_to_diary(env):
    with env.app.app_context():
        stray = UnifiedPortion(recipe_id=424242, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=424242,
        food_type="recipe",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "Recipe not found." in _flashes(env.client)


def test_add_unknown_food_type_to_diary(env):
    with env.app.app_context():
        stray = UnifiedPortion(gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=1,
        food_type="mystery",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Dinner",
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "Invalid food type for diary." in _flashes(env.client)


# --------------------------------------------------------------------------- #
# add_item() — target: recipe
# --------------------------------------------------------------------------- #
def test_add_to_recipe_requires_recipe_id(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="recipe",
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Recipe ID is required to add to a recipe." in _flashes(env.client)


def test_add_to_missing_recipe_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="recipe",
        recipe_id=424242,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Recipe not found or not authorized." in _flashes(env.client)


def test_add_to_other_users_recipe_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="recipe",
        recipe_id=env.other_recipe,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Recipe not found or not authorized." in _flashes(env.client)
    with env.app.app_context():
        assert RecipeIngredient.query.filter_by(recipe_id=env.other_recipe).count() == 0


def test_add_usda_ingredient_to_recipe(env):
    response = _add_item(
        env.client,
        food_id=env.apple,
        food_type="usda",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id="",  # falls back to the generated 1 g portion
        amount=250,
    )
    assert response.status_code == 302
    assert "Search Apple Sauce added to recipe Search Target Recipe." in _flashes(
        env.client
    )
    with env.app.app_context():
        ingredient = RecipeIngredient.query.filter_by(recipe_id=env.target_recipe).one()
        assert ingredient.fdc_id == env.apple
        assert ingredient.amount_grams == pytest.approx(250.0)
        assert ingredient.seq_num == 1
        assert db.session.get(Recipe, env.target_recipe).calories_per_100g > 0


def test_add_missing_usda_ingredient_to_recipe(env):
    response = _add_item(
        env.client,
        food_id=999999,
        food_type="usda",
        target="recipe",
        recipe_id=env.target_recipe,
    )
    assert response.status_code == 302
    assert "USDA Food not found." in _flashes(env.client)


def test_add_to_recipe_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.my_food_portion,
        return_url="/search/",
    )
    assert _path(response) == "/search/"


def test_add_other_users_my_food_to_recipe_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_food,
        food_type="my_food",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.other_food_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.target_recipe
    )


def test_add_deleted_users_my_food_to_recipe_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_food,
        food_type="my_food",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.ghost_food_portion,
    )
    assert response.status_code == 302
    assert (
        "This food belongs to a deleted user and cannot be added as an ingredient."
        in _flashes(env.client)
    )


def test_add_missing_my_food_ingredient_to_recipe(env):
    with env.app.app_context():
        stray = UnifiedPortion(my_food_id=987654, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=987654,
        food_type="my_food",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "My Food not found." in _flashes(env.client)


def test_add_subrecipe_to_recipe(env):
    response = _add_item(
        env.client,
        food_id=env.sub_recipe,
        food_type="recipe",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.sub_recipe_portion,
        amount=2,
    )
    assert response.status_code == 302
    assert "Search Sub Recipe added as ingredient to recipe Search Target Recipe." in (
        _flashes(env.client)
    )
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.target_recipe
    )
    with env.app.app_context():
        ingredient = RecipeIngredient.query.filter_by(recipe_id=env.target_recipe).one()
        assert ingredient.recipe_id_link == env.sub_recipe
        assert ingredient.amount_grams == pytest.approx(160.0)


def test_self_nesting_is_reported_before_portion_checks(env):
    """Even a mismatched portion must not mask the self-nesting contract."""
    response = _add_item(
        env.client,
        food_id=env.own_recipe,
        food_type="recipe",
        target="recipe",
        recipe_id=env.own_recipe,
        portion_id=env.sub_recipe_portion,
    )
    assert response.status_code == 302
    assert "A recipe cannot be an ingredient of itself." in _flashes(env.client)
    assert "target=recipe" in response.location


def test_self_nesting_check_tolerates_unparseable_ids(env):
    """A non-numeric food id skips the numeric guard and lands on lookup instead."""
    response = _add_item(
        env.client,
        food_id="not-a-number",
        food_type="recipe",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Sub-recipe not found." in _flashes(env.client)


def test_add_other_users_subrecipe_to_recipe_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_recipe,
        food_type="recipe",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.other_recipe_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.target_recipe
    )


def test_add_deleted_users_subrecipe_to_recipe_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_recipe,
        food_type="recipe",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.ghost_recipe_portion,
    )
    assert response.status_code == 302
    assert (
        "This recipe belongs to a deleted user and cannot be added as an ingredient."
        in _flashes(env.client)
    )


def test_add_missing_subrecipe_to_recipe(env):
    with env.app.app_context():
        stray = UnifiedPortion(recipe_id=424242, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=424242,
        food_type="recipe",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "Sub-recipe not found." in _flashes(env.client)
    assert "target=recipe" in response.location


def test_add_unknown_food_type_to_recipe(env):
    response = _add_item(
        env.client,
        food_id=1,
        food_type="mystery",
        target="recipe",
        recipe_id=env.target_recipe,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Invalid food type for recipe." in _flashes(env.client)


# --------------------------------------------------------------------------- #
# add_item() — target: rematch_ingredient
# --------------------------------------------------------------------------- #
def _placeholder_ingredient(env, name="Search Placeholder Flour", shared=False):
    with env.app.app_context():
        placeholder = MyFood(user_id=env.me, description=name, is_placeholder=True)
        db.session.add(placeholder)
        db.session.flush()
        portion = UnifiedPortion(
            my_food_id=placeholder.id,
            amount=2,
            measure_unit_description="cup",
            gram_weight=1.0,
        )
        db.session.add(portion)
        db.session.flush()
        ingredient = RecipeIngredient(
            recipe_id=env.own_recipe,
            my_food_id=placeholder.id,
            portion_id_fk=portion.id,
            amount_grams=2.0,
        )
        db.session.add(ingredient)
        if shared:
            db.session.add(
                RecipeIngredient(
                    recipe_id=env.target_recipe,
                    my_food_id=placeholder.id,
                    amount_grams=5.0,
                )
            )
        db.session.commit()
        return SimpleNamespace(
            ingredient=ingredient.id,
            placeholder=placeholder.id,
            portion=portion.id,
        )


def test_rematch_unknown_ingredient_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=424242,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert (
        "Original ingredient not found or you are not authorized to edit it."
        in _flashes(env.client)
    )
    assert _path(response) == _url(env.app, "recipes.recipes")


def test_rematch_ingredient_of_other_user_is_rejected(env):
    with env.app.app_context():
        foreign = RecipeIngredient(
            recipe_id=env.other_recipe, fdc_id=env.apple, amount_grams=10
        )
        portion = UnifiedPortion(my_food_id=env.my_food, gram_weight=10.0, seq_num=9)
        db.session.add_all([foreign, portion])
        db.session.commit()
        foreign_id = foreign.id
        portion_id = portion.id

    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=foreign_id,
        portion_id=portion_id,
    )
    assert response.status_code == 302
    assert (
        "Original ingredient not found or you are not authorized to edit it."
        in _flashes(env.client)
    )


def test_rematch_to_another_placeholder_is_rejected(env):
    setup = _placeholder_ingredient(env)
    with env.app.app_context():
        other_placeholder = MyFood(
            user_id=env.me, description="Search Second Placeholder", is_placeholder=True
        )
        db.session.add(other_placeholder)
        db.session.flush()
        portion = UnifiedPortion(my_food_id=other_placeholder.id, gram_weight=4.0)
        db.session.add(portion)
        db.session.commit()
        placeholder_id = other_placeholder.id
        portion_id = portion.id

    response = _add_item(
        env.client,
        food_id=placeholder_id,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        portion_id=portion_id,
    )
    assert response.status_code == 302
    assert "Cannot match an ingredient to another placeholder." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.own_recipe
    )


def test_rematch_of_non_placeholder_is_rejected(env):
    """Only the single live rematch branch validates the placeholder.

    ``add_item`` used to carry a second, unreachable ``elif target ==
    "rematch_ingredient"`` duplicate without these guards; this assertion is the
    regression pin that keeps the validated semantics in charge.
    """
    with env.app.app_context():
        ingredient = RecipeIngredient(
            recipe_id=env.own_recipe, my_food_id=env.my_food, amount_grams=10
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=ingredient_id,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Original ingredient is not a placeholder." in _flashes(env.client)


def test_rematch_requires_a_resolvable_portion(env):
    setup = _placeholder_ingredient(env)
    response = _add_item(
        env.client,
        food_id=env.banana,
        food_type="usda",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        # No portion_id: the USDA branch synthesises one for the guard, but the
        # rematch branch needs an explicit portion of the new food.
    )
    assert response.status_code == 302
    assert "A valid portion is required for rematching." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.own_recipe
    )


def test_rematch_placeholder_to_my_food(env):
    setup = _placeholder_ingredient(env)
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        portion_id=env.my_food_portion,
        amount=1,
    )
    assert response.status_code == 302
    assert "Ingredient matched successfully." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "recipes.edit_recipe", recipe_id=env.own_recipe
    )
    with env.app.app_context():
        ingredient = db.session.get(RecipeIngredient, setup.ingredient)
        assert ingredient.my_food_id == env.my_food
        assert ingredient.portion_id_fk == env.my_food_portion
        # original quantity (2 cups) * new gram weight (100 g)
        assert ingredient.amount_grams == pytest.approx(200.0)
        assert db.session.get(MyFood, setup.placeholder) is None
        assert db.session.get(UnifiedPortion, setup.portion) is None


def test_rematch_placeholder_to_usda_food(env):
    setup = _placeholder_ingredient(env)
    with env.app.app_context():
        gram = UnifiedPortion(fdc_id=env.apple, gram_weight=1.0)
        db.session.add(gram)
        db.session.commit()
        gram_id = gram.id

    response = _add_item(
        env.client,
        food_id=env.apple,
        food_type="usda",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        portion_id=gram_id,
        amount=1,
    )
    assert response.status_code == 302
    assert "Ingredient matched successfully." in _flashes(env.client)
    with env.app.app_context():
        ingredient = db.session.get(RecipeIngredient, setup.ingredient)
        assert ingredient.fdc_id == env.apple
        assert ingredient.amount_grams == pytest.approx(2.0)


def test_rematch_placeholder_to_subrecipe(env):
    setup = _placeholder_ingredient(env)
    response = _add_item(
        env.client,
        food_id=env.sub_recipe,
        food_type="recipe",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        portion_id=env.sub_recipe_portion,
    )
    assert response.status_code == 302
    assert "Ingredient matched successfully." in _flashes(env.client)
    with env.app.app_context():
        ingredient = db.session.get(RecipeIngredient, setup.ingredient)
        assert ingredient.recipe_id_link == env.sub_recipe


def test_rematch_keeps_placeholder_used_elsewhere(env):
    setup = _placeholder_ingredient(env, shared=True)
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="rematch_ingredient",
        ingredient_id_to_replace=setup.ingredient,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Ingredient matched successfully." in _flashes(env.client)
    with env.app.app_context():
        assert db.session.get(MyFood, setup.placeholder) is not None


# --------------------------------------------------------------------------- #
# add_item() — target: meal
# --------------------------------------------------------------------------- #
def test_add_to_meal_requires_meal_id(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="meal",
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Meal ID is required to add to a meal." in _flashes(env.client)


def test_add_to_missing_meal_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="meal",
        recipe_id=424242,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "My Meal not found or not authorized." in _flashes(env.client)


def test_add_to_other_users_meal_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="meal",
        recipe_id=env.other_meal,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "My Meal not found or not authorized." in _flashes(env.client)


def test_add_my_food_to_meal_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.my_food_portion,
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    with env.app.app_context():
        item = MyMealItem.query.filter_by(my_meal_id=env.target_meal).one()
        assert item.my_food_id == env.my_food
        assert item.amount_grams == pytest.approx(100.0)


def test_add_missing_usda_food_to_meal(env):
    response = _add_item(
        env.client,
        food_id=999999,
        food_type="usda",
        target="meal",
        recipe_id=env.target_meal,
    )
    assert response.status_code == 302
    assert "USDA Food not found." in _flashes(env.client)


def test_add_other_users_my_food_to_meal_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_food,
        food_type="my_food",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.other_food_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.edit_meal", meal_id=env.target_meal)


def test_add_deleted_users_my_food_to_meal_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_food,
        food_type="my_food",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.ghost_food_portion,
    )
    assert response.status_code == 302
    assert (
        "This food belongs to a deleted user and cannot be added to a meal."
        in _flashes(env.client)
    )


def test_add_missing_my_food_to_meal(env):
    with env.app.app_context():
        stray = UnifiedPortion(my_food_id=987654, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=987654,
        food_type="my_food",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "My Food not found." in _flashes(env.client)


def test_add_recipe_to_meal(env):
    response = _add_item(
        env.client,
        food_id=env.own_recipe,
        food_type="recipe",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.own_recipe_portion,
        amount=2,
    )
    assert response.status_code == 302
    assert "Search Own Recipe added to meal Search Target Meal." in _flashes(env.client)


def test_add_other_users_recipe_to_meal_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_recipe,
        food_type="recipe",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.other_recipe_portion,
    )
    assert response.status_code == 302
    assert "You can only add your own foods, recipes and meals." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.edit_meal", meal_id=env.target_meal)


def test_add_deleted_users_recipe_to_meal_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_recipe,
        food_type="recipe",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.ghost_recipe_portion,
    )
    assert response.status_code == 302
    assert (
        "This recipe belongs to a deleted user and cannot be added to a meal."
        in _flashes(env.client)
    )


def test_add_missing_recipe_to_meal(env):
    with env.app.app_context():
        stray = UnifiedPortion(recipe_id=424242, gram_weight=10.0)
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id

    response = _add_item(
        env.client,
        food_id=424242,
        food_type="recipe",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=stray_id,
    )
    assert response.status_code == 302
    assert "Recipe not found." in _flashes(env.client)


def test_my_meal_into_meal_is_intercepted_before_the_meal_branch(env):
    """``food_type=my_meal`` is fully handled by the special case at the top.

    The ``elif food_type == "my_meal"`` arm inside ``target == "meal"`` is
    therefore unreachable (and would raise, since ``MyMealItem`` has no
    ``my_meal_id_link`` column); saving a meal inside another meal is not
    supported and reports the generic target rejection instead.
    """
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="meal",
        recipe_id=env.target_meal,
    )
    assert response.status_code == 302
    assert "Cannot add a meal to the selected target: meal." in _flashes(env.client)
    with env.app.app_context():
        assert MyMealItem.query.filter_by(my_meal_id=env.target_meal).count() == 0


def test_add_unknown_food_type_to_meal(env):
    response = _add_item(
        env.client,
        food_id=1,
        food_type="mystery",
        target="meal",
        recipe_id=env.target_meal,
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Invalid food type for meal." in _flashes(env.client)


# --------------------------------------------------------------------------- #
# add_item() — food_type: my_meal (expanded)
# --------------------------------------------------------------------------- #
def test_add_missing_my_meal(env):
    response = _add_item(
        env.client,
        food_id=424242,
        food_type="my_meal",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Lunch",
    )
    assert response.status_code == 302
    assert "My Meal not found." in _flashes(env.client)
    # The referrer wins over the diary fallback.
    assert _path(response) == "/search/"


def test_add_other_users_my_meal_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.other_meal,
        food_type="my_meal",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Lunch",
    )
    assert response.status_code == 302
    assert "You are not authorized to add this meal." in _flashes(env.client)
    with env.app.app_context():
        assert DailyLog.query.count() == 0


def test_add_deleted_users_my_meal_is_info(env):
    response = _add_item(
        env.client,
        food_id=env.ghost_meal,
        food_type="my_meal",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Lunch",
    )
    assert response.status_code == 302
    assert "This meal belongs to a deleted user and cannot be added." in _flashes(
        env.client
    )


def test_add_my_meal_to_diary_honours_return_url_and_counts_usage(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="diary",
        log_date=LOG_DATE_STR,
        meal_name="Lunch",
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    assert '"Search Own Meal" (expanded) added to your diary.' in _flashes(env.client)
    with env.app.app_context():
        assert db.session.get(MyMeal, env.meal).usage_count == 1
        assert DailyLog.query.filter_by(meal_name="Lunch").count() == 2


def test_add_my_meal_to_diary_without_log_date_uses_user_today(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="diary",
        meal_name="Lunch",
    )
    assert response.status_code == 302
    with env.app.app_context():
        assert DailyLog.query.filter_by(meal_name="Lunch").count() == 2


def test_add_my_meal_to_missing_recipe(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="recipe",
        recipe_id=424242,
    )
    assert response.status_code == 302
    assert "Recipe not found or not authorized." in _flashes(env.client)
    assert _path(response) == _url(env.app, "recipes.recipes")


def test_add_my_meal_to_other_users_recipe(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="recipe",
        recipe_id=env.other_recipe,
    )
    assert response.status_code == 302
    assert "Recipe not found or not authorized." in _flashes(env.client)


def test_add_my_meal_to_recipe_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="recipe",
        recipe_id=env.target_recipe,
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    assert '"Search Own Meal" (expanded) added to recipe Search Target Recipe.' in (
        _flashes(env.client)
    )
    with env.app.app_context():
        ingredients = RecipeIngredient.query.filter_by(
            recipe_id=env.target_recipe
        ).all()
        assert {i.seq_num for i in ingredients} == {1, 2}


def test_add_my_meal_to_unknown_target(env):
    response = _add_item(
        env.client,
        food_id=env.meal,
        food_type="my_meal",
        target="somewhere",
    )
    assert response.status_code == 302
    assert "Cannot add a meal to the selected target: somewhere." in _flashes(
        env.client
    )


# --------------------------------------------------------------------------- #
# add_item() — food_type: diary_meal (copy a meal)
# --------------------------------------------------------------------------- #
def _seed_source_meal(env, user_id=None):
    with env.app.app_context():
        db.session.add_all(
            [
                DailyLog(
                    user_id=user_id or env.me,
                    log_date=LOG_DATE,
                    meal_name="Breakfast",
                    fdc_id=env.apple,
                    amount_grams=100,
                ),
                DailyLog(
                    user_id=user_id or env.me,
                    log_date=LOG_DATE,
                    meal_name="Breakfast",
                    fdc_id=env.banana,
                    amount_grams=200,
                ),
            ]
        )
        db.session.commit()


def test_copy_diary_meal_without_return_url(env):
    _seed_source_meal(env)
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
    )
    assert response.status_code == 302
    assert "Successfully copied items from Breakfast to Dinner." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "diary.diary", log_date_str=OTHER_LOG_DATE_STR
    )
    with env.app.app_context():
        copied = DailyLog.query.filter_by(meal_name="Dinner").all()
        assert len(copied) == 2
        assert {item.amount_grams for item in copied} == {100.0, 200.0}


def test_copy_diary_meal_honours_return_url(env):
    _seed_source_meal(env)
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
        amount=2,
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    with env.app.app_context():
        assert DailyLog.query.filter_by(meal_name="Dinner").count() == 2


def test_copy_diary_meal_from_unknown_friend(env):
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
        friend_username="nobody-here",
    )
    assert response.status_code == 302
    assert "Friend 'nobody-here' not found." in _flashes(env.client)


def test_copy_diary_meal_from_non_friend_is_rejected(env):
    """A pending request is not read access: only accepted friendships count."""
    _seed_source_meal(env, user_id=env.other)
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
        friend_username="search_other",
    )
    assert response.status_code == 302
    assert "You are not friends with search_other." in _flashes(env.client)
    with env.app.app_context():
        assert DailyLog.query.filter_by(user_id=env.me).count() == 0


def test_copy_diary_meal_from_accepted_friend(env):
    """The same request succeeds once the friendship is accepted."""
    with env.app.app_context():
        db.session.add(
            Friendship(requester_id=env.other, receiver_id=env.me, status="accepted")
        )
        db.session.commit()
    _seed_source_meal(env, user_id=env.other)

    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
        friend_username="search_other",
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    assert "Successfully copied items from Breakfast to Dinner." in _flashes(env.client)
    with env.app.app_context():
        copied = DailyLog.query.filter_by(user_id=env.me, meal_name="Dinner").all()
        assert [item.fdc_id for item in copied] == [env.apple, env.banana]


def test_copy_diary_meal_onto_itself_is_rejected(env):
    _seed_source_meal(env)
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
    )
    assert response.status_code == 302
    assert "Source and target meal cannot be the same." in _flashes(env.client)
    assert _path(response) == _url(env.app, "diary.diary", log_date_str=LOG_DATE_STR)


def test_copy_diary_meal_onto_itself_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        return_url="/search/",
    )
    assert _path(response) == "/search/"


def test_copy_diary_meal_from_friend_onto_same_slot_is_allowed(env):
    """Identical meal/date from a friend is a copy, not a self-overwrite."""
    _seed_source_meal(env, user_id=env.friend)
    response = _add_item(
        env.client,
        food_id="Breakfast",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=LOG_DATE_STR,
        meal_name="Breakfast",
        friend_username="search_friend",
    )
    assert response.status_code == 302
    assert "Successfully copied items from Breakfast to Breakfast." in _flashes(
        env.client
    )


def test_copy_empty_diary_meal_warns(env):
    response = _add_item(
        env.client,
        food_id="Supper",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
    )
    assert response.status_code == 302
    assert "No items found in Supper to copy." in _flashes(env.client)
    assert _path(response) == _url(
        env.app, "diary.diary", log_date_str=OTHER_LOG_DATE_STR
    )


def test_copy_empty_diary_meal_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id="Supper",
        food_type="diary_meal",
        target="diary",
        source_log_date=LOG_DATE_STR,
        log_date=OTHER_LOG_DATE_STR,
        meal_name="Dinner",
        return_url="/search/",
    )
    assert _path(response) == "/search/"


# --------------------------------------------------------------------------- #
# add_item() — target: my_foods (copy a USDA food) and unknown targets
# --------------------------------------------------------------------------- #
def test_copy_usda_food_to_my_foods(env):
    response = _add_item(
        env.client,
        food_id=env.apple,
        food_type="usda",
        target="my_foods",
    )
    assert response.status_code == 302
    assert "Search Apple Sauce has been added to your foods." in _flashes(env.client)

    with env.app.app_context():
        copied = MyFood.query.filter_by(fdc_id=env.apple, user_id=env.me).one()
        assert copied.description == "Search Apple Sauce"
        assert copied.ingredients == "apples"
        assert copied.upc == USDA_UPC
        assert copied.calories_per_100g == pytest.approx(100.0)
        assert copied.protein_per_100g == pytest.approx(1.0)
        assert copied.carbs_per_100g == pytest.approx(20.0)
        assert copied.fat_per_100g == pytest.approx(0.5)
        # Nutrients that were never inserted fall back to 0.0.
        assert copied.sodium_mg_per_100g == 0.0
        assert _path(response) == _url(
            env.app, "my_foods.edit_my_food", food_id=copied.id
        )


def test_copy_usda_food_to_my_foods_honours_return_url(env):
    response = _add_item(
        env.client,
        food_id=env.banana,  # no FoodNutrient rows at all
        food_type="usda",
        target="my_foods",
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    with env.app.app_context():
        copied = MyFood.query.filter_by(fdc_id=env.banana).one()
        assert copied.calories_per_100g == 0.0


def test_copy_non_usda_to_my_foods_is_rejected(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="my_foods",
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Only USDA foods can be copied to My Foods via this method." in _flashes(
        env.client
    )


def test_add_item_with_unknown_target(env):
    response = _add_item(
        env.client,
        food_id=env.my_food,
        food_type="my_food",
        target="nowhere",
        portion_id=env.my_food_portion,
    )
    assert response.status_code == 302
    assert "Invalid target for adding item." in _flashes(env.client)
    assert "target=nowhere" in response.location


def test_add_item_defaults_target_to_my_foods(env):
    """An omitted target falls through to the My Foods copy branch."""
    response = _add_item(
        env.client,
        food_id=env.apple,
        food_type="usda",
        target="None",
        return_url="/search/",
    )
    assert _path(response) == "/search/"
    with env.app.app_context():
        assert MyFood.query.filter_by(fdc_id=env.apple).count() == 1


# --------------------------------------------------------------------------- #
# get_portions()
# --------------------------------------------------------------------------- #
def test_get_portions_recipe_lists_portions(env):
    response = env.client.get(f"/search/api/get-portions/recipe/{env.own_recipe}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["calories_per_100g"] == 0.0
    assert payload["portions"][0]["description"] == " serving"
    assert payload["portions"][0]["gram_weight"] == pytest.approx(150.0)
    assert payload["portions"][0]["is_default"] is True


def test_get_portions_public_recipe_of_other_user(env):
    with env.app.app_context():
        db.session.add(UnifiedPortion(recipe_id=env.public_recipe, gram_weight=42.0))
        db.session.commit()

    response = env.client.get(f"/search/api/get-portions/recipe/{env.public_recipe}")
    assert response.status_code == 200
    assert response.get_json()["portions"][0]["gram_weight"] == pytest.approx(42.0)


def test_get_portions_friend_recipe(env):
    with env.app.app_context():
        db.session.add(UnifiedPortion(recipe_id=env.friend_recipe, gram_weight=33.0))
        db.session.commit()

    response = env.client.get(f"/search/api/get-portions/recipe/{env.friend_recipe}")
    assert response.status_code == 200
    assert response.get_json()["portions"][0]["gram_weight"] == pytest.approx(33.0)


def test_get_portions_friend_my_food(env):
    response = env.client.get(f"/search/api/get-portions/my_food/{env.friend_food}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["calories_per_100g"] == 10
    assert payload["portions"][0]["gram_weight"] == pytest.approx(25.0)


def test_get_portions_usda(env):
    response = env.client.get(f"/search/api/get-portions/usda/{env.apple}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["calories_per_100g"] == pytest.approx(100.0)
    assert payload["portions"] == [
        {"id": -1, "description": "g", "gram_weight": 1.0, "is_default": True}
    ]


def test_get_portions_usda_with_portions(env):
    with env.app.app_context():
        db.session.add_all(
            [
                UnifiedPortion(
                    fdc_id=env.apple, gram_weight=240.0, portion_description="cup"
                ),
                UnifiedPortion(
                    fdc_id=env.apple, gram_weight=5.0, portion_description="slice"
                ),
            ]
        )
        db.session.commit()

    response = env.client.get(f"/search/api/get-portions/usda/{env.apple}")
    payload = response.get_json()["portions"]
    assert [p["gram_weight"] for p in payload] == [240.0, 5.0]
    # No "serving" description, so the first portion becomes the default.
    assert payload[0]["is_default"] is True
    assert "is_default" not in payload[1]


def test_get_portions_my_food_prefers_serving_as_default(env):
    with env.app.app_context():
        db.session.add(
            UnifiedPortion(
                my_food_id=env.my_food,
                gram_weight=5.0,
                amount=1,
                measure_unit_description="serving",
                seq_num=0,
            )
        )
        db.session.commit()

    response = env.client.get(f"/search/api/get-portions/my_food/{env.my_food}")
    payload = response.get_json()["portions"]
    assert payload[0]["description"] == " serving"
    assert payload[0]["is_default"] is True
    assert "is_default" not in payload[1]


def test_get_portions_my_meal_of_other_user(env):
    response = env.client.get(f"/search/api/get-portions/my_meal/{env.other_meal}")
    assert response.status_code == 404
    assert b"Not Found or Unauthorized" in response.data


def test_get_portions_my_meal_with_items(env):
    response = env.client.get(f"/search/api/get-portions/my_meal/{env.meal}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["portions"][0]["id"] == -1
    assert payload["portions"][0]["gram_weight"] == pytest.approx(80.0)


def test_get_portions_unknown_food_type(env):
    response = env.client.get("/search/api/get-portions/mystery/1")
    assert response.status_code == 200
    assert response.get_json()["portions"][0]["description"] == "g"


def test_add_item_usda_non_numeric_food_id_does_not_500(env):
    """Regression: int(food_id) for a USDA add used to sit outside the try, so
    a non-numeric id raised an unhandled ValueError (HTTP 500)."""
    response = _add_item(
        env.client,
        food_type="usda",
        food_id="not-a-number",
        target="diary",
        follow_redirects=False,
    )
    assert response.status_code == 302  # flashed + redirected, no 500
    page = env.client.get("/search/").get_data()
    assert b"Invalid food ID." in page
