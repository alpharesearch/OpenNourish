"""Coverage and regression tests for ``opennourish/diary``.

Locked regressions:

1. ``DASHBOARD_ROUTE`` must name a registered endpoint (it used to be the
   non-existent ``"dashboard.dashboard"``, so every early return in
   ``copy_meal_from_friend`` raised ``BuildError``).
2. ``UserGoal`` is looked up by ``user_id``, never by its surrogate PK (a
   ``db.session.get(UserGoal, user_id)`` can hand back another account's goal).
3. A stored ``meal_name`` outside ``constants.ALL_MEAL_TYPES`` (the bare
   ``"Snack"`` of ``AddToLogForm``, or a meal orphaned by a ``meals_per_day``
   change) renders as its own block instead of crashing the day page.
"""

from datetime import timedelta

import pytest
from flask import url_for

from models import (
    db,
    DailyLog,
    ExerciseLog,
    FastingSession,
    Food,
    FoodNutrient,
    MyFood,
    MyMeal,
    MyMealItem,
    Nutrient,
    Recipe,
    RecipeIngredient,
    UnifiedPortion,
    User,
    UserGoal,
)
from opennourish.time_utils import get_user_today


def today():
    """ "Today" for the fixture users, which all use the UTC timezone."""
    return get_user_today("UTC")


def iso_day(offset_days=0):
    return (today() + timedelta(days=offset_days)).isoformat()


def make_my_food(user_id, description="Test Food", calories=100.0, with_portion=True):
    """Create a ``MyFood`` (plus its 1 g portion) and return ``(id, portion_id)``."""
    food = MyFood(
        user_id=user_id,
        description=description,
        calories_per_100g=calories,
        protein_per_100g=5.0,
        carbs_per_100g=10.0,
        fat_per_100g=2.0,
    )
    db.session.add(food)
    db.session.flush()
    portion_id = None
    if with_portion:
        portion = UnifiedPortion(
            my_food_id=food.id,
            gram_weight=1.0,
            amount=1.0,
            measure_unit_description="g",
            seq_num=1,
        )
        db.session.add(portion)
        db.session.flush()
        portion_id = portion.id
    return food.id, portion_id


def user_id_of(client, username):
    return User.query.filter_by(username=username).first().id


# ---------------------------------------------------------------------------
# Bug 1 — the dashboard endpoint literal
# ---------------------------------------------------------------------------


def test_dashboard_route_constant_names_a_registered_endpoint(app_with_db):
    """``DASHBOARD_ROUTE`` must resolve, otherwise the friend-copy redirects 500."""
    from opennourish.diary.routes import DASHBOARD_ROUTE

    assert DASHBOARD_ROUTE == "dashboard.index"
    with app_with_db.app_context():
        assert url_for(DASHBOARD_ROUTE).endswith("/dashboard/")


@pytest.mark.parametrize(
    "payload",
    [
        # Missing everything.
        {},
        # Missing meal_name only.
        {"friend_username": "somebody", "log_date": "2025-01-01"},
        # Complete payload but the username does not exist.
        {
            "friend_username": "nobody_here",
            "log_date": "2025-01-01",
            "meal_name": "Breakfast",
        },
    ],
)
def test_copy_meal_from_friend_early_returns_redirect_to_dashboard(
    auth_client, payload
):
    """Regression: these three redirects used to raise ``BuildError``."""
    response = auth_client.post("/diary/copy_meal_from_friend", data=payload)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")

    followed = auth_client.get("/diary/", follow_redirects=False)
    assert followed.status_code == 200


def test_copy_meal_from_friend_rejects_non_friend(auth_client_two_users):
    """Security negative test: no rows may be read or written for a stranger."""
    client, user_one, user_two = auth_client_two_users
    day = today()

    with client.application.app_context():
        db.session.add(
            DailyLog(
                user_id=user_two.id,
                log_date=day,
                meal_name="Breakfast",
                amount_grams=100,
                fdc_id=12345,
            )
        )
        db.session.commit()

    response = client.post(
        "/diary/copy_meal_from_friend",
        data={
            "friend_username": "user_two",
            "log_date": day.isoformat(),
            "meal_name": "Breakfast",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")
    assert (
        b"You are not friends with user_two."
        in client.get(f"/diary/{day.isoformat()}").data
    )

    with client.application.app_context():
        assert DailyLog.query.filter_by(user_id=user_one.id).count() == 0


def test_copy_meal_from_friend_copies_friend_meal(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship
    day = today()

    with client.application.app_context():
        friend_food, _ = make_my_food(friend.id, "Friend Stew", 90.0)
        db.session.add(
            DailyLog(
                user_id=friend.id,
                log_date=day,
                meal_name="Lunch",
                my_food_id=friend_food,
                amount_grams=250,
                serving_type="g",
            )
        )
        db.session.commit()

    response = client.post(
        "/diary/copy_meal_from_friend",
        data={
            "friend_username": friend.username,
            "log_date": day.isoformat(),
            "meal_name": "Lunch",
        },
    )

    assert response.status_code == 302
    assert f"/diary/{day.isoformat()}" in response.headers["Location"]

    with client.application.app_context():
        copied = DailyLog.query.filter_by(user_id=me.id, meal_name="Lunch").all()
        assert len(copied) == 1
        assert copied[0].my_food_id == friend_food
        assert copied[0].amount_grams == pytest.approx(250.0)
        assert copied[0].log_date == day

    page = client.get(f"/diary/{day.isoformat()}")
    assert b"Successfully copied Lunch" in page.data
    # The copied row points at somebody else's food, so it is labelled as such.
    assert f"(from {friend.username})".encode() in page.data


def test_copy_meal_from_friend_empty_meal_redirects_to_profile(
    auth_client_with_friendship,
):
    client, _me, friend = auth_client_with_friendship
    day = today()

    response = client.post(
        "/diary/copy_meal_from_friend",
        data={
            "friend_username": friend.username,
            "log_date": day.isoformat(),
            "meal_name": "Dinner",
        },
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert f"/user/{friend.username}/diary" in location
    assert "/dashboard/" not in location


# ---------------------------------------------------------------------------
# Bug 2 — UserGoal looked up by the wrong column
# ---------------------------------------------------------------------------


def _seed_shifted_goal_ids(app):
    """Give the signed-in user a goal whose PK differs from their user id.

    Returns ``(user, own_goal_calories, other_goal_calories)``. ``testuser`` is
    user 1; the *first* goal row belongs to another account, so the old
    ``db.session.get(UserGoal, current_user.id)`` returned that row.
    """
    with app.app_context():
        user = User.query.filter_by(username="testuser").first()
        stranger = User(username="goal_stranger", email="goal_stranger@example.com")
        stranger.set_password("password")
        db.session.add(stranger)
        db.session.commit()

        db.session.add(
            UserGoal(user_id=stranger.id, calories=3000, protein=90, carbs=300, fat=100)
        )
        db.session.commit()
        db.session.add(
            UserGoal(user_id=user.id, calories=1500, protein=120, carbs=140, fat=45)
        )
        db.session.commit()
        return user.id


def test_diary_page_uses_own_goal_when_goal_pk_differs_from_user_id(auth_client):
    _seed_shifted_goal_ids(auth_client.application)

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b"Goal: 1500.0 kcal" in page.data
    assert b"Goal: 3000.0 kcal" not in page.data


def test_get_remaining_calories_uses_own_goal_when_pk_differs(auth_client):
    _seed_shifted_goal_ids(auth_client.application)

    response = auth_client.get(f"/api/get-remaining-calories/{iso_day()}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["goal_calories"] == 1500
    assert data["calories_consumed"] == 0
    assert data["remaining_calories"] == 1500


def test_get_remaining_calories_counts_logs_and_exercise(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, _ = make_my_food(user_id, "Api Snack", 200.0)
        day = today()
        db.session.add(
            DailyLog(
                user_id=user_id,
                log_date=day,
                meal_name="Snack (afternoon)",
                my_food_id=food_id,
                amount_grams=100,
            )
        )
        db.session.add(
            ExerciseLog(
                user_id=user_id,
                log_date=day,
                duration_minutes=30,
                calories_burned=250,
                manual_description="Cycling",
            )
        )
        db.session.add(UserGoal(user_id=user_id, calories=2000))
        db.session.commit()

    response = auth_client.get(f"/api/get-remaining-calories/{iso_day()}")

    data = response.get_json()
    assert data["calories_consumed"] == pytest.approx(200.0)
    assert data["calories_burned"] == 250
    assert data["remaining_calories"] == pytest.approx(2050.0)


def test_get_remaining_calories_without_goal(auth_client):
    response = auth_client.get(f"/api/get-remaining-calories/{iso_day()}")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Calorie goal not set"


def test_get_remaining_calories_rejects_malformed_date(auth_client):
    response = auth_client.get("/api/get-remaining-calories/not-a-date")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid date format"


# ---------------------------------------------------------------------------
# Bug 3 — meal names outside constants.ALL_MEAL_TYPES
# ---------------------------------------------------------------------------


def test_day_with_ad_hoc_snack_name_renders_after_meal_config_changes(auth_client):
    """A "Snack" row must not crash the day page when meals_per_day changes."""
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user.meals_per_day = 3
        food_id, portion_id = make_my_food(user.id, "Granola Bar", 400.0)
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=today(),
                meal_name="Snack",
                my_food_id=food_id,
                amount_grams=50,
                portion_id_fk=portion_id,
                serving_type="g",
            )
        )
        db.session.commit()

        # The user then switches to the 6-meal layout: "Snack" is in neither
        # MEAL_CONFIG[3] nor ALL_MEAL_TYPES.
        user.meals_per_day = 6
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    # The unknown meal stays visible as its own block, sorted after the
    # configured ones, and its own totals render.
    assert b'id="meal-snack"' in page.data
    assert b"Granola Bar" in page.data
    assert b"200.0kcal" in page.data
    # Configured meals still render as usual.
    assert b'id="meal-breakfast"' in page.data
    assert b'id="meal-snack-morning"' in page.data


def test_ad_hoc_meal_name_survives_move_and_still_renders(auth_client):
    """Moving an entry to an unconfigured meal name must stay renderable."""
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user.meals_per_day = 3
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=today(),
                meal_name="Breakfast",
                amount_grams=80,
                fdc_id=12345,
            )
        )
        db.session.commit()
        log_id = DailyLog.query.filter_by(user_id=user.id).first().id

    response = auth_client.post(
        "/diary/move_entry",
        data={
            "log_id": log_id,
            "target_date": iso_day(),
            "target_meal_name": "Brunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Diary entry moved successfully." in response.data

    page = auth_client.get(f"/diary/{iso_day()}")
    assert page.status_code == 200
    assert b'id="meal-brunch"' in page.data


# ---------------------------------------------------------------------------
# Diary GET
# ---------------------------------------------------------------------------


def test_diary_renders_own_day_with_all_food_sources(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")

        db.session.add(Food(fdc_id=12345, description="USDA Apple"))
        db.session.add(Nutrient(id=1008, name="Energy", unit_name="kcal"))
        db.session.add(Nutrient(id=1003, name="Protein", unit_name="g"))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1008, amount=100.0))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1003, amount=10.0))
        usda_portion = UnifiedPortion(
            fdc_id=12345,
            gram_weight=10.0,
            amount=1.0,
            measure_unit_description="slice",
            seq_num=1,
        )

        my_food_id, _ = make_my_food(user_id, "House Bread", 300.0)
        soup_base_id, _ = make_my_food(user_id, "Soup Base", 100.0)

        recipe = Recipe(user_id=user_id, name="Test Soup")
        db.session.add(recipe)
        db.session.flush()
        db.session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                my_food_id=soup_base_id,
                amount_grams=100,
                seq_num=1,
            )
        )
        recipe_portion = UnifiedPortion(
            recipe_id=recipe.id,
            gram_weight=1.0,
            amount=1.0,
            measure_unit_description="g",
            seq_num=1,
        )
        db.session.add_all([usda_portion, recipe_portion])
        db.session.flush()

        day = today()
        db.session.add_all(
            [
                DailyLog(
                    user_id=user_id,
                    log_date=day,
                    meal_name="Breakfast",
                    fdc_id=12345,
                    amount_grams=50,
                    portion_id_fk=usda_portion.id,
                    serving_type="1 slice",
                ),
                DailyLog(
                    user_id=user_id,
                    log_date=day,
                    meal_name="Lunch",
                    my_food_id=my_food_id,
                    amount_grams=100,
                ),
                DailyLog(
                    user_id=user_id,
                    log_date=day,
                    meal_name="Dinner",
                    recipe_id=recipe.id,
                    amount_grams=200,
                    portion_id_fk=recipe_portion.id,
                ),
                DailyLog(
                    user_id=user_id,
                    log_date=day,
                    meal_name="Water",
                    amount_grams=500,
                ),
                ExerciseLog(
                    user_id=user_id,
                    log_date=day,
                    duration_minutes=45,
                    calories_burned=300,
                    manual_description="Rowing",
                ),
            ]
        )
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b"USDA Apple" in page.data
    assert b"House Bread" in page.data
    assert b"Test Soup" in page.data
    # 50 g apple @100/100 g = 50, 100 g bread @300/100 g = 300,
    # 200 g of a recipe whose 100 g of ingredients carry 100 kcal = 200.
    assert b"Consumed: 550.0 kcal" in page.data
    # 500 g of water rows are reported as the water total.
    assert b"(Total: 500 ml)" in page.data
    # Default 2000 kcal goal, 300 kcal burned by the exercise row.
    assert b"Goal: 2000.0 kcal" in page.data
    assert b"Remaining: 1750.0 kcal" in page.data


def test_diary_labels_orphaned_and_foreign_foods(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        foreign_food, _ = make_my_food(user_two.id, "User Two Cake", 450.0)
        orphan_food, _ = make_my_food(None, "Ghost Pudding", 120.0)
        db.session.add_all(
            [
                DailyLog(
                    user_id=user_one.id,
                    log_date=today(),
                    meal_name="Dinner",
                    my_food_id=foreign_food,
                    amount_grams=100,
                ),
                DailyLog(
                    user_id=user_one.id,
                    log_date=today(),
                    meal_name="Dinner",
                    my_food_id=orphan_food,
                    amount_grams=100,
                ),
            ]
        )
        db.session.commit()

    page = client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b"User Two Cake (from user_two)" in page.data
    assert b"Ghost Pudding (deleted)" in page.data


def test_diary_labels_food_of_a_hard_deleted_user(auth_client):
    """A dangling ``user_id`` (row survives account deletion) reads as deleted."""
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        ghost = User(username="ghost_owner", email="ghost_owner@example.com")
        ghost.set_password("password")
        db.session.add(ghost)
        db.session.commit()
        food_id, _ = make_my_food(ghost.id, "Ghost Cake", 300.0)
        db.session.delete(ghost)
        db.session.add(
            DailyLog(
                user_id=user_id,
                log_date=today(),
                meal_name="Dinner",
                my_food_id=food_id,
                amount_grams=100,
            )
        )
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b"Ghost Cake (deleted)" in page.data


def test_diary_default_view_yesterday(auth_client):
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user.diary_default_view = "yesterday"
        food_id, _ = make_my_food(user.id, "Yesterday Egg", 100.0)
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=today() - timedelta(days=1),
                meal_name="Breakfast",
                amount_grams=120,
                my_food_id=food_id,
            )
        )
        db.session.commit()

    page = auth_client.get("/diary/")

    assert page.status_code == 200
    assert b"Consumed: 120.0 kcal" in page.data


def test_diary_fasting_shows_only_water_block(auth_client):
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user.meals_per_day = 3
        db.session.add(
            FastingSession(
                user_id=user.id,
                planned_duration_hours=16,
                status="active",
            )
        )
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b'id="meal-water"' in page.data
    assert b'id="meal-breakfast"' not in page.data
    assert b'id="meal-dinner"' not in page.data


def test_diary_backfills_missing_standard_water_portions(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        partial = MyFood(
            user_id=user_id,
            description="Water",
            calories_per_100g=0,
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
        )
        db.session.add(partial)
        db.session.flush()
        db.session.add(
            UnifiedPortion(
                my_food_id=partial.id,
                gram_weight=1.0,
                amount=1.0,
                measure_unit_description="ml",
            )
        )
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    with auth_client.application.app_context():
        water = MyFood.query.filter_by(description="Water").first()
        units = {p.measure_unit_description for p in water.portions}
        assert {"ml", "fl oz", "cup", "L", "gal", "Glass of Water (8oz)"} <= units
        assert len(water.portions) == 13


def test_diary_creates_water_food_when_absent(auth_client):
    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    with auth_client.application.app_context():
        water = MyFood.query.filter_by(description="Water").first()
        assert water is not None
        assert len(water.portions) == 13


# ---------------------------------------------------------------------------
# Diary entry mutations + ownership (both directions)
# ---------------------------------------------------------------------------


def test_delete_log_owner_succeeds_and_other_user_is_rejected(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine = DailyLog(
            user_id=user_one.id,
            log_date=today(),
            meal_name="Lunch",
            amount_grams=100,
            fdc_id=12345,
        )
        theirs = DailyLog(
            user_id=user_two.id,
            log_date=today(),
            meal_name="Lunch",
            amount_grams=100,
            fdc_id=12345,
        )
        db.session.add_all([mine, theirs])
        db.session.commit()
        mine_id, theirs_id = mine.id, theirs.id

    # Owner: hard delete stashed for undo.
    response = client.post(f"/diary/log/{mine_id}/delete")
    assert response.status_code == 302
    assert f"/diary/{iso_day()}#meal-lunch" in response.headers["Location"]
    with client.application.app_context():
        assert db.session.get(DailyLog, mine_id) is None
    with client.session_transaction() as sess:
        assert sess["last_deleted"]["type"] == "dailylog"
        assert sess["last_deleted"]["undo_method"] == "reinsert"
        assert sess["last_deleted"]["data"]["id"] == mine_id

    # Non-owner: rejected, row untouched.
    response = client.post(f"/diary/log/{theirs_id}/delete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/diary/")
    assert (
        b"Entry not found or you do not have permission to delete it."
        in client.get("/diary/").data
    )
    with client.application.app_context():
        assert db.session.get(DailyLog, theirs_id) is not None


def test_update_entry_branches(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Update Me", 100.0)
        other_food_id, other_portion_id = make_my_food(user_id, "Other", 100.0)
        log = DailyLog(
            user_id=user_id,
            log_date=today(),
            meal_name="Dinner",
            my_food_id=food_id,
            amount_grams=10,
            portion_id_fk=portion_id,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    # Missing entry.
    response = auth_client.post(
        "/diary/update_entry/999999", data={"amount": 1, "portion_id": portion_id}
    )
    assert response.status_code == 302
    assert (
        b"Entry not found or you do not have permission to edit it."
        in auth_client.get("/diary/").data
    )

    # Unknown portion.
    response = auth_client.post(
        f"/diary/update_entry/{log_id}", data={"amount": 2, "portion_id": 424242}
    )
    assert response.status_code == 302
    assert b"Invalid portion selected." in auth_client.get("/diary/").data

    # Missing amount.
    response = auth_client.post(
        f"/diary/update_entry/{log_id}", data={"amount": "", "portion_id": portion_id}
    )
    assert response.status_code == 302
    assert b"Invalid data submitted." in auth_client.get("/diary/").data

    # Valid update keeps amount/portion/serving_type in lockstep.
    response = auth_client.post(
        f"/diary/update_entry/{log_id}",
        data={"amount": 3, "portion_id": other_portion_id},
    )
    assert f"/diary/{iso_day()}#meal-dinner" in response.headers["Location"]
    with auth_client.application.app_context():
        entry = db.session.get(DailyLog, log_id)
        assert entry.amount_grams == pytest.approx(3.0)
        assert entry.portion_id_fk == other_portion_id
        assert entry.serving_type.strip() == "g"


def test_move_and_copy_entry_reject_other_users_rows(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        theirs = DailyLog(
            user_id=user_two.id,
            log_date=today(),
            meal_name="Breakfast",
            amount_grams=100,
            fdc_id=12345,
        )
        mine = DailyLog(
            user_id=user_one.id,
            log_date=today(),
            meal_name="Breakfast",
            amount_grams=100,
            fdc_id=12345,
        )
        db.session.add_all([theirs, mine])
        db.session.commit()
        theirs_id, mine_id = theirs.id, mine.id

    response = client.post(
        "/diary/move_entry",
        data={
            "log_id": theirs_id,
            "target_date": iso_day(3),
            "target_meal_name": "Lunch",
        },
    )
    assert response.status_code == 302
    assert (
        b"Diary entry not found or you do not have permission to move it."
        in client.get("/diary/").data
    )
    with client.application.app_context():
        moved = db.session.get(DailyLog, theirs_id)
        assert moved.log_date == today()
        assert moved.meal_name == "Breakfast"

    response = client.post(
        "/diary/copy_entry",
        data={
            "log_id": theirs_id,
            "target_date": iso_day(3),
            "target_meal_name": "Lunch",
        },
    )
    assert response.status_code == 302
    assert (
        b"Diary entry not found or you do not have permission to copy it."
        in client.get("/diary/").data
    )
    with client.application.app_context():
        assert (
            DailyLog.query.filter_by(
                user_id=user_one.id, log_date=today() + timedelta(days=3)
            ).count()
            == 0
        )

    # Owner may still copy their own row forward (the "copy yesterday" flow).
    response = client.post(
        "/diary/copy_entry",
        data={
            "log_id": mine_id,
            "target_date": iso_day(1),
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )
    assert b"Diary entry copied successfully." in response.data
    with client.application.app_context():
        copied = DailyLog.query.filter_by(
            user_id=user_one.id, log_date=today() + timedelta(days=1)
        ).all()
        assert len(copied) == 1
        assert copied[0].meal_name == "Lunch"
        # The original keeps its own date.
        assert db.session.get(DailyLog, mine_id).log_date == today()


def test_move_and_copy_entry_report_bad_target_dates(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        log = DailyLog(
            user_id=user_id,
            log_date=today(),
            meal_name="Breakfast",
            amount_grams=100,
            fdc_id=12345,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    response = auth_client.post(
        "/diary/move_entry",
        data={
            "log_id": log_id,
            "target_date": "31-12-2024",
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )
    assert b"There was an error moving the diary entry." in response.data

    response = auth_client.post(
        "/diary/copy_entry",
        data={
            "log_id": log_id,
            "target_date": "yesterday",
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )
    assert b"There was an error copying the diary entry." in response.data

    with auth_client.application.app_context():
        entry = db.session.get(DailyLog, log_id)
        assert entry.log_date == today()


# ---------------------------------------------------------------------------
# Saved meals
# ---------------------------------------------------------------------------


def test_new_meal_and_rename(auth_client):
    response = auth_client.post("/my_meals/new")
    assert response.status_code == 302
    assert "/my_meals/edit/" in response.headers["Location"]
    meal_id = int(response.headers["Location"].rstrip("/").split("/")[-1])

    response = auth_client.post(
        f"/my_meals/edit/{meal_id}",
        data={"name": "Protein Bowl", "submit": "Update Name"},
        follow_redirects=True,
    )
    assert b"Meal name updated." in response.data
    with auth_client.application.app_context():
        assert db.session.get(MyMeal, meal_id).name == "Protein Bowl"


def test_edit_meal_renders_items_and_handles_broken_portions(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Meal Item", 250.0)
        meal = MyMeal(user_id=user_id, name="Saved Meal")
        db.session.add(meal)
        db.session.flush()

        zero_portion = UnifiedPortion(my_food_id=food_id, gram_weight=0.0, amount=0.0)
        db.session.add(zero_portion)
        db.session.flush()

        db.session.add_all(
            [
                # Good portion.
                MyMealItem(
                    my_meal_id=meal.id,
                    my_food_id=food_id,
                    amount_grams=60,
                    portion_id_fk=portion_id,
                ),
                # Portion with a zero gram weight.
                MyMealItem(
                    my_meal_id=meal.id,
                    my_food_id=food_id,
                    amount_grams=60,
                    portion_id_fk=zero_portion.id,
                ),
                # Portion that no longer exists.
                MyMealItem(
                    my_meal_id=meal.id,
                    my_food_id=food_id,
                    amount_grams=60,
                    portion_id_fk=987654,
                ),
                # USDA item.
                MyMealItem(
                    my_meal_id=meal.id, fdc_id=99999, amount_grams=30, serving_type="g"
                ),
            ]
        )
        db.session.commit()
        meal_id = meal.id

    page = auth_client.get(f"/my_meals/edit/{meal_id}")

    assert page.status_code == 200
    assert b"Saved Meal" in page.data
    assert b"Meal Item" in page.data


def test_edit_meal_rejects_other_users_meal(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        meal = MyMeal(user_id=user_two.id, name="User Two Meal")
        db.session.add(meal)
        db.session.commit()
        meal_id = meal.id

    response = client.get(f"/my_meals/edit/{meal_id}", follow_redirects=True)

    assert b"Meal not found or you do not have permission to edit it." in response.data
    with client.application.app_context():
        assert db.session.get(MyMeal, meal_id).name == "User Two Meal"


def test_delete_meal_ownership_both_ways(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine = MyMeal(user_id=user_one.id, name="Mine")
        theirs = MyMeal(user_id=user_two.id, name="Theirs")
        db.session.add_all([mine, theirs])
        db.session.commit()
        mine_id, theirs_id = mine.id, theirs.id

    response = client.post(f"/my_meals/{theirs_id}/delete", follow_redirects=True)
    assert (
        b"Meal not found or you do not have permission to delete it." in response.data
    )
    with client.application.app_context():
        assert db.session.get(MyMeal, theirs_id).user_id == user_two.id

    response = client.post(f"/my_meals/{mine_id}/delete", follow_redirects=True)
    assert b"Meal deleted." in response.data
    with client.application.app_context():
        assert db.session.get(MyMeal, mine_id).user_id is None
    with client.session_transaction() as sess:
        assert sess["last_deleted"]["undo_method"] == "reassign_owner"
        assert sess["last_deleted"]["data"]["original_user_id"] == user_one.id


def test_delete_meal_item_ownership_both_ways(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine = MyMeal(user_id=user_one.id, name="Mine")
        theirs = MyMeal(user_id=user_two.id, name="Theirs")
        db.session.add_all([mine, theirs])
        db.session.flush()
        my_item = MyMealItem(my_meal_id=mine.id, amount_grams=50, fdc_id=12345)
        their_item = MyMealItem(my_meal_id=theirs.id, amount_grams=50, fdc_id=12345)
        stranger_item = MyMealItem(my_meal_id=mine.id, amount_grams=50, fdc_id=12345)
        db.session.add_all([my_item, their_item, stranger_item])
        db.session.commit()
        my_item_id = my_item.id
        their_item_id = their_item.id
        stranger_item_id = stranger_item.id
        my_meal_id = mine.id

    # Item that belongs to somebody else's meal.
    response = client.post(
        f"/my_meals/{user_two.id}/delete_item/{their_item_id}", follow_redirects=True
    )
    assert (
        b"Item not found or you do not have permission to delete it." in response.data
    )

    # Own meal but the item lives in a different meal.
    response = client.post(
        f"/my_meals/{my_meal_id}/delete_item/{their_item_id}", follow_redirects=True
    )
    assert (
        b"Item not found or you do not have permission to delete it." in response.data
    )

    # Own item: deleted and stashed for undo.
    response = client.post(
        f"/my_meals/{user_one.id}/delete_item/{my_item_id}", follow_redirects=True
    )
    assert b"Meal item deleted." in response.data
    with client.application.app_context():
        assert db.session.get(MyMealItem, my_item_id) is None
        assert db.session.get(MyMealItem, stranger_item_id) is not None
    with client.session_transaction() as sess:
        assert sess["last_deleted"]["type"] == "mymealitem"


def test_copy_meal_ownership_matrix(auth_client_two_users, app_with_db):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        mine = MyMeal(user_id=user_one.id, name="Own Meal")
        theirs = MyMeal(user_id=user_two.id, name="Stranger Meal")
        db.session.add_all([mine, theirs])
        db.session.flush()
        db.session.add(MyMealItem(my_meal_id=mine.id, amount_grams=40, fdc_id=12345))
        db.session.add(MyMealItem(my_meal_id=theirs.id, amount_grams=40, fdc_id=12345))
        db.session.commit()
        mine_id, theirs_id = mine.id, theirs.id

    # Stranger's meal is refused.
    response = client.post(f"/my_meals/{theirs_id}/copy", follow_redirects=True)
    assert b"You can only copy meals from your friends." in response.data
    with client.application.app_context():
        assert MyMeal.query.filter_by(user_id=user_one.id).count() == 1

    # Own meal is cloned with its items.
    response = client.post(f"/my_meals/{mine_id}/copy", follow_redirects=True)
    assert b"to your meals." in response.data
    with client.application.app_context():
        clone = MyMeal.query.filter_by(
            user_id=user_one.id, name="Own Meal (Copy)"
        ).first()
        assert clone is not None
        assert len(clone.items) == 1
        assert clone.items[0].amount_grams == pytest.approx(40.0)


def test_copy_friend_meal_is_allowed(auth_client_with_friendship):
    client, me, friend = auth_client_with_friendship

    with client.application.app_context():
        meal = MyMeal(user_id=friend.id, name="Friend Meal")
        db.session.add(meal)
        db.session.flush()
        db.session.add(MyMealItem(my_meal_id=meal.id, amount_grams=25, fdc_id=12345))
        db.session.commit()
        meal_id = meal.id

    response = client.post(f"/my_meals/{meal_id}/copy", follow_redirects=True)

    assert b"to your meals." in response.data
    with client.application.app_context():
        clone = MyMeal.query.filter_by(user_id=me.id).first()
        assert clone is not None
        assert clone.name == "Friend Meal (Copy)"


def test_save_meal_and_edit_branches(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Saved Source", 120.0)
        db.session.add(
            DailyLog(
                user_id=user_id,
                log_date=today(),
                meal_name="Breakfast",
                my_food_id=food_id,
                amount_grams=90,
                portion_id_fk=portion_id,
                serving_type="g",
            )
        )
        db.session.commit()

    # Invalid payload.
    response = auth_client.post(
        "/diary/save_meal_and_edit", data={}, follow_redirects=True
    )
    assert b"Invalid data." in response.data

    # Empty meal.
    response = auth_client.post(
        "/diary/save_meal_and_edit",
        data={"log_date": iso_day(), "meal_name": "Dinner"},
    )
    assert response.status_code == 302
    assert f"/diary/{iso_day()}#meal-dinner" in response.headers["Location"]
    assert b"There are no items in Dinner to save." in auth_client.get("/diary/").data

    # Happy path.
    response = auth_client.post(
        "/diary/save_meal_and_edit",
        data={"log_date": iso_day(), "meal_name": "Breakfast"},
    )
    assert response.status_code == 302
    assert "/my_meals/edit/" in response.headers["Location"]
    with auth_client.application.app_context():
        meal = MyMeal.query.filter(
            MyMeal.user_id == user_id,
            MyMeal.name.startswith("New Meal from Breakfast"),
        ).first()
        assert meal is not None
        assert len(meal.items) == 1
        assert meal.items[0].portion_id_fk == portion_id
        assert meal.items[0].amount_grams == pytest.approx(90.0)


def test_save_meal_as_recipe_branches(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Recipe Source", 80.0)
        db.session.add(
            DailyLog(
                user_id=user_id,
                log_date=today(),
                meal_name="Lunch",
                my_food_id=food_id,
                amount_grams=200,
                portion_id_fk=portion_id,
                serving_type="g",
            )
        )
        db.session.commit()

    response = auth_client.post(
        "/diary/save_meal_as_recipe", data={}, follow_redirects=True
    )
    assert b"Invalid data." in response.data

    response = auth_client.post(
        "/diary/save_meal_as_recipe",
        data={"log_date": iso_day(), "meal_name": "Dinner"},
    )
    assert f"/diary/{iso_day()}#meal-dinner" in response.headers["Location"]
    assert (
        b"There are no items in Dinner to save as a recipe."
        in auth_client.get("/diary/").data
    )

    response = auth_client.post(
        "/diary/save_meal_as_recipe",
        data={"log_date": iso_day(), "meal_name": "Lunch"},
    )
    assert response.status_code == 302
    assert "/recipes/" in response.headers["Location"]
    with auth_client.application.app_context():
        recipe = Recipe.query.filter(
            Recipe.user_id == user_id,
            Recipe.name.startswith("Recipe from Lunch"),
        ).first()
        assert recipe is not None
        assert len(recipe.ingredients) == 1
        ingredient = recipe.ingredients[0]
        assert ingredient.amount_grams == pytest.approx(200.0)
        assert ingredient.seq_num == 1
        assert recipe.calories_per_100g == pytest.approx(80.0)
        assert any(p.gram_weight == 1.0 for p in recipe.portions)


def test_update_meal_item_branches(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Item Food", 200.0)
        meal = MyMeal(user_id=user_id, name="Items")
        db.session.add(meal)
        db.session.flush()
        item = MyMealItem(
            my_meal_id=meal.id,
            my_food_id=food_id,
            amount_grams=10,
            portion_id_fk=portion_id,
        )
        db.session.add(item)
        db.session.commit()
        meal_id, item_id = meal.id, item.id

    response = auth_client.post(
        "/my_meals/update_item/999999", data={"quantity": 2, "portion_id": portion_id}
    )
    assert response.status_code == 302
    assert (
        b"Item not found or you do not have permission to edit it."
        in auth_client.get("/my_meals").data
    )

    response = auth_client.post(f"/my_meals/update_item/{item_id}", data={})
    assert response.status_code == 302
    assert f"/my_meals/edit/{meal_id}" in response.headers["Location"]
    assert b"Invalid data submitted." in auth_client.get("/my_meals").data

    response = auth_client.post(
        f"/my_meals/update_item/{item_id}",
        data={"quantity": 2, "portion_id": 555555},
        follow_redirects=True,
    )
    assert b"Invalid portion selected." in response.data

    response = auth_client.post(
        f"/my_meals/update_item/{item_id}",
        data={"quantity": 4, "portion_id": portion_id},
    )
    assert f"/my_meals/edit/{meal_id}" in response.headers["Location"]
    with auth_client.application.app_context():
        entry = db.session.get(MyMealItem, item_id)
        assert entry.amount_grams == pytest.approx(4.0)
        assert entry.serving_type.strip() == "g"
        assert entry.portion_id_fk == portion_id


def test_update_meal_item_rejects_other_users_item(auth_client_two_users):
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        their_meal = MyMeal(user_id=user_two.id, name="Theirs")
        db.session.add(their_meal)
        db.session.flush()
        their_item = MyMealItem(my_meal_id=their_meal.id, amount_grams=15, fdc_id=12345)
        db.session.add(their_item)
        db.session.commit()
        their_item_id = their_item.id

    response = client.post(
        f"/my_meals/update_item/{their_item_id}",
        data={"quantity": 9, "portion_id": 1},
    )

    assert response.status_code == 302
    assert (
        b"Item not found or you do not have permission to edit it."
        in client.get("/my_meals").data
    )
    with client.application.app_context():
        assert db.session.get(MyMealItem, their_item_id).amount_grams == pytest.approx(
            15.0
        )


# ---------------------------------------------------------------------------
# my_meals listing
# ---------------------------------------------------------------------------


def test_my_meals_lists_user_meals_with_items(auth_client):
    with auth_client.application.app_context():
        db.session.add(Food(fdc_id=12345, description="USDA Apple"))
        db.session.add(Nutrient(id=1008, name="Energy", unit_name="kcal"))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1008, amount=200.0))
        usda_portion = UnifiedPortion(fdc_id=12345, gram_weight=25.0, amount=1.0)
        db.session.add(usda_portion)

        user_id = user_id_of(auth_client, "testuser")
        food_id, portion_id = make_my_food(user_id, "Listed Item", 100.0)
        meal = MyMeal(user_id=user_id, name="Listed Meal")
        db.session.add(meal)
        db.session.flush()
        db.session.add_all(
            [
                MyMealItem(
                    my_meal_id=meal.id,
                    my_food_id=food_id,
                    amount_grams=50,
                    portion_id_fk=portion_id,
                ),
                MyMealItem(
                    my_meal_id=meal.id,
                    fdc_id=12345,
                    amount_grams=50,
                    portion_id_fk=usda_portion.id,
                ),
            ]
        )
        db.session.commit()

    page = auth_client.get("/my_meals")

    assert page.status_code == 200
    assert b"Listed Meal" in page.data
    assert b"Listed Item" in page.data
    assert b"USDA Apple" in page.data


def test_my_meals_paginates(auth_client):
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        meals = [MyMeal(user_id=user_id, name=f"Paged Meal {i}") for i in range(12)]
        db.session.add_all(meals)
        db.session.commit()

    first = auth_client.get("/my_meals")
    second = auth_client.get("/my_meals?page=2")
    beyond = auth_client.get("/my_meals?page=99")
    bad = auth_client.get("/my_meals?page=abc")

    assert b"Paged Meal 0" in first.data
    assert b"Paged Meal 5" in second.data
    assert b"Paged Meal 0" not in second.data
    assert beyond.status_code == 200
    assert bad.status_code == 200


def test_my_meals_friends_view(auth_client_with_friendship, app_with_db):
    client, me, friend = auth_client_with_friendship

    with client.application.app_context():
        food_id, _ = make_my_food(friend.id, "Friend Item", 100.0)
        meal = MyMeal(user_id=friend.id, name="Friend Saved Meal")
        db.session.add(meal)
        db.session.flush()
        db.session.add(
            MyMealItem(
                my_meal_id=meal.id,
                my_food_id=food_id,
                amount_grams=30,
                serving_type="g",
            )
        )
        db.session.commit()

    page = client.get("/my_meals?view=friends")

    assert page.status_code == 200
    assert b"Friend Saved Meal" in page.data


def test_my_meals_friends_view_without_friends(auth_client_with_user):
    client, user = auth_client_with_user

    with client.application.app_context():
        db.session.add(MyMeal(user_id=user.id, name="Own Private Meal"))
        db.session.commit()

    page = client.get("/my_meals?view=friends")

    assert page.status_code == 200
    assert b"No meals found from your friends." in page.data
    assert b"Own Private Meal" not in page.data


# ---------------------------------------------------------------------------
# Diary day navigation (prev/next + pagination-ish day stepping)
# ---------------------------------------------------------------------------


def test_diary_day_navigation_links(auth_client):
    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert f"/diary/{iso_day(-1)}".encode() in page.data
    assert f"/diary/{iso_day(1)}".encode() in page.data


def test_recipe_ingredient_row_is_displayed_with_recipe_totals(auth_client):
    """A diary row pointing at a recipe uses the recipe's rolled-up nutrition."""
    with auth_client.application.app_context():
        user_id = user_id_of(auth_client, "testuser")
        food_id, _ = make_my_food(user_id, "Ingredient Base", 100.0)
        recipe = Recipe(user_id=user_id, name="Derived Recipe", servings=1)
        db.session.add(recipe)
        db.session.flush()
        db.session.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                my_food_id=food_id,
                amount_grams=100,
                seq_num=1,
            )
        )
        db.session.add(
            UnifiedPortion(recipe_id=recipe.id, gram_weight=1.0, amount=1.0, seq_num=1)
        )
        db.session.flush()
        from opennourish.utils import update_recipe_nutrition

        update_recipe_nutrition(recipe)
        db.session.add(
            DailyLog(
                user_id=user_id,
                log_date=today(),
                meal_name="Dinner",
                recipe_id=recipe.id,
                amount_grams=150,
            )
        )
        db.session.commit()

    page = auth_client.get(f"/diary/{iso_day()}")

    assert page.status_code == 200
    assert b"Derived Recipe" in page.data
    assert b"Consumed: 150.0 kcal" in page.data
