"""Coverage-focused tests for ``opennourish/recipes/routes.py``.

The feature-oriented recipe tests already exercise the happy paths. This file
targets what they never reach: guard clauses (ownership, portion ownership,
missing portions), the YAML importer's error branches, the label routes,
re-ordering routes and the ingredient/portion display helpers.
"""

import io

import pytest
import yaml
from flask import g, url_for
from models import (
    db,
    Food,
    FoodCategory,
    MyFood,
    MyMeal,
    Recipe,
    RecipeIngredient,
    UnifiedPortion,
    User,
)

SERVER_PREFIX = "http://localhost.localdomain:5000"


def _path(url):
    """Strip the test SERVER_NAME so URLs compare against rendered hrefs."""
    if url.startswith(SERVER_PREFIX):
        return url[len(SERVER_PREFIX) :]
    return url


def _login_as(client, user_id):
    """Point an existing test client's session at a different user id.

    ``conftest.app_with_db`` keeps an application context pushed for the whole
    test, and Flask-Login caches the loaded user on ``flask.g``, so the cache
    has to be dropped or the previous identity keeps answering requests.
    """
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True
    g.pop("_login_user", None)


def _flashes(client):
    """The flash messages still pending in the client's session."""
    with client.session_transaction() as sess:
        return [message for _category, message in sess.get("_flashes", [])]


def _has_flash(client, needle):
    """True when any pending flash message contains ``needle``."""
    return any(needle in message for message in _flashes(client))


def _loc(response):
    """The redirect target as a path, without the fragment."""
    location = _path(response.headers["Location"])
    return location.split("#", 1)[0]


def _loc_fragment(response):
    """The fragment of the redirect target, or an empty string."""
    location = response.headers["Location"]
    return location.split("#", 1)[1] if "#" in location else ""


def _add_recipe(user_id, name="Test Recipe", **kwargs):
    """Create and commit a recipe (must run inside an app context)."""
    recipe = Recipe(user_id=user_id, name=name, **kwargs)
    db.session.add(recipe)
    db.session.commit()
    return recipe


def _import_text(client, text):
    """POST raw YAML at the importer and return the response."""
    return client.post(url_for("recipes.import_recipes"), data={"yaml_text": text})


# ---------------------------------------------------------------------------
# List page view modes
# ---------------------------------------------------------------------------


def test_recipes_friends_view_without_friends_shows_placeholder(auth_client):
    response = auth_client.get(url_for("recipes.recipes", view="friends"))
    assert response.status_code == 200
    assert b"No recipes found from your friends." in response.data


def test_recipes_friends_view_lists_friend_recipes(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship
    with client.application.app_context():
        _add_recipe(friend.id, "Friends Casserole", is_public=False)
        _add_recipe(me.id, "My Own Stew")

    response = client.get(url_for("recipes.recipes", view="friends"))
    assert response.status_code == 200
    assert b"Friends Casserole" in response.data
    assert b"My Own Stew" not in response.data


def test_recipes_public_view_lists_public_recipes_only(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        _add_recipe(user.id, "Private To Me")
        other = _add_recipe(user.id, "Shared To All", is_public=True)
        other_id = other.id

    response = client.get(url_for("recipes.recipes", view="public"))
    assert response.status_code == 200
    assert b"Shared To All" in response.data
    assert b"Private To Me" not in response.data
    assert _path(url_for("recipes.view_recipe", recipe_id=other_id)).encode() in (
        response.data
    )


# ---------------------------------------------------------------------------
# Recipe create / edit / delete
# ---------------------------------------------------------------------------


def test_new_recipe_get_renders_categories(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        db.session.add(FoodCategory(description="Casseroles", user_id=None, code=1))
        db.session.add(FoodCategory(description="Bowls", user_id=user.id, code=2))
        db.session.commit()

    response = client.get(url_for("recipes.new_recipe"))
    assert response.status_code == 200
    assert b"Casseroles" in response.data
    assert b"Bowls" in response.data


def test_new_recipe_invalid_form_rerenders(auth_client):
    response = auth_client.post(
        url_for("recipes.new_recipe"), data={"name": "Missing servings"}
    )
    assert response.status_code == 200
    assert b"Recipe Name" in response.data
    with auth_client.application.app_context():
        assert Recipe.query.count() == 0


def test_new_recipe_with_category_creates_default_gram_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Soups", user_id=user.id, code=3)
        db.session.add(category)
        db.session.commit()
        category_id = category.id

    response = client.post(
        url_for("recipes.new_recipe"),
        data={
            "name": "Chowder",
            "servings": "4",
            "instructions": "Simmer",
            "final_weight_grams": "800",
            "food_category": str(category_id),
            "is_public": "y",
        },
    )
    assert response.status_code == 302
    assert _has_flash(client, "Recipe created successfully.")

    with client.application.app_context():
        recipe = Recipe.query.filter_by(name="Chowder").one()
        assert recipe.food_category_id == category_id
        assert recipe.is_public is True
        assert [(p.amount, p.gram_weight) for p in recipe.portions] == [(1.0, 1.0)]


def test_edit_recipe_rejects_non_owner_before_backfilling_seq_nums(
    auth_client_two_users,
):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Owned By One")
        ingredient = RecipeIngredient(recipe_id=recipe.id, amount_grams=50)
        portion = UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0, amount=1.0)
        db.session.add_all([ingredient, portion])
        db.session.commit()
        recipe_id, ingredient_id, portion_id = recipe.id, ingredient.id, portion.id

    _login_as(client, user_two.id)
    response = client.get(
        url_for("recipes.edit_recipe", recipe_id=recipe_id), follow_redirects=True
    )
    assert response.status_code == 200
    assert b"You are not authorized to edit this recipe." in response.data

    with client.application.app_context():
        # The ownership check must run before any seq_num backfill commits.
        assert db.session.get(RecipeIngredient, ingredient_id).seq_num is None
        assert db.session.get(UnifiedPortion, portion_id).seq_num is None


def test_edit_recipe_prefills_form_from_query_params(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Bakes", user_id=user.id)
        db.session.add(category)
        db.session.flush()
        recipe = _add_recipe(user.id, "Param Recipe", food_category_id=category.id)
        recipe_id, category_id = recipe.id, category.id

    response = client.get(
        url_for("recipes.edit_recipe", recipe_id=recipe_id),
        query_string={
            "servings_param": "6",
            "name_param": "Renamed In Query",
            "instructions_param": "Query instructions",
            "final_weight_grams_param": "not-a-number",
        },
    )
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'value="Renamed In Query"' in html
    assert "Query instructions" in html
    assert 'value="6.0"' in html
    assert f'<option selected value="{category_id}">' in html


def test_edit_recipe_accepts_valid_final_weight_param(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe_id = _add_recipe(user.id, "Numeric Param").id

    response = client.get(
        url_for("recipes.edit_recipe", recipe_id=recipe_id),
        query_string={"final_weight_grams_param": "250.5"},
    )
    assert response.status_code == 200
    assert b'value="250.5"' in response.data


def test_edit_recipe_post_sets_category_upc_and_recalculates(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Mains", user_id=user.id)
        db.session.add(category)
        db.session.flush()
        food = MyFood(
            user_id=user.id,
            description="Saucy Base",
            calories_per_100g=200.0,
            protein_per_100g=10.0,
            carbs_per_100g=20.0,
            fat_per_100g=5.0,
        )
        db.session.add(food)
        db.session.flush()
        recipe = _add_recipe(user.id, "Updater", servings=2.0)
        db.session.add(
            RecipeIngredient(recipe_id=recipe.id, my_food_id=food.id, amount_grams=100)
        )
        db.session.commit()
        recipe_id, category_id = recipe.id, category.id

    response = client.post(
        url_for("recipes.edit_recipe", recipe_id=recipe_id),
        data={
            "name": "Updater v2",
            "servings": "3",
            "upc": "012345678905",
            "instructions": "Combine",
            "final_weight_grams": "200",
            "food_category": str(category_id),
        },
    )
    assert response.status_code == 302
    assert _has_flash(client, "Recipe updated successfully.")

    with client.application.app_context():
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe.name == "Updater v2"
        assert recipe.upc == "012345678905"
        assert recipe.food_category_id == category_id
        # 200 kcal per 100 g over 100 g into a 200 g final weight.
        assert recipe.calories_per_100g == pytest.approx(100.0)


def test_edit_recipe_post_clears_category_when_blank(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Temp Category", user_id=user.id)
        db.session.add(category)
        db.session.flush()
        recipe = _add_recipe(user.id, "Uncategorise Me", food_category_id=category.id)
        recipe_id = recipe.id

    response = client.post(
        url_for("recipes.edit_recipe", recipe_id=recipe_id),
        data={"name": "Uncategorise Me", "servings": "1", "food_category": ""},
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert db.session.get(Recipe, recipe_id).food_category_id is None


def test_edit_recipe_invalid_post_retains_submitted_params(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe_id = _add_recipe(user.id, "Keep My Input").id

    response = client.post(
        url_for(
            "recipes.edit_recipe",
            recipe_id=recipe_id,
            servings_param="5",
            name_param="Typed Name",
            instructions_param="Typed Instructions",
            final_weight_grams_param="oops",
        ),
        data={"name": "Ignored", "servings": ""},
    )
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'value="Typed Name"' in html
    assert "Typed Instructions" in html


def test_edit_recipe_search_block_accepts_query(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        db.session.add(Food(fdc_id=88001, description="Searchable Oats"))
        db.session.add(MyFood(user_id=user.id, description="Searchable Flour"))
        db.session.add(MyMeal(user_id=user.id, name="Searchable Meal"))
        recipe = _add_recipe(user.id, "Search Host")
        db.session.commit()
        recipe_id = recipe.id

    response = client.get(
        url_for("recipes.edit_recipe", recipe_id=recipe_id),
        query_string={"q": "Searchable"},
    )
    assert response.status_code == 200
    assert b'value="Searchable"' in response.data


def test_delete_recipe_anonymizes_then_undo_restores_owner(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe_id = _add_recipe(user.id, "Doomed Recipe").id

    response = client.post(url_for("recipes.delete_recipe", recipe_id=recipe_id))
    assert response.status_code == 302
    with client.application.app_context():
        assert db.session.get(Recipe, recipe_id).user_id is None

    undo_response = client.get(url_for("undo.undo_last_action"))
    assert undo_response.status_code == 302
    with client.application.app_context():
        assert db.session.get(Recipe, recipe_id).user_id == user.id


def test_delete_ingredient_recalculates_and_undo_reinserts(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        food = MyFood(user_id=user.id, description="Droppable", calories_per_100g=100)
        db.session.add(food)
        db.session.flush()
        recipe = _add_recipe(user.id, "Loses An Ingredient")
        ingredient = RecipeIngredient(
            recipe_id=recipe.id, my_food_id=food.id, amount_grams=100
        )
        db.session.add(ingredient)
        db.session.commit()
        recipe_id, ingredient_id = recipe.id, ingredient.id

    response = client.post(
        url_for("recipes.delete_ingredient", ingredient_id=ingredient_id)
    )
    assert response.status_code == 302
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _loc_fragment(response) == "ingredients-section"
    with client.application.app_context():
        assert db.session.get(RecipeIngredient, ingredient_id) is None
        assert db.session.get(Recipe, recipe_id).calories_per_100g == pytest.approx(0)

    undo_response = client.get(url_for("undo.undo_last_action"))
    assert undo_response.status_code == 302
    with client.application.app_context():
        restored = db.session.get(RecipeIngredient, ingredient_id)
        assert restored is not None
        assert restored.amount_grams == pytest.approx(100)


# ---------------------------------------------------------------------------
# Ingredients: update / move
# ---------------------------------------------------------------------------


def _my_food_ingredient(user, with_portion=True, gram_weight=10.0):
    food = MyFood(
        user_id=user.id,
        description="Portioned Item",
        calories_per_100g=200.0,
        protein_per_100g=10.0,
        carbs_per_100g=20.0,
        fat_per_100g=5.0,
    )
    db.session.add(food)
    db.session.flush()
    recipe = _add_recipe(user.id, "Ingredient Host")
    portion = None
    if with_portion:
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1.0,
            measure_unit_description="slice",
            gram_weight=gram_weight,
        )
        db.session.add(portion)
        db.session.flush()
    ingredient = RecipeIngredient(
        recipe_id=recipe.id,
        my_food_id=food.id,
        amount_grams=100,
        portion_id_fk=portion.id if portion else None,
    )
    db.session.add(ingredient)
    db.session.commit()
    return recipe, food, ingredient, portion


def test_update_ingredient_recomputes_grams_and_recipe_nutrition(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe, _food, ingredient, portion = _my_food_ingredient(user)
        recipe_id, ingredient_id, portion_id = recipe.id, ingredient.id, portion.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "3", "portion_id": portion_id},
    )
    assert response.status_code == 302
    assert _has_flash(client, "Ingredient updated successfully.")

    with client.application.app_context():
        ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert ingredient.amount_grams == pytest.approx(30.0)
        assert ingredient.serving_type.strip() == "slice"
        assert ingredient.portion_id_fk == portion_id
        recipe = db.session.get(Recipe, recipe_id)
        # 30 g of a 200 kcal/100 g food, recipe weight = 30 g.
        assert recipe.calories_per_100g == pytest.approx(200.0)


def test_update_ingredient_rejects_portion_of_another_food(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe, _food, ingredient, _portion = _my_food_ingredient(user)
        stranger_food = MyFood(user_id=user.id, description="Other Item")
        db.session.add(stranger_food)
        db.session.flush()
        stranger_portion = UnifiedPortion(
            my_food_id=stranger_food.id, amount=1.0, gram_weight=500.0
        )
        db.session.add(stranger_portion)
        db.session.commit()
        recipe_id, ingredient_id, stranger_portion_id = (
            recipe.id,
            ingredient.id,
            stranger_portion.id,
        )

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "2", "portion_id": stranger_portion_id},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Selected portion does not belong to this ingredient." in response.data

    with client.application.app_context():
        ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert ingredient.amount_grams == pytest.approx(100)
        assert ingredient.portion_id_fk != stranger_portion_id
        assert (
            url_for("recipes.edit_recipe", recipe_id=recipe_id) in response.request.url
        )


def test_update_ingredient_accepts_usda_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        db.session.add(Food(fdc_id=88002, description="USDA Portioned"))
        portion = UnifiedPortion(
            fdc_id=88002,
            amount=1.0,
            measure_unit_description="cup",
            gram_weight=240.0,
        )
        recipe = _add_recipe(user.id, "USDA Ingredient Host")
        db.session.add_all([portion])
        db.session.flush()
        ingredient = RecipeIngredient(
            recipe_id=recipe.id, fdc_id=88002, amount_grams=10, portion_id_fk=portion.id
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id, portion_id = ingredient.id, portion.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "2", "portion_id": portion_id},
    )
    assert response.status_code == 302

    with client.application.app_context():
        ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert ingredient.amount_grams == pytest.approx(480.0)
        assert ingredient.serving_type.strip() == "cup"


def test_update_ingredient_accepts_sub_recipe_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        sub = _add_recipe(user.id, "Sub Sauce")
        sub_portion = UnifiedPortion(
            recipe_id=sub.id,
            amount=1.0,
            measure_unit_description="jar",
            gram_weight=350.0,
        )
        db.session.add(sub_portion)
        db.session.flush()
        main = _add_recipe(user.id, "Main Dish")
        ingredient = RecipeIngredient(
            recipe_id=main.id,
            recipe_id_link=sub.id,
            amount_grams=100,
            portion_id_fk=sub_portion.id,
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id, sub_portion_id = ingredient.id, sub_portion.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "2", "portion_id": sub_portion_id},
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert db.session.get(
            RecipeIngredient, ingredient_id
        ).amount_grams == pytest.approx(700.0)


def test_update_ingredient_accepts_host_recipe_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe, _food, ingredient, _portion = _my_food_ingredient(user)
        own_portion = UnifiedPortion(
            recipe_id=recipe.id,
            amount=1.0,
            measure_unit_description="tray",
            gram_weight=600.0,
        )
        db.session.add(own_portion)
        db.session.commit()
        ingredient_id, own_portion_id = ingredient.id, own_portion.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "1.5", "portion_id": own_portion_id},
    )
    assert response.status_code == 302

    with client.application.app_context():
        assert db.session.get(
            RecipeIngredient, ingredient_id
        ).amount_grams == pytest.approx(900.0)


def test_update_ingredient_rejects_non_owner(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Protected")
        portion = UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0, amount=1.0)
        db.session.add(portion)
        db.session.flush()
        ingredient = RecipeIngredient(
            recipe_id=recipe.id, amount_grams=100, portion_id_fk=portion.id
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id, portion_id = ingredient.id, portion.id

    _login_as(client, user_two.id)
    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "5", "portion_id": portion_id},
    )
    assert response.status_code == 302
    assert _has_flash(client, "You are not authorized to modify this recipe.")

    with client.application.app_context():
        assert db.session.get(RecipeIngredient, ingredient_id).amount_grams == 100


def test_update_ingredient_rejects_non_positive_amount(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        _recipe, _food, ingredient, portion = _my_food_ingredient(user)
        ingredient_id, portion_id = ingredient.id, portion.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "0", "portion_id": portion_id},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Amount must be a positive number." in response.data
    with client.application.app_context():
        assert db.session.get(RecipeIngredient, ingredient_id).amount_grams == 100


def test_update_ingredient_requires_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        _recipe, _food, ingredient, _portion = _my_food_ingredient(user)
        ingredient_id = ingredient.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "2"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion is required." in response.data


def test_update_ingredient_missing_portion_row(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        _recipe, _food, ingredient, _portion = _my_food_ingredient(user)
        ingredient_id = ingredient.id

    response = client.post(
        url_for("recipes.update_ingredient", ingredient_id=ingredient_id),
        data={"amount": "2", "portion_id": "424242"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Selected portion not found." in response.data


def test_move_ingredient_up_rejects_non_owner_then_backfills_seq_nums(
    auth_client_two_users,
):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Shuffle Me")
        first = RecipeIngredient(recipe_id=recipe.id, amount_grams=10)
        second = RecipeIngredient(recipe_id=recipe.id, amount_grams=20)
        db.session.add_all([first, second])
        db.session.commit()
        recipe_id, first_id, second_id = recipe.id, first.id, second.id

    _login_as(client, user_two.id)
    response = client.post(
        url_for("recipes.move_recipe_ingredient_up", ingredient_id=first_id)
    )
    assert response.status_code == 302
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "Ingredient not found or unauthorized.")

    _login_as(client, user_one.id)
    response = client.post(
        url_for("recipes.move_recipe_ingredient_up", ingredient_id=second_id)
    )
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _has_flash(client, "Assigned sequence numbers to all ingredients.")
    with client.application.app_context():
        assert db.session.get(RecipeIngredient, first_id).seq_num == 1
        assert db.session.get(RecipeIngredient, second_id).seq_num == 2


def test_move_ingredient_down_rejects_non_owner_then_backfills_seq_nums(
    auth_client_two_users,
):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Shuffle Down")
        first = RecipeIngredient(recipe_id=recipe.id, amount_grams=10)
        second = RecipeIngredient(recipe_id=recipe.id, amount_grams=20)
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id = first.id, second.id

    _login_as(client, user_two.id)
    response = client.post(
        url_for("recipes.move_recipe_ingredient_down", ingredient_id=first_id)
    )
    assert response.status_code == 302
    assert _has_flash(client, "Ingredient not found or unauthorized.")

    _login_as(client, user_one.id)
    response = client.post(
        url_for("recipes.move_recipe_ingredient_down", ingredient_id=first_id)
    )
    assert _has_flash(client, "Assigned sequence numbers to all ingredients.")
    with client.application.app_context():
        assert db.session.get(RecipeIngredient, first_id).seq_num == 1
        assert db.session.get(RecipeIngredient, second_id).seq_num == 2


# ---------------------------------------------------------------------------
# Viewing a recipe
# ---------------------------------------------------------------------------


def test_view_recipe_renders_every_ingredient_kind(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        db.session.add(Food(fdc_id=88003, description="Displayed USDA Item"))
        my_food = MyFood(user_id=user.id, description="Displayed MyFood")
        sub = _add_recipe(user.id, "Displayed Sub")
        db.session.add(my_food)
        db.session.flush()

        usda_portion = UnifiedPortion(
            fdc_id=88003, amount=2.0, measure_unit_description="cup", gram_weight=120.0
        )
        zero_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=0.0,
            measure_unit_description="",
            gram_weight=0.0,
        )
        db.session.add_all([usda_portion, zero_portion])
        db.session.commit()

        recipe = _add_recipe(user.id, "Mixed Ingredients")
        db.session.add_all(
            [
                RecipeIngredient(
                    recipe_id=recipe.id,
                    fdc_id=88003,
                    amount_grams=360.0,
                    portion_id_fk=usda_portion.id,
                ),
                RecipeIngredient(
                    recipe_id=recipe.id,
                    my_food_id=my_food.id,
                    amount_grams=80.0,
                    portion_id_fk=zero_portion.id,
                ),
                RecipeIngredient(
                    recipe_id=recipe.id, recipe_id_link=sub.id, amount_grams=40.0
                ),
            ]
        )
        db.session.commit()
        recipe_id = recipe.id

    response = client.get(url_for("recipes.view_recipe", recipe_id=recipe_id))
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Displayed USDA Item" in html
    assert "Displayed MyFood" in html
    assert "Displayed Sub" in html
    # 360 g / 120 g per portion = 3.00 cups
    assert "3.00" in html
    # Zero gram portions fall back to grams.
    assert "80.00" in html


def test_view_recipe_tolerates_missing_usda_row(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = _add_recipe(user.id, "Dangling USDA")
        db.session.add(
            RecipeIngredient(recipe_id=recipe.id, fdc_id=999999, amount_grams=25.0)
        )
        db.session.commit()
        recipe_id = recipe.id

    response = client.get(url_for("recipes.view_recipe", recipe_id=recipe_id))
    assert response.status_code == 200
    assert b"Unknown Food" in response.data


# ---------------------------------------------------------------------------
# Portions
# ---------------------------------------------------------------------------


def test_auto_add_recipe_portion_rejects_non_owner(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe_id = _add_recipe(user_one.id, "Someone Elses Servings").id

    _login_as(client, user_two.id)
    response = client.post(
        url_for("recipes.auto_add_recipe_portion", recipe_id=recipe_id),
        data={"servings": "4"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"You are not authorized to modify this recipe." in response.data


@pytest.mark.parametrize("servings", ["0", "", "-2"])
def test_auto_add_recipe_portion_rejects_bad_servings(auth_client_with_user, servings):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe_id = _add_recipe(user.id, "Bad Servings").id

    response = client.post(
        url_for("recipes.auto_add_recipe_portion", recipe_id=recipe_id),
        data={"servings": servings},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid servings value provided." in response.data
    with client.application.app_context():
        assert UnifiedPortion.query.filter_by(recipe_id=recipe_id).count() == 0


def test_auto_add_recipe_portion_echoes_form_values(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = _add_recipe(user.id, "Echo Recipe", servings=2.0)
        db.session.add(RecipeIngredient(recipe_id=recipe.id, amount_grams=250))
        db.session.commit()
        recipe_id = recipe.id

    response = client.post(
        url_for("recipes.auto_add_recipe_portion", recipe_id=recipe_id),
        data={
            "servings": "5",
            "name": "Echo Recipe Edited",
            "instructions": "New instructions",
            "final_weight_grams": "500",
        },
    )
    assert response.status_code == 302
    assert _has_flash(client, "Portion created based on the final cooked weight")

    follow = client.get(response.headers["Location"])
    assert follow.status_code == 200
    assert b'value="Echo Recipe Edited"' in follow.data


def test_add_recipe_portion_sequenced_after_existing(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = _add_recipe(user.id, "Sequenced Portions")
        db.session.add(UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0, seq_num=4))
        db.session.commit()
        recipe_id = recipe.id

    client.post(
        url_for("recipes.add_recipe_portion", recipe_id=recipe_id),
        data={
            "portion_description": "bowl",
            "gram_weight": "300",
            "amount": "1",
            "measure_unit_description": "bowl",
            "modifier": "",
        },
    )
    with client.application.app_context():
        newest = (
            UnifiedPortion.query.filter_by(recipe_id=recipe_id)
            .order_by(UnifiedPortion.id.desc())
            .first()
        )
        assert newest.seq_num == 5


def test_update_recipe_portion_rejects_missing_and_non_recipe_portions(
    auth_client_with_user,
):
    client, user = auth_client_with_user
    with client.application.app_context():
        food = MyFood(user_id=user.id, description="Portion Owner")
        db.session.add(food)
        db.session.flush()
        food_portion = UnifiedPortion(my_food_id=food.id, gram_weight=10.0)
        db.session.add(food_portion)
        db.session.commit()
        food_portion_id = food_portion.id

    for portion_id in (424243, food_portion_id):
        response = client.post(
            url_for("recipes.update_recipe_portion", portion_id=portion_id),
            data={"gram_weight": "20", "amount": "1", "measure_unit_description": "g"},
        )
        assert response.status_code == 302
        assert _loc(response) == _path(url_for("recipes.recipes"))
        assert _has_flash(
            client, "Portion not found or you do not have permission to edit it."
        )


def test_update_recipe_portion_redirects_to_recipe_table(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = _add_recipe(user.id, "Portion Update")
        portion = UnifiedPortion(recipe_id=recipe.id, gram_weight=50.0, amount=1.0)
        db.session.add(portion)
        db.session.commit()
        recipe_id, portion_id = recipe.id, portion.id

    response = client.post(
        url_for("recipes.update_recipe_portion", portion_id=portion_id),
        data={
            "portion_description": "half",
            "gram_weight": "55",
            "amount": "1",
            "measure_unit_description": "portion",
            "modifier": "cooked",
        },
    )
    assert response.status_code == 302
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _loc_fragment(response) == "portions-table"
    assert _has_flash(client, "Portion updated successfully!")


def test_delete_recipe_portion_rejects_non_recipe_portion(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        food = MyFood(user_id=user.id, description="Food Portion Guard")
        db.session.add(food)
        db.session.flush()
        food_portion = UnifiedPortion(my_food_id=food.id, gram_weight=12.0)
        db.session.add(food_portion)
        db.session.commit()
        food_portion_id = food_portion.id

    for portion_id in (424244, food_portion_id):
        response = client.post(
            url_for("recipes.delete_recipe_portion", portion_id=portion_id)
        )
        assert response.status_code == 302
        assert _loc(response) == _path(url_for("recipes.recipes"))
        assert _has_flash(
            client, "Portion not found or you do not have permission to delete it."
        )


def test_move_recipe_portion_up_guards_and_swap(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Portion Order")
        mine = MyFood(user_id=user_one.id, description="Foreign Portion Owner")
        db.session.add(mine)
        db.session.flush()
        foreign = UnifiedPortion(my_food_id=mine.id, gram_weight=5.0, seq_num=1)
        p1 = UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0)
        p2 = UnifiedPortion(recipe_id=recipe.id, gram_weight=20.0)
        db.session.add_all([foreign, p1, p2])
        db.session.commit()
        recipe_id, foreign_id, p1_id, p2_id = (
            recipe.id,
            foreign.id,
            p1.id,
            p2.id,
        )

    # Unknown portion id.
    response = client.post(url_for("recipes.move_recipe_portion_up", portion_id=424245))
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "Portion not found or unauthorized.")

    # Portion that belongs to a MyFood, not a recipe.
    response = client.post(
        url_for("recipes.move_recipe_portion_up", portion_id=foreign_id)
    )
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "Portion not found or unauthorized.")

    # Another user's recipe portion.
    _login_as(client, user_two.id)
    response = client.post(url_for("recipes.move_recipe_portion_up", portion_id=p1_id))
    assert _has_flash(client, "Portion not found or unauthorized.")
    _login_as(client, user_one.id)

    # Missing seq_num: backfill and ask to retry.
    response = client.post(url_for("recipes.move_recipe_portion_up", portion_id=p2_id))
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _has_flash(client, "Assigned sequence numbers to all portions.")
    with client.application.app_context():
        assert db.session.get(UnifiedPortion, p1_id).seq_num == 1
        assert db.session.get(UnifiedPortion, p2_id).seq_num == 2

    # Already at the top.
    response = client.post(url_for("recipes.move_recipe_portion_up", portion_id=p1_id))
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _loc_fragment(response) == "portions-table"
    assert _has_flash(client, "Portion is already at the top.")

    # Real swap.
    client.post(url_for("recipes.move_recipe_portion_up", portion_id=p2_id))
    with client.application.app_context():
        assert db.session.get(UnifiedPortion, p1_id).seq_num == 2
        assert db.session.get(UnifiedPortion, p2_id).seq_num == 1


def test_move_recipe_portion_down_guards(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe = _add_recipe(user_one.id, "Portion Order Down")
        mine = MyFood(user_id=user_one.id, description="Down Portion Owner")
        db.session.add(mine)
        db.session.flush()
        foreign = UnifiedPortion(my_food_id=mine.id, gram_weight=5.0, seq_num=1)
        only = UnifiedPortion(recipe_id=recipe.id, gram_weight=10.0, seq_num=1)
        db.session.add_all([foreign, only])
        db.session.commit()
        recipe_id, foreign_id, only_id = recipe.id, foreign.id, only.id

    response = client.post(
        url_for("recipes.move_recipe_portion_down", portion_id=424246)
    )
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "Portion not found or unauthorized.")

    response = client.post(
        url_for("recipes.move_recipe_portion_down", portion_id=foreign_id)
    )
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "Portion not found or unauthorized.")

    _login_as(client, user_two.id)
    response = client.post(
        url_for("recipes.move_recipe_portion_down", portion_id=only_id)
    )
    assert _has_flash(client, "Portion not found or unauthorized.")
    _login_as(client, user_one.id)

    response = client.post(
        url_for("recipes.move_recipe_portion_down", portion_id=only_id)
    )
    assert _loc(response) == _path(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert _loc_fragment(response) == "portions-table"
    assert _has_flash(client, "Portion is already at the bottom.")


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------


def test_copy_recipe_rejects_strangers_private_recipe(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe_id = _add_recipe(user_one.id, "Secret Sauce").id

    _login_as(client, user_two.id)
    response = client.post(url_for("recipes.copy_recipe", recipe_id=recipe_id))
    assert response.status_code == 302
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(
        client, "You can only copy recipes from your friends or public recipes."
    )
    with client.application.app_context():
        assert Recipe.query.filter_by(name="Secret Sauce (Copy)").count() == 0


def test_copy_recipe_from_friend_is_private_copy(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship
    with client.application.app_context():
        source = _add_recipe(friend.id, "Friends Stew", servings=3.0, is_public=False)
        db.session.add(
            UnifiedPortion(recipe_id=source.id, gram_weight=250.0, seq_num=1)
        )
        db.session.commit()
        source_id = source.id

    response = client.post(url_for("recipes.copy_recipe", recipe_id=source_id))
    assert response.status_code == 302
    assert _has_flash(client, "Successfully copied")

    with client.application.app_context():
        copy = Recipe.query.filter_by(name="Friends Stew (Copy)").one()
        assert copy.user_id == me.id
        assert copy.is_public is False
        assert copy.servings == pytest.approx(3.0)
        assert len(copy.portions) == 1


def test_copy_recipe_missing_recipe_is_404(auth_client):
    response = auth_client.post(url_for("recipes.copy_recipe", recipe_id=424247))
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Nutrition label routes
# ---------------------------------------------------------------------------


@pytest.fixture
def label_recipe(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        food = MyFood(user_id=user.id, description="Label Ingredient")
        db.session.add(food)
        db.session.flush()
        recipe = _add_recipe(user.id, "Labelled Recipe")
        db.session.add(
            RecipeIngredient(recipe_id=recipe.id, my_food_id=food.id, amount_grams=120)
        )
        db.session.commit()
        return client, user, recipe.id


def test_owner_can_render_svg_label(label_recipe):
    client, _user, recipe_id = label_recipe
    response = client.get(url_for("recipes.nutrition_label_svg", recipe_id=recipe_id))
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert b"<svg" in response.data


def test_stranger_cannot_render_private_svg_label(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe_id = _add_recipe(user_one.id, "Private Label").id

    _login_as(client, user_two.id)
    response = client.get(url_for("recipes.nutrition_label_svg", recipe_id=recipe_id))
    assert response.status_code == 403


def test_public_recipe_svg_label_readable_by_other_user(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe_id = _add_recipe(user_one.id, "Public Label", is_public=True).id

    _login_as(client, user_two.id)
    response = client.get(url_for("recipes.nutrition_label_svg", recipe_id=recipe_id))
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"


def test_svg_label_of_missing_recipe_is_404(auth_client):
    response = auth_client.get(url_for("recipes.nutrition_label_svg", recipe_id=424248))
    assert response.status_code == 404


def test_generate_label_pdf_owner_and_stranger(label_recipe):
    client, _user, recipe_id = label_recipe
    response = client.get(url_for("recipes.generate_label_pdf", recipe_id=recipe_id))
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data[:4] == b"%PDF"


def test_generate_label_pdf_denied_for_private_recipe(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        recipe_id = _add_recipe(user_one.id, "Pdf Private").id

    _login_as(client, user_two.id)
    response = client.get(url_for("recipes.generate_label_pdf", recipe_id=recipe_id))
    assert response.status_code == 302
    assert _loc(response) == _path(url_for("recipes.recipes"))
    assert _has_flash(client, "You are not authorized to view this recipe.")


def test_generate_pdf_details_owner_and_stranger(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        mine = _add_recipe(user_one.id, "Details Recipe")
        food = MyFood(user_id=user_one.id, description="Details Ingredient")
        db.session.add(food)
        db.session.flush()
        db.session.add(
            RecipeIngredient(recipe_id=mine.id, my_food_id=food.id, amount_grams=100)
        )
        db.session.commit()
        my_id, other_id = (
            mine.id,
            _add_recipe(user_one.id, "Details Private", is_public=False).id,
        )

    response = client.get(url_for("recipes.generate_pdf_details", recipe_id=my_id))
    assert response.status_code == 200
    assert response.data[:4] == b"%PDF"

    _login_as(client, user_two.id)
    denied = client.get(
        url_for("recipes.generate_pdf_details", recipe_id=other_id),
        follow_redirects=True,
    )
    assert denied.status_code == 200
    assert b"You are not authorized to view this recipe." in denied.data
    assert _loc(denied.history[0]) == _path(url_for("recipes.recipes"))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_recipes_round_trips_and_tolerates_missing_portions(
    auth_client_with_user,
):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Global Bakery", user_id=None)
        db.session.add(category)
        db.session.flush()

        sub = Recipe(user_id=user.id, name="Sub Syrup", food_category=category)
        db.session.add(sub)
        db.session.flush()

        placeholder = MyFood(
            user_id=user.id,
            description="Placeholder Flour",
            calories_per_100g=364.0,
            is_placeholder=True,
        )
        zero_food = MyFood(
            user_id=user.id, description="Zero Portion Food", calories_per_100g=50.0
        )
        scaled_food = MyFood(
            user_id=user.id, description="Scaled Food", calories_per_100g=100.0
        )
        db.session.add_all([placeholder, zero_food, scaled_food])
        db.session.flush()
        db.session.add_all(
            [
                UnifiedPortion(my_food_id=zero_food.id, amount=1.0, gram_weight=0.0),
                UnifiedPortion(
                    my_food_id=scaled_food.id,
                    amount=2.0,
                    measure_unit_description="bag",
                    gram_weight=250.0,
                ),
            ]
        )
        db.session.flush()

        recipe = Recipe(
            user_id=user.id,
            name="Export Recipe",
            servings=2.0,
            instructions="Mix",
            final_weight_grams=300.0,
            food_category=category,
        )
        db.session.add(recipe)
        db.session.flush()

        fdc_portion = UnifiedPortion(
            fdc_id=777001,
            amount=1.0,
            measure_unit_description="cup",
            gram_weight=240.0,
        )
        db.session.add(fdc_portion)
        db.session.flush()

        db.session.add_all(
            [
                RecipeIngredient(
                    recipe_id=recipe.id,
                    fdc_id=777001,
                    amount_grams=240.0,
                    portion_id_fk=fdc_portion.id,
                ),
                # No portion at all.
                RecipeIngredient(
                    recipe_id=recipe.id, my_food_id=placeholder.id, amount_grams=100.0
                ),
                # Portion id pointing at a row that no longer exists.
                RecipeIngredient(
                    recipe_id=recipe.id,
                    my_food_id=zero_food.id,
                    amount_grams=100.0,
                    portion_id_fk=424249,
                ),
                RecipeIngredient(
                    recipe_id=recipe.id,
                    my_food_id=scaled_food.id,
                    amount_grams=100.0,
                ),
                RecipeIngredient(
                    recipe_id=recipe.id, recipe_id_link=sub.id, amount_grams=50.0
                ),
                RecipeIngredient(recipe_id=sub.id, amount_grams=25.0),
                # A circular link so the export queue is fed from both sides.
                RecipeIngredient(
                    recipe_id=sub.id, recipe_id_link=recipe.id, amount_grams=10.0
                ),
            ]
        )
        db.session.commit()

    response = client.get(url_for("recipes.export_recipes"))
    assert response.status_code == 200
    assert response.mimetype == "application/x-yaml"
    assert "recipes_export_" in response.headers["Content-Disposition"]

    payload = yaml.safe_load(response.data)
    assert payload["format_version"] == 1.0
    exported_names = {r["name"] for r in payload["recipes"]}
    assert exported_names == {"Export Recipe", "Sub Syrup"}

    main = next(r for r in payload["recipes"] if r["name"] == "Export Recipe")
    assert main["category"] == "Global Bakery"
    assert "portion" in main["ingredients"][0]
    assert "portion" not in main["ingredients"][1]
    assert "portion" not in main["ingredients"][2]

    sub_export = next(r for r in payload["recipes"] if r["name"] == "Sub Syrup")
    assert sub_export["category"] == "Global Bakery"

    by_description = {f["description"]: f for f in payload["dependent_my_foods"]}
    assert by_description["Placeholder Flour"]["is_placeholder"] is True
    # A food whose only portion weighs 0 g exports no nutrition facts.
    assert by_description["Zero Portion Food"]["nutrition_facts"] == {}
    assert by_description["Zero Portion Food"]["portions"] == [
        {"amount": 1.0, "measure_unit_description": "", "gram_weight": 0.0}
    ]
    # A 250 g portion scales the per-100 g values by 2.5.
    scaled = by_description["Scaled Food"]["nutrition_facts"]
    assert scaled["calories"] == pytest.approx(250.0)

    # The export must be importable by the same code that produced it.
    reimport = client.post(
        url_for("recipes.import_recipes"),
        data={"yaml_text": response.data.decode("utf-8")},
        follow_redirects=True,
    )
    assert reimport.status_code == 200
    assert b"Import successful!" in reimport.data


def test_export_recipes_empty_user(auth_client):
    response = auth_client.get(url_for("recipes.export_recipes"))
    assert response.status_code == 200
    payload = yaml.safe_load(response.data)
    assert payload["recipes"] == []
    assert payload["dependent_my_foods"] == []


# ---------------------------------------------------------------------------
# Import: route plumbing
# ---------------------------------------------------------------------------


def test_import_page_renders(auth_client):
    response = auth_client.get(url_for("recipes.import_recipes"))
    assert response.status_code == 200
    assert b"import" in response.data.lower()


def test_import_post_without_file_or_text(auth_client):
    response = auth_client.post(url_for("recipes.import_recipes"), data={})
    assert response.status_code == 302
    assert _has_flash(auth_client, "No file or text provided.")


def test_import_post_blank_file_is_treated_as_missing(auth_client):
    response = auth_client.post(
        url_for("recipes.import_recipes"),
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert _has_flash(auth_client, "No file or text provided.")


@pytest.mark.parametrize("filename", ["notes.txt", "recipes.yaml.bak"])
def test_import_post_rejects_non_yaml_file(auth_client, filename):
    response = auth_client.post(
        url_for("recipes.import_recipes"),
        data={"file": (io.BytesIO(b"name: Nope\n"), filename)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert _has_flash(auth_client, "Invalid file type. Please upload a .yaml file.")


@pytest.mark.parametrize("filename", ["recipes.yaml", "recipes.yml"])
def test_import_yaml_file_upload_simple(auth_client, filename):
    body = (
        "name: Uploaded Pancakes\n"
        "servings: 3\n"
        "instructions: Mix well\n"
        "ingredients:\n"
        "  - name: Flour\n"
        "    quantity: 2\n"
        "    unit: cup\n"
        "    notes: sifted\n"
    )
    response = auth_client.post(
        url_for("recipes.import_recipes"),
        data={"file": (io.BytesIO(body.encode("utf-8")), filename)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert _has_flash(
        auth_client, "Recipe imported! Please match the ingredients to real foods."
    )

    with auth_client.application.app_context():
        recipe = Recipe.query.filter_by(name="Uploaded Pancakes").one()
        assert recipe.servings == pytest.approx(3.0)
        assert len(recipe.ingredients) == 1
        ingredient = recipe.ingredients[0]
        assert ingredient.amount_grams == pytest.approx(2.0)
        assert ingredient.my_food.is_placeholder is True
        portion = UnifiedPortion.query.filter_by(my_food_id=ingredient.my_food_id).one()
        assert portion.measure_unit_description == "cup"
        assert portion.modifier == "sifted"
        assert _loc(response) == _path(
            url_for("recipes.edit_recipe", recipe_id=recipe.id)
        )


# ---------------------------------------------------------------------------
# Import: malformed input
# ---------------------------------------------------------------------------


def test_import_empty_yaml_document(auth_client):
    response = _import_text(auth_client, "# nothing to see here\n")
    assert response.status_code == 302
    assert _has_flash(auth_client, "No data found in the YAML content.")


def test_import_unparsable_yaml(auth_client):
    response = _import_text(auth_client, "name: Broken\ningredients: [unclosed\n")
    assert response.status_code == 302
    assert _has_flash(auth_client, "Error parsing YAML file:")


def test_import_unknown_yaml_shape(auth_client):
    response = _import_text(auth_client, "just_a_key: some value\n")
    assert response.status_code == 302
    assert _has_flash(
        auth_client, "Invalid YAML format. Could not determine import type."
    )


def test_import_simple_without_name(auth_client):
    response = _import_text(auth_client, "ingredients:\n  - name: Salt\n")
    assert response.status_code == 302
    assert _has_flash(auth_client, "Simple import requires a 'name' for the recipe.")
    with auth_client.application.app_context():
        assert Recipe.query.count() == 0


def test_import_simple_skips_broken_ingredient_entries(auth_client):
    text = (
        "name: Patchy Recipe\n"
        "servings: 2\n"
        "ingredients:\n"
        "  - just a bare string\n"
        "  - quantity: 5\n"
        "  - name: Real Item\n"
    )
    response = _import_text(auth_client, text)
    assert response.status_code == 302
    flashes = _flashes(auth_client)
    assert any("Skipping invalid ingredient entry" in m for m in flashes)
    assert any("Skipping ingredient with no name." in m for m in flashes)

    with auth_client.application.app_context():
        recipe = Recipe.query.filter_by(name="Patchy Recipe").one()
        assert len(recipe.ingredients) == 1


def test_import_simple_defaults_quantity_to_one(auth_client):
    _import_text(auth_client, "name: Default Quantity\ningredients:\n  - name: Water\n")
    with auth_client.application.app_context():
        recipe = Recipe.query.filter_by(name="Default Quantity").one()
        assert recipe.servings == pytest.approx(1.0)
        assert recipe.ingredients[0].amount_grams == pytest.approx(1.0)


def test_import_complex_rejects_non_list_sections(auth_client):
    response = _import_text(auth_client, "dependent_my_foods: not a list\n")
    assert response.status_code == 302
    assert _has_flash(
        auth_client,
        "Complex import must contain 'dependent_my_foods' and 'recipes' as lists.",
    )


def test_import_complex_unexpected_error_rolls_back(auth_client):
    response = _import_text(auth_client, "recipes:\n  - a bare recipe string\n")
    assert response.status_code == 302
    assert _has_flash(auth_client, "An unexpected error occurred during import:")
    with auth_client.application.app_context():
        assert Recipe.query.count() == 0


# ---------------------------------------------------------------------------
# Import: complex format
# ---------------------------------------------------------------------------


def test_import_complex_creates_foods_portions_and_reuses_portion(auth_client):
    with auth_client.application.app_context():
        db.session.add(FoodCategory(description="Pantry", user_id=None))
        db.session.commit()

    text = """
dependent_my_foods:
  - description: Imported Flour
    category: Bakery
    ingredients: wheat
    upc: "000123"
    nutrition_facts:
      calories: 364
      protein_grams: 10
      carbohydrates_grams: 76
      fat_grams: 1
    portions:
      - amount: 1
        measure_unit_description: cup
        gram_weight: 120
  - description: Imported Flour
    category: Bakery
  - category: No Description Here
  - description: Second Food
    category: bakery
  - description: Pantry Item
    category: PANTRY
  - description: Self Category
    category: Self Category
  - description: No Portion Food
    nutrition_facts:
      calories: 42
recipes:
  - name: Imported Cake
    servings: 8
    instructions: Bake
    category: Bakery
    final_weight_grams: 900
    portions:
      - amount: 1
        measure_unit_description: slice
        gram_weight: 112.5
      - amount: 0.5
        measure_unit_description: wedge
        gram_weight: 56.25
    ingredients:
      - type: my_food
        identifier: Imported Flour
        amount_grams: 240
        portion:
          amount: 1
          measure_unit_description: cup
          gram_weight: 120
      - type: recipe
        identifier: Existing Sauce
        amount_grams: 60
        portion:
          amount: 1
          measure_unit_description: jar
          gram_weight: 400
      - type: usda
        identifier: 12345
        amount_grams: 30
        portion:
          amount: 1
          measure_unit_description: serving
          gram_weight: 140
      - type: my_food
        identifier: Never Seen Item
        amount_grams: 10
"""
    with auth_client.application.app_context():
        owner = User.query.filter_by(username="testuser").one()
        sauce = Recipe(user_id=owner.id, name="Existing Sauce")
        db.session.add(sauce)
        db.session.flush()
        db.session.add(
            UnifiedPortion(
                recipe_id=sauce.id,
                amount=1,
                measure_unit_description="jar",
                gram_weight=400,
            )
        )
        db.session.commit()

    response = _import_text(auth_client, text)
    assert response.status_code == 302
    assert _has_flash(auth_client, "Import successful!")

    with auth_client.application.app_context():
        flour = MyFood.query.filter_by(description="Imported Flour").one()
        # The duplicate entry was skipped.
        assert MyFood.query.filter_by(description="Imported Flour").count() == 1
        assert flour.food_category.description == "Bakery"
        # 364 kcal for a 120 g portion -> 303.33 kcal per 100 g.
        assert flour.calories_per_100g == pytest.approx(364.0 * 100.0 / 120.0)

        # Case-insensitive lookup reused the user's own category.
        second = MyFood.query.filter_by(description="Second Food").one()
        assert second.food_category.id == flour.food_category.id

        # A global category was adopted instead of creating a new row.
        pantry_item = MyFood.query.filter_by(description="Pantry Item").one()
        assert pantry_item.food_category.user_id is None

        # category == description stores no category at all.
        self_cat = MyFood.query.filter_by(description="Self Category").one()
        assert self_cat.food_category is None

        # A food without portions stores zeroed nutrition.
        no_portion = MyFood.query.filter_by(description="No Portion Food").one()
        assert no_portion.calories_per_100g == pytest.approx(0.0)

        cake = Recipe.query.filter_by(name="Imported Cake").one()
        assert cake.is_public is False
        assert cake.final_weight_grams == pytest.approx(900.0)
        assert {p.measure_unit_description for p in cake.portions} == {
            "slice",
            "wedge",
        }

        by_type = {}
        for ingredient in cake.ingredients:
            if ingredient.my_food_id:
                by_type["my_food"] = ingredient
            elif ingredient.recipe_id_link:
                by_type["recipe"] = ingredient
            else:
                by_type["usda"] = ingredient

        # Existing portions are matched, not duplicated.
        flour_portion = UnifiedPortion.query.filter_by(my_food_id=flour.id).one()
        assert by_type["my_food"].portion_id_fk == flour_portion.id
        sauce = Recipe.query.filter_by(name="Existing Sauce").one()
        sauce_portion = UnifiedPortion.query.filter_by(recipe_id=sauce.id).one()
        assert by_type["recipe"].recipe_id_link == sauce.id
        assert by_type["recipe"].portion_id_fk == sauce_portion.id
        assert UnifiedPortion.query.filter_by(fdc_id=12345).count() == 1

        # Ingredients whose identifier matches nothing are still recorded
        # without a food link.
        assert cake.ingredients[3].my_food_id is None

        # Nutrition was rolled up from the ingredients.
        assert cake.calories_per_100g > 0


def test_import_complex_skips_existing_names(auth_client):
    first = """
dependent_my_foods:
  - description: Solo Flour
    portions:
      - amount: 1
        measure_unit_description: cup
        gram_weight: 100
recipes:
  - name: Solo Cake
    servings: 4
    ingredients:
      - type: my_food
        identifier: Solo Flour
        amount_grams: 100
"""
    _import_text(auth_client, first)
    with auth_client.application.app_context():
        assert Recipe.query.count() == 1
        assert MyFood.query.count() == 1

    response = _import_text(auth_client, first)
    assert response.status_code == 302
    assert _has_flash(
        auth_client, "Import successful! Added 0 new recipes and 0 new foods."
    )
    with auth_client.application.app_context():
        assert Recipe.query.count() == 1
        assert MyFood.query.count() == 1
        # Re-import reuses the portion and does not duplicate the ingredient.
        cake = Recipe.query.filter_by(name="Solo Cake").one()
        assert len(cake.ingredients) == 1
        assert (
            UnifiedPortion.query.filter_by(
                my_food_id=cake.ingredients[0].my_food_id
            ).count()
            == 1
        )
