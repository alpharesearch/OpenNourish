"""Coverage tests for the shared service helpers in ``opennourish/utils.py``.

The feature suites already drive the happy paths; these tests aim at the
defensive branches (mail failures, zero/None goals, invalid delete methods) and
at the projection stop conditions that no page currently reaches.
"""

from datetime import date, timedelta
from decimal import Decimal

from cryptography.fernet import Fernet, InvalidToken
from flask import session
from sqlalchemy import Column, Date, Integer, Numeric
from sqlalchemy.orm import declarative_base

import pytest
from constants import DEFAULT_MEAL_NAMES
from models import (
    db,
    CheckIn,
    DailyLog,
    MyFood,
    User,
    UserGoal,
)
from opennourish import mail
from opennourish.utils import (
    _serialize_model_for_session,
    calculate_bmr,
    calculate_intake_vs_goal_deviation,
    calculate_nutrient_density,
    calculate_weight_projection,
    convert_display_nutrients_to_100g,
    decrypt_value,
    encrypt_value,
    get_available_portions,
    calculate_nutrition_for_items,
    calculate_recipe_nutrition_per_100g,
    get_meal_based_nutrition,
    get_nutrients_for_display,
    get_standard_meal_names_for_user,
    update_recipe_nutrition,
    prepare_undo_and_delete,
    send_password_reset_email,
    send_verification_email,
)

TODAY = date(2024, 6, 15)


def test_serialize_model_for_session_handles_decimal_and_date():
    """Decimal and date columns are converted into JSON-serialisable scalars."""
    Base = declarative_base()

    class DecimalProbe(Base):
        __tablename__ = "coverage_decimal_probe"
        id = Column(Integer, primary_key=True)
        amount = Column(Numeric(10, 2))
        checked_on = Column(Date)
        label = Column(Integer)

    payload = _serialize_model_for_session(
        DecimalProbe(
            id=7, amount=Decimal("12.34"), checked_on=date(2024, 5, 1), label=None
        )
    )

    assert payload == {
        "id": 7,
        "amount": 12.34,
        "checked_on": "2024-05-01",
        "label": None,
    }


def test_encrypt_value_round_trip_and_wrong_key():
    """encrypt_value/decrypt_value are the Fernet pair behind MAIL_PASSWORD."""
    key = Fernet.generate_key().decode()
    encrypted = encrypt_value("hunter2", key)

    assert encrypted != "hunter2"
    assert decrypt_value(encrypted, key) == "hunter2"

    other_key = Fernet.generate_key().decode()
    try:
        decrypt_value(encrypted, other_key)
    except InvalidToken:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("decrypt_value accepted a foreign key")


def test_send_password_reset_email_swallows_transport_errors(app_with_db, mocker):
    """A failing SMTP round trip is logged, never raised into the request."""
    user = User(username="resetme", email="resetme@example.com")
    send = mocker.patch.object(mail, "send_message", side_effect=OSError("smtp down"))

    with app_with_db.test_request_context():
        db.session.add(user)
        db.session.commit()
        send_password_reset_email(user, "abc123")

    assert send.call_count == 1


def test_send_verification_email_swallows_transport_errors(app_with_db, mocker):
    """A failing verification mail is logged, never raised into the request."""
    user = User(username="verifyme", email="verifyme@example.com")
    send = mocker.patch.object(mail, "send_message", side_effect=OSError("smtp down"))

    with app_with_db.test_request_context():
        db.session.add(user)
        db.session.commit()
        send_verification_email(user, "abc123")

    assert send.call_count == 1


def test_send_email_helpers_report_success(app_with_db, mocker):
    """The success paths log the recipient address instead of raising."""

    async def _sent(_msg):
        return None

    mocker.patch.object(mail, "send_message", side_effect=_sent)

    with app_with_db.test_request_context():
        reset_user = User(username="okmail", email="okmail@example.com")
        verify_user = User(username="okverify", email="okverify@example.com")
        db.session.add_all([reset_user, verify_user])
        db.session.commit()

        send_password_reset_email(reset_user, "tok")
        send_verification_email(verify_user, "tok")


def test_calculate_nutrient_density_without_weight(app_with_db):
    """Zero logged grams returns zeroes instead of dividing by zero."""
    zeroed = {"overall": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    with app_with_db.app_context():
        user = User(username="density", email="density@example.com")
        db.session.add(user)
        db.session.commit()
        logs = [
            DailyLog(
                user_id=user.id, log_date=TODAY, meal_name="Breakfast", amount_grams=0
            )
        ]

        assert calculate_nutrient_density(logs) == zeroed
        assert calculate_nutrient_density([]) == zeroed


def test_get_meal_based_nutrition_forwards_added_sugars(app_with_db, monkeypatch):
    """A totals dict carrying added_sugars is forwarded, not defaulted to 0."""
    from opennourish import utils as utils_module

    full_totals = {
        "calories": 400,
        "protein": 20,
        "carbs": 40,
        "fat": 15,
        "saturated_fat": 3,
        "trans_fat": 0.5,
        "cholesterol": 30,
        "sodium": 200,
        "fiber": 6,
        "sugars": 8,
        "added_sugars": 4,
        "vitamin_d": 1,
        "calcium": 90,
        "iron": 2,
        "potassium": 300,
        "net_carbs": 34,
    }
    monkeypatch.setattr(
        utils_module, "calculate_nutrition_for_items", lambda _logs: full_totals
    )

    with app_with_db.app_context():
        user = User(username="meals", email="meals@example.com")
        db.session.add(user)
        db.session.commit()
        logs = [
            DailyLog(
                user_id=user.id, log_date=TODAY, meal_name="Lunch", amount_grams=250
            ),
            DailyLog(user_id=user.id, log_date=TODAY, meal_name=None, amount_grams=50),
        ]
        result = get_meal_based_nutrition(logs)

    assert result["Lunch"]["added_sugars"] == 4
    assert result["Lunch"]["grams"] == 250
    # Logs without a meal name are grouped under "Other".
    assert result["Other"]["added_sugars"] == 4
    assert result["Other"]["grams"] == 50


def test_get_meal_based_nutrition_defaults_added_sugars(app_with_db):
    """The shipped totals dict has no added_sugars key, so it defaults to 0.0."""
    with app_with_db.app_context():
        user = User(username="meals2", email="meals2@example.com")
        db.session.add(user)
        db.session.commit()
        logs = [
            DailyLog(
                user_id=user.id, log_date=TODAY, meal_name="Dinner", amount_grams=100
            )
        ]
        result = get_meal_based_nutrition(logs)

    assert result["Dinner"]["added_sugars"] == 0.0


def test_calculate_intake_vs_goal_deviation_with_empty_goals(app_with_db):
    """Macros with a zero/None goal report a 0.0 deviation instead of dividing."""
    zeroes = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    with app_with_db.app_context():
        user = User(username="deviation", email="deviation@example.com")
        db.session.add(user)
        db.session.commit()
        # SQLAlchemy applies the column defaults for explicit None values, so the
        # falsy-goal branch has to be provoked with zeroes.
        goal = UserGoal(user_id=user.id, calories=0, protein=0, carbs=0, fat=0)
        db.session.add(goal)
        db.session.commit()
        logs = [DailyLog(user_id=user.id, log_date=TODAY, amount_grams=100)]

        assert calculate_intake_vs_goal_deviation(goal, logs) == zeroes
        assert calculate_intake_vs_goal_deviation(None, logs) == zeroes
        assert calculate_intake_vs_goal_deviation(goal, []) == zeroes


def test_calculate_intake_vs_goal_deviation_reports_real_deviations(app_with_db):
    """A real goal row yields a signed percentage per macro."""
    with app_with_db.app_context():
        user = User(username="deviation2", email="deviation2@example.com")
        db.session.add(user)
        goal = MyFood(
            user_id=user.id,
            description="Fatty",
            calories_per_100g=800.0,
            protein_per_100g=30.0,
            carbs_per_100g=10.0,
            fat_per_100g=60.0,
        )
        db.session.add(goal)
        db.session.commit()
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=TODAY,
                my_food_id=goal.id,
                amount_grams=100,
            )
        )
        db.session.commit()
        user_goal = UserGoal(
            user_id=user.id, calories=400, protein=15, carbs=20, fat=30
        )
        db.session.add(user_goal)
        db.session.commit()

        deviations = calculate_intake_vs_goal_deviation(
            user_goal, DailyLog.query.filter_by(user_id=user.id).all()
        )

    assert deviations["calories"] == 100.0
    assert deviations["protein"] == 100.0
    assert deviations["carbs"] == -50.0
    assert deviations["fat"] == 100.0


def test_calculate_intake_vs_goal_deviation_swallows_errors(app_with_db):
    """A broken goal object degrades to zeroes rather than a 500."""

    class ExplodingGoals:
        def __getattr__(self, _name):
            raise RuntimeError("goal row is unusable")

    with app_with_db.app_context():
        user = User(username="boom", email="boom@example.com")
        db.session.add(user)
        db.session.commit()
        logs = [DailyLog(user_id=user.id, log_date=TODAY, amount_grams=100)]

        assert calculate_intake_vs_goal_deviation(ExplodingGoals(), logs) == {
            "calories": 0.0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
        }


def test_calculate_bmr_rejects_unknown_gender():
    """Only Male/Female have a Mifflin-St Jeor constant."""
    assert calculate_bmr(70, 175, 30, "Other") == (None, None)
    assert calculate_bmr(70, 175, 30, None) == (None, None)

    bmr, formula = calculate_bmr(70, 175, 30, "Male", body_fat_percentage=15)
    assert formula == "Katch-McArdle"
    assert bmr > 0


def test_get_available_portions_without_relationship():
    """Objects without a portions relationship return an empty list."""

    class NoPortions:
        pass

    assert get_available_portions(None) == []
    assert get_available_portions(NoPortions()) == []


def test_get_standard_meal_names_without_user():
    """A missing user falls back to the six-meal default."""
    assert get_standard_meal_names_for_user(None) == DEFAULT_MEAL_NAMES
    assert get_standard_meal_names_for_user(object()) == DEFAULT_MEAL_NAMES


def _seed_projection_user(
    app,
    suffix,
    gender="Female",
    weight_kg=70.0,
    weight_goal_kg=65.0,
    calories=2000,
    calories_burned_goal_weekly=0,
    log_grams=None,
    null_calories=False,
    null_weekly_burn=False,
):
    """Create the user plus the check-in/goal rows the projection needs."""
    user = User(
        username=f"proj{suffix}",
        email=f"proj{suffix}@example.com",
        age=30,
        height_cm=175,
        gender=gender,
    )
    db.session.add(user)
    db.session.flush()

    db.session.add(
        UserGoal(
            user_id=user.id,
            calories=calories,
            calories_burned_goal_weekly=calories_burned_goal_weekly,
            weight_goal_kg=weight_goal_kg,
        )
    )
    db.session.commit()
    db.session.add(
        CheckIn(user_id=user.id, checkin_date=app_config_today(), weight_kg=weight_kg)
    )
    if log_grams is not None:
        food = MyFood(
            user_id=user.id,
            description=f"Lean logs {suffix}",
            calories_per_100g=4.0,
            protein_per_100g=1.0,
        )
        db.session.add(food)
        db.session.flush()
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=app_config_today() - timedelta(days=1),
                meal_name="Dinner",
                my_food_id=food.id,
                amount_grams=log_grams,
            )
        )
    db.session.commit()
    # UserGoal columns have defaults, so a NULL has to be written explicitly.
    goal = UserGoal.query.filter_by(user_id=user.id).one()
    if null_calories:
        goal.calories = None
    if null_weekly_burn:
        goal.calories_burned_goal_weekly = None
    if null_calories or null_weekly_burn:
        db.session.commit()
    return user


def app_config_today():
    """The projection anchors on the user-local today; UTC keeps it deterministic."""
    from opennourish.time_utils import get_user_today

    return get_user_today("UTC")


def test_weight_projection_stops_without_missing_essential_data(app_with_db):
    """Without a check-in or a goal weight there is nothing to project."""
    with app_with_db.app_context():
        bare = User(username="proj0", email="proj0@example.com")
        db.session.add(bare)
        db.session.commit()

        assert calculate_weight_projection(bare) == ([], [], False, False)

        user = _seed_projection_user(app_with_db, 10, weight_goal_kg=None)
        assert calculate_weight_projection(user) == ([], [], False, False)


def test_weight_projection_stops_without_bmr(app_with_db):
    """No usable gender means no BMR, so no projection is returned."""
    with app_with_db.app_context():
        user = _seed_projection_user(app_with_db, 11, gender="Other")

        assert calculate_weight_projection(user) == ([], [], False, False)


def test_weight_projection_without_intake_baseline(app_with_db):
    """No calorie intake data at all returns the short 3-tuple guard."""
    with app_with_db.app_context():
        user = _seed_projection_user(app_with_db, 13, null_calories=True)

        assert calculate_weight_projection(user) == ([], [], False)


def test_weight_projection_without_exercise_baseline(app_with_db):
    """No exercise logs and no weekly burn goal are treated as zero expenditure."""
    with app_with_db.app_context():
        user = _seed_projection_user(
            app_with_db,
            14,
            weight_kg=70.0,
            weight_goal_kg=69.0,
            null_weekly_burn=True,
            log_grams=100,
        )

        dates, weights, trending_away, at_goal = calculate_weight_projection(user)

        assert dates and weights[0] == 70.0
        assert weights[-1] <= 69.0  # the projection stops at the goal weight
        assert trending_away is False
        assert at_goal is False


def test_weight_projection_uses_goal_fallbacks_without_logs(app_with_db):
    """Intake falls back to the calorie goal, burn to the weekly goal / 7."""
    with app_with_db.app_context():
        user = _seed_projection_user(
            app_with_db,
            15,
            weight_kg=80.0,
            weight_goal_kg=82.0,
            calories=9000,
            calories_burned_goal_weekly=700,
        )

        dates, weights, trending_away, _at_goal = calculate_weight_projection(user)

        assert trending_away is False
        assert len(dates) == len(weights)
        assert weights[-1] > weights[0]


def test_weight_projection_flags_trending_away(app_with_db):
    """Gaining against a lower goal is reported as trending away."""
    with app_with_db.app_context():
        user = _seed_projection_user(
            app_with_db,
            16,
            weight_kg=80.0,
            weight_goal_kg=79.0,
            calories=9000,
            calories_burned_goal_weekly=0,
        )

        _dates, _weights, trending_away, _at_goal = calculate_weight_projection(user)

        assert trending_away is True


def test_weight_projection_flags_at_goal_and_maintaining(app_with_db):
    """A maintainer within half a kilo of the goal projects a single day."""
    with app_with_db.app_context():
        user = User(
            username="proj17",
            email="proj17@example.com",
            age=30,
            height_cm=175,
            gender="Female",
        )
        db.session.add(user)
        db.session.flush()
        checkin_weight = 70.0
        db.session.add(
            CheckIn(user_id=user.id, checkin_date=app_config_today(), weight_kg=70.0)
        )
        db.session.commit()
        bmr = round(
            10 * checkin_weight + 6.25 * 175 - 5 * 30 - 161
        )  # 1483 kcal, the Mifflin-St Jeor value
        db.session.add(
            UserGoal(
                user_id=user.id,
                calories=bmr,
                calories_burned_goal_weekly=0,
                weight_goal_kg=70.2,
            )
        )
        db.session.commit()

        dates, weights, trending_away, at_goal = calculate_weight_projection(user)

        assert at_goal is True
        assert trending_away is False
        assert len(dates) == 1


def test_convert_display_nutrients_to_100g_coerces_junk_values():
    """Non-numeric and missing display values become 0.0 before scaling."""
    portion = type("P", (), {"gram_weight": 50.0})()
    result = convert_display_nutrients_to_100g(
        {"calories": "not-a-number", "protein": None, "carbs": 10}, portion
    )

    assert result == {"calories": 0.0, "protein": 0.0, "carbs": 20.0}

    assert convert_display_nutrients_to_100g({"calories": 12}, None) == {
        "calories": 12.0
    }


def test_prepare_undo_and_delete_hard_delete_stores_reinsert_payload(app_with_db):
    """The hard mode serialises the row so /undo can reinsert it."""
    with app_with_db.test_request_context():
        user = User(username="undoer", email="undoer@example.com")
        db.session.add(user)
        db.session.commit()
        check_in = CheckIn(
            user_id=user.id, checkin_date=app_config_today(), weight_kg=71.5
        )
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

        prepare_undo_and_delete(
            check_in,
            "check_in",
            {"endpoint": "tracking.progress", "params": {}},
            success_message="Your check-in has been deleted.",
        )

        stored = dict(session["last_deleted"])
        flashes = list(session.get("_flashes", ()))

    assert stored["undo_method"] == "reinsert"
    assert stored["type"] == "check_in"
    assert stored["redirect_info"] == {"endpoint": "tracking.progress", "params": {}}
    assert stored["data"]["id"] == check_in_id
    assert stored["data"]["weight_kg"] == 71.5
    assert any("Undo" in str(message) for _category, message in flashes)
    with app_with_db.app_context():
        assert db.session.get(CheckIn, check_in_id) is None


def test_prepare_undo_and_delete_anonymize_stores_reassignment(app_with_db):
    """The anonymize mode keeps the row and remembers its original owner."""
    with app_with_db.test_request_context():
        user = User(username="owner", email="owner@example.com")
        db.session.add(user)
        db.session.commit()
        my_food = MyFood(user_id=user.id, description="Anonymize me")
        db.session.add(my_food)
        db.session.commit()
        my_food_id, user_id = my_food.id, user.id

        prepare_undo_and_delete(
            my_food,
            "my_food",
            {"endpoint": "my_foods.my_foods", "params": {}},
            delete_method="anonymize",
            success_message="Deleted.",
        )

        stored = dict(session["last_deleted"])

    assert stored["undo_method"] == "reassign_owner"
    assert stored["data"] == {"item_id": my_food_id, "original_user_id": user_id}
    with app_with_db.app_context():
        assert db.session.get(MyFood, my_food_id).user_id is None


def test_prepare_undo_and_delete_rejects_unknown_method(app_with_db):
    """An unexpected delete_method is a programming error, not a silent no-op."""
    with app_with_db.test_request_context():
        user = User(username="weird", email="weird@example.com")
        db.session.add(user)
        db.session.commit()
        check_in = CheckIn(
            user_id=user.id, checkin_date=app_config_today(), weight_kg=70.0
        )
        db.session.add(check_in)
        db.session.commit()

        try:
            prepare_undo_and_delete(
                check_in, "check_in", {"endpoint": "tracking.progress"}, "implode"
            )
        except ValueError as exc:
            assert "Unknown delete_method: implode" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("prepare_undo_and_delete accepted a bad method")


def test_calculate_nutrition_for_usda_items(app_with_db):
    """464-488: USDA logs are resolved through the pinned nutrient ids."""
    from constants import CORE_NUTRIENT_IDS
    from models import Food, FoodNutrient

    with app_with_db.app_context():
        user = User(username="usda", email="usda@example.com")
        food = Food(fdc_id=99001, description="Test oats")
        db.session.add(user)
        db.session.add(food)
        db.session.add_all(
            [
                FoodNutrient(
                    fdc_id=99001,
                    nutrient_id=CORE_NUTRIENT_IDS["calories"],
                    amount=380.0,
                ),
                FoodNutrient(
                    fdc_id=99001, nutrient_id=CORE_NUTRIENT_IDS["protein"], amount=13.0
                ),
                FoodNutrient(fdc_id=99001, nutrient_id=9999, amount=1.0),
            ]
        )
        db.session.commit()
        logs = [
            DailyLog(user_id=user.id, log_date=TODAY, fdc_id=99001, amount_grams=50)
        ]

        totals = calculate_nutrition_for_items(logs)

    assert totals["calories"] == pytest.approx(190.0)
    assert totals["protein"] == pytest.approx(6.5)
    # Net carbs are floored at zero even when fiber exceeds the carb count.
    assert totals["net_carbs"] == 0


def test_recipe_nutrition_helpers(app_with_db):
    """518-551, 577-670: the recipe rollups scale by final weight and tolerate empties."""
    from models import Recipe, RecipeIngredient

    with app_with_db.app_context():
        user = User(username="cook", email="cook@example.com")
        db.session.add(user)
        db.session.commit()

        stock = MyFood(
            user_id=user.id,
            description="Stock",
            calories_per_100g=40.0,
            protein_per_100g=2.0,
            carbs_per_100g=3.0,
            fat_per_100g=1.0,
            fiber_per_100g=0.0,
        )
        recipe = Recipe(user_id=user.id, name="Chilli", final_weight_grams=1000.0)
        db.session.add(stock)
        db.session.add(recipe)
        db.session.flush()

        db.session.add_all(
            [
                RecipeIngredient(
                    recipe_id=recipe.id, my_food_id=stock.id, amount_grams=500
                ),
                # A bare ingredient carries only its parent recipe_id, which
                # calculate_nutrition_for_items reads as a nested-recipe link:
                # the recursion guard stops the descent, and the parent's own
                # ingredients are folded in a second time at 500/1000 scale.
                RecipeIngredient(recipe_id=recipe.id, amount_grams=500),
            ]
        )
        db.session.commit()

        per_100g = calculate_recipe_nutrition_per_100g(recipe)
        update_recipe_nutrition(recipe)
        db.session.commit()

        # 200 kcal from the stock plus 100 kcal of re-counted parent, per 1000 g.
        assert per_100g["calories"] == pytest.approx(30.0)
        assert per_100g["net_carbs"] == pytest.approx(
            max(0, per_100g["carbs"] - per_100g["fiber"])
        )
        assert recipe.calories_per_100g == pytest.approx(30.0)
        assert recipe.protein_per_100g == pytest.approx(1.5)

        empty_recipe = Recipe(user_id=user.id, name="Nothing yet", final_weight_grams=0)
        db.session.add(empty_recipe)
        db.session.commit()

        assert calculate_recipe_nutrition_per_100g(empty_recipe) == {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "fiber": 0,
            "net_carbs": 0,
        }
        update_recipe_nutrition(empty_recipe)
        assert empty_recipe.calories_per_100g == 0.0
        assert empty_recipe.potassium_mg_per_100g == 0.0


def test_get_nutrients_for_display_scales_by_portion(app_with_db):
    """858-888: a portion of 1 g or none means the values stay per 100 g."""
    from models import UnifiedPortion

    with app_with_db.app_context():
        user = User(username="portion", email="portion@example.com")
        db.session.add(user)
        db.session.commit()
        my_food = MyFood(
            user_id=user.id,
            description="Yoghurt",
            calories_per_100g=60.0,
            protein_per_100g=10.0,
            carbs_per_100g=None,
        )
        db.session.add(my_food)
        db.session.commit()

        base = get_nutrients_for_display(my_food, None)
        one_gram = get_nutrients_for_display(
            my_food, UnifiedPortion(gram_weight=1.0, my_food_id=my_food.id)
        )
        half = get_nutrients_for_display(
            my_food, UnifiedPortion(gram_weight=50.0, my_food_id=my_food.id)
        )

    assert base["calories"] == 60.0
    assert base["carbs"] == 0  # a NULL column is treated as zero
    assert one_gram["calories"] == 60.0
    assert half["calories"] == 30.0
    assert half["protein"] == 5.0
