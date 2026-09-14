"""Coverage tests for ``opennourish/main/routes.py`` and ``opennourish/tracking``.

The tracking suite in ``tests/test_tracking.py`` covers the metric happy path;
the tests here add the US/customary branch of the check-in form, the permission
branch of the delete route, the analytics page with and without data, and the
index redirects of the main blueprint.
"""

from datetime import date, timedelta

import pytest
from flask import url_for

from models import (
    CheckIn,
    DailyLog,
    ExerciseLog,
    FoodCategory,
    MyFood,
    Recipe,
    User,
    UserGoal,
    db,
)
from opennourish.main.routes import main_bp
from opennourish.time_utils import get_user_today
from opennourish.tracking.analytics import (
    get_body_composition_trends,
    get_daily_nutrition_data,
    get_exercise_vs_diet_balance,
    get_food_category_breakdown,
    get_macro_distribution_by_meal,
    get_nutrient_intake_vs_goals,
    get_weekly_trends,
)

TODAY = date.today()


@pytest.fixture
def us_client(app_with_db):
    """A client for a user whose measurement system is US customary."""
    with app_with_db.app_context():
        user = User(
            username="ususer",
            email="ususer@example.com",
            measurement_system="us",
        )
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app_with_db.test_client() as client:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True
        yield client


# --- main blueprint ---


def test_main_blueprint_is_registered_once(app_with_db):
    """The blueprint object survives registration under the expected endpoints."""
    assert main_bp.name == "main"
    assert app_with_db.blueprints["main"] is main_bp
    for endpoint in ("index", "favicon", "food_detail", "upc_search"):
        assert f"main.{endpoint}" in app_with_db.view_functions


def test_index_redirects_anonymous_to_login(client):
    """/ sends an anonymous visitor to the login page."""
    response = client.get(url_for("main.index"), follow_redirects=False)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_index_redirects_logged_in_user_to_dashboard(auth_client):
    """/ sends a signed-in user to the dashboard."""
    response = auth_client.get(url_for("main.index"), follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(url_for("dashboard.index"))


def test_food_detail_renders_portions(client, sample_usda_food, app_with_db):
    """The food detail page backfills portion sequence numbers and renders."""
    from models import UnifiedPortion

    with app_with_db.app_context():
        db.session.add(
            UnifiedPortion(
                fdc_id=sample_usda_food.fdc_id,
                portion_description="handful",
                gram_weight=40.0,
            )
        )
        db.session.commit()

    response = client.get(url_for("main.food_detail", fdc_id=sample_usda_food.fdc_id))

    assert response.status_code == 200
    assert b"handful" in response.data
    with app_with_db.app_context():
        portion = UnifiedPortion.query.filter_by(fdc_id=sample_usda_food.fdc_id).one()
        assert portion.seq_num == 1


# --- tracking: progress page ---


def test_progress_lists_check_ins_and_chart(auth_client, app_with_db):
    """The progress page charts every check-in and shows the goal line."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        db.session.add(UserGoal(user_id=user.id, calories=2000, weight_goal_kg=68.0))
        db.session.add_all(
            [
                CheckIn(
                    user_id=user.id,
                    checkin_date=TODAY - timedelta(days=10),
                    weight_kg=72.0,
                ),
                CheckIn(
                    user_id=user.id,
                    checkin_date=TODAY - timedelta(days=5),
                    weight_kg=71.0,
                    body_fat_percentage=18.456,
                ),
                CheckIn(
                    user_id=user.id, checkin_date=TODAY, weight_kg=70.0, waist_cm=80.0
                ),
            ]
        )
        db.session.commit()

    response = auth_client.get("/tracking/progress")

    assert response.status_code == 200
    assert b"progressChart" in response.data
    assert b"72" in response.data
    assert b"18.46" in response.data  # body fat rounded to two decimals
    assert b"68" in response.data  # the goal line


def test_progress_empty_state(auth_client):
    """Without check-ins the chart is replaced by zeroed summary cards."""
    response = auth_client.get("/tracking/progress")

    assert response.status_code == 200
    assert b"progressChart" not in response.data
    assert b"Log a check-in to see your progress chart!" in response.data
    assert b"0.0 kg" in response.data


def test_progress_paginates_history(auth_client, app_with_db):
    """More than ten check-ins spill onto a second page."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        db.session.add_all(
            [
                CheckIn(
                    user_id=user.id,
                    checkin_date=TODAY - timedelta(days=offset),
                    weight_kg=70.0 + offset / 100,
                )
                for offset in range(12)
            ]
        )
        db.session.commit()

    page_two = auth_client.get("/tracking/progress?page=2")

    assert page_two.status_code == 200
    assert b"page-link" in page_two.data


def test_progress_post_metric(auth_client, app_with_db):
    """A metric check-in is stored verbatim."""
    response = auth_client.post(
        "/tracking/progress",
        data={
            "checkin_date": TODAY.isoformat(),
            "weight_kg": 75.5,
            "waist_cm": 80.0,
            "body_fat_percentage": 15.0,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been recorded." in response.data
    with app_with_db.app_context():
        check_in = CheckIn.query.one()
        assert check_in.weight_kg == pytest.approx(75.5)
        assert check_in.waist_cm == pytest.approx(80.0)


def test_progress_post_us_units(us_client, app_with_db):
    """33-35: a US check-in converts pounds and inches before storing them."""
    response = us_client.post(
        "/tracking/progress",
        data={
            "checkin_date": TODAY.isoformat(),
            "weight_lbs": 154.32,
            "waist_in": 31.5,
            "body_fat_percentage": 15.0,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been recorded." in response.data
    with app_with_db.app_context():
        check_in = CheckIn.query.one()
        assert check_in.weight_kg == pytest.approx(70.0, abs=0.01)
        assert check_in.waist_cm == pytest.approx(80.01, abs=0.02)


def test_progress_post_us_without_waist(us_client, app_with_db):
    """33-35: leaving the waist blank stores no waist."""
    response = us_client.post(
        "/tracking/progress",
        data={
            "checkin_date": TODAY.isoformat(),
            "weight_lbs": 150.0,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been recorded." in response.data
    with app_with_db.app_context():
        assert CheckIn.query.one().waist_cm is None


def test_progress_us_form_converts_stored_values(us_client, app_with_db):
    """72-82: the edit rows show pounds and inches, rounded, and tolerate blanks."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="ususer").one()
        db.session.add_all(
            [
                CheckIn(
                    user_id=user.id,
                    checkin_date=TODAY - timedelta(days=2),
                    weight_kg=70.0,
                    waist_cm=80.0,
                    body_fat_percentage=15.678,
                ),
                CheckIn(user_id=user.id, checkin_date=TODAY - timedelta(days=1)),
                CheckIn(user_id=user.id, checkin_date=TODAY, weight_kg=69.0),
            ]
        )
        db.session.commit()

    response = us_client.get("/tracking/progress")

    assert response.status_code == 200
    assert b"154.32" in response.data  # 70 kg in pounds
    assert b"31.5" in response.data  # 80 cm in inches
    assert b"15.68" in response.data
    assert b"Weight (lbs)" in response.data


def test_progress_post_metric_without_weight_is_rejected(auth_client, app_with_db):
    """52-53: the metric weight is required for a new entry.

    ``templates/tracking/progress.html`` renders no ``form.errors``, so a rejected
    POST silently re-renders the page; the contract to assert is that nothing is
    written.
    """
    response = auth_client.post(
        "/tracking/progress",
        data={"checkin_date": TODAY.isoformat(), "waist_cm": 80.0},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Your check-in has been recorded." not in response.data
    with app_with_db.app_context():
        assert CheckIn.query.count() == 0


def test_progress_post_us_without_weight_is_rejected(us_client, app_with_db):
    """43-47: the US weight is required for a new entry."""
    response = us_client.post(
        "/tracking/progress",
        data={"checkin_date": TODAY.isoformat(), "waist_in": 31.5},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Your check-in has been recorded." not in response.data
    with app_with_db.app_context():
        assert CheckIn.query.count() == 0


def test_progress_post_without_date_uses_the_field_default(auth_client, app_with_db):
    """An omitted date is not a validation error: DateField defaults to today."""
    response = auth_client.post(
        "/tracking/progress", data={"weight_kg": 70.0}, follow_redirects=True
    )

    assert b"Your check-in has been recorded." in response.data
    with app_with_db.app_context():
        assert CheckIn.query.one().checkin_date == TODAY


# --- tracking: update / delete ---


def test_update_check_in_us_units(us_client, app_with_db):
    """135-137: a US update converts the submitted pounds and inches."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="ususer").one()
        check_in = CheckIn(
            user_id=user.id,
            checkin_date=TODAY,
            weight_kg=70.0,
            waist_cm=80.0,
            body_fat_percentage=15.0,
        )
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = us_client.post(
        f"/tracking/check-in/{check_in_id}/update",
        data={
            f"form-{check_in_id}-checkin_date": TODAY.isoformat(),
            f"form-{check_in_id}-weight_lbs": 176.37,
            f"form-{check_in_id}-waist_in": 35.4,
            f"form-{check_in_id}-body_fat_percentage": 20.0,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been updated." in response.data
    with app_with_db.app_context():
        updated = db.session.get(CheckIn, check_in_id)
        assert updated.weight_kg == pytest.approx(80.0, abs=0.02)
        assert updated.waist_cm == pytest.approx(89.92, abs=0.02)
        assert updated.body_fat_percentage == pytest.approx(20.0)


def test_update_check_in_metric_units(auth_client, app_with_db):
    """141-142: a metric update stores the submitted kilograms and centimetres."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        check_in = CheckIn(
            user_id=user.id, checkin_date=TODAY, weight_kg=70.0, waist_cm=80.0
        )
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = auth_client.post(
        f"/tracking/check-in/{check_in_id}/update",
        data={
            f"form-{check_in_id}-checkin_date": TODAY.isoformat(),
            f"form-{check_in_id}-weight_kg": 68.5,
            f"form-{check_in_id}-waist_cm": 79.0,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been updated." in response.data
    with app_with_db.app_context():
        updated = db.session.get(CheckIn, check_in_id)
        assert updated.weight_kg == pytest.approx(68.5)
        assert updated.waist_cm == pytest.approx(79.0)


def test_update_other_users_check_in_is_rejected(auth_client_two_users, app_with_db):
    """129-130: editing somebody else\'s check-in is refused."""
    client, _user_one, _user_two = auth_client_two_users

    with app_with_db.app_context():
        other = User.query.filter_by(username="user_two").one()
        check_in = CheckIn(user_id=other.id, checkin_date=TODAY, weight_kg=70.0)
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = client.post(
        f"/tracking/check-in/{check_in_id}/update",
        data={
            f"form-{check_in_id}-checkin_date": TODAY.isoformat(),
            f"form-{check_in_id}-weight_kg": 999.0,
        },
        follow_redirects=True,
    )

    assert b"you do not have permission to edit it" in response.data
    with app_with_db.app_context():
        assert db.session.get(CheckIn, check_in_id).weight_kg == pytest.approx(70.0)


def test_update_check_in_us_clears_missing_waist(us_client, app_with_db):
    """139: omitting the waist in a US update clears the stored value."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="ususer").one()
        check_in = CheckIn(
            user_id=user.id, checkin_date=TODAY, weight_kg=70.0, waist_cm=80.0
        )
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = us_client.post(
        f"/tracking/check-in/{check_in_id}/update",
        data={
            f"form-{check_in_id}-checkin_date": TODAY.isoformat(),
            f"form-{check_in_id}-weight_lbs": 154.32,
        },
        follow_redirects=True,
    )

    assert b"Your check-in has been updated." in response.data
    with app_with_db.app_context():
        assert db.session.get(CheckIn, check_in_id).waist_cm is None


def test_update_check_in_with_invalid_data_keeps_values(us_client, app_with_db):
    """A rejected edit leaves the stored row untouched."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="ususer").one()
        check_in = CheckIn(
            user_id=user.id, checkin_date=TODAY, weight_kg=70.0, waist_cm=80.0
        )
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = us_client.post(
        f"/tracking/check-in/{check_in_id}/update",
        data={f"form-{check_in_id}-checkin_date": TODAY.isoformat()},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app_with_db.app_context():
        unchanged = db.session.get(CheckIn, check_in_id)
        assert unchanged.weight_kg == pytest.approx(70.0)
        assert unchanged.waist_cm == pytest.approx(80.0)


def test_delete_other_users_check_in_is_rejected(auth_client_two_users, app_with_db):
    """156-157: deleting somebody else's check-in is refused."""
    client, _user_one, _user_two = auth_client_two_users

    with app_with_db.app_context():
        other = User.query.filter_by(username="user_two").one()
        check_in = CheckIn(user_id=other.id, checkin_date=TODAY, weight_kg=70.0)
        db.session.add(check_in)
        db.session.commit()
        check_in_id = check_in.id

    response = client.post(
        f"/tracking/check-in/{check_in_id}/delete", follow_redirects=True
    )

    assert b"you do not have permission to delete it" in response.data
    with app_with_db.app_context():
        assert db.session.get(CheckIn, check_in_id) is not None


def test_delete_check_in_honours_page_parameter(auth_client, app_with_db):
    """The delete redirect keeps the user on the page they were on."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        db.session.add_all(
            [
                CheckIn(
                    user_id=user.id,
                    checkin_date=TODAY - timedelta(days=offset),
                    weight_kg=70.0,
                )
                for offset in range(11)
            ]
        )
        db.session.commit()
        victim = (
            CheckIn.query.filter_by(user_id=user.id)
            .order_by(CheckIn.checkin_date.asc())
            .first()
        )
        victim_id = victim.id

    response = auth_client.post(
        f"/tracking/check-in/{victim_id}/delete?page=2", follow_redirects=False
    )

    assert response.status_code == 302
    assert "page=2" in response.headers["Location"]
    with app_with_db.app_context():
        assert db.session.get(CheckIn, victim_id) is None


def test_delete_missing_check_in_returns_404(auth_client):
    """A check-in id that does not exist is a 404, not a redirect."""
    assert auth_client.post("/tracking/check-in/999999/delete").status_code == 404


# --- tracking: analytics page ---


def _seed_analytics_data(user_id, with_goal=True):
    """Food, recipe, diary, exercise and check-in rows inside the 30-day window."""
    category = FoodCategory(id=700, code=700, description="Dairy and Egg Products")
    other_category = FoodCategory(id=701, code=701, description="Fruits and Vegetables")
    db.session.add_all([category, other_category])
    db.session.flush()

    my_food = MyFood(
        user_id=user_id,
        description="Skyr",
        food_category_id=category.id,
        calories_per_100g=60.0,
        protein_per_100g=11.0,
        carbs_per_100g=4.0,
        fat_per_100g=0.2,
    )
    recipe = Recipe(
        user_id=user_id,
        name="Big batch chilli",
        food_category_id=other_category.id,
        calories_per_100g=120.0,
        protein_per_100g=8.0,
        carbs_per_100g=14.0,
        fat_per_100g=4.0,
        final_weight_grams=2000.0,
    )
    db.session.add_all([my_food, recipe])
    db.session.flush()

    db.session.add_all(
        [
            DailyLog(
                user_id=user_id,
                log_date=TODAY,
                meal_name="Breakfast",
                my_food_id=my_food.id,
                amount_grams=250,
            ),
            DailyLog(
                user_id=user_id,
                log_date=TODAY,
                meal_name="Dinner",
                recipe_id=recipe.id,
                amount_grams=400,
            ),
            DailyLog(
                user_id=user_id,
                log_date=TODAY - timedelta(days=3),
                meal_name="Lunch",
                my_food_id=my_food.id,
                amount_grams=200,
            ),
            DailyLog(
                user_id=user_id,
                log_date=TODAY - timedelta(days=400),
                meal_name="Lunch",
                my_food_id=my_food.id,
                amount_grams=200,
            ),
            ExerciseLog(
                user_id=user_id,
                log_date=TODAY,
                manual_description="Ruck",
                duration_minutes=45,
                calories_burned=350,
            ),
            ExerciseLog(
                user_id=user_id,
                log_date=TODAY - timedelta(days=6),
                manual_description="Pool lap",
                duration_minutes=30,
                calories_burned=280,
            ),
            CheckIn(
                user_id=user_id,
                checkin_date=TODAY,
                weight_kg=70.0,
                waist_cm=80.0,
                body_fat_percentage=15.0,
            ),
        ]
    )
    db.session.commit()
    if with_goal and UserGoal.query.filter_by(user_id=user_id).first() is None:
        db.session.add(
            UserGoal(user_id=user_id, calories=2000, protein=120, carbs=220, fat=65)
        )
        db.session.commit()
    return my_food, recipe


def test_analytics_page_renders_every_chart(auth_client_onboarded, app_with_db):
    """176-205: with a month of data every analytics card is populated."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="onboardeduser").one()
        _seed_analytics_data(user.id)

    response = auth_client_onboarded.get("/tracking/analytics")

    assert response.status_code == 200
    assert b"Analytics Dashboard" in response.data
    for canvas in (
        b"dailyNutritionChart",
        b"macroDistributionChart",
        b"weeklyTrendsChart",
        b"categoryBreakdownChart",
        b"exerciseBalanceChart",
        b"bodyCompositionChart",
    ):
        assert canvas in response.data
    assert b"Today's Progress vs Goals" in response.data
    assert b"Dairy and Egg Products" in response.data
    assert b"No nutrition data available" not in response.data


def test_analytics_page_without_a_goal_row(auth_client, app_with_db):
    """With data but no goal row the goal card disappears, the rest stays."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        _seed_analytics_data(user.id, with_goal=False)

    response = auth_client.get("/tracking/analytics")

    assert response.status_code == 200
    assert b"Today's Progress vs Goals" not in response.data
    assert b"dailyNutritionChart" in response.data


def test_analytics_page_empty_state(auth_client):
    """A brand-new account gets the empty-state copy in every card."""
    response = auth_client.get("/tracking/analytics")

    assert response.status_code == 200
    assert b"Today's Progress vs Goals" not in response.data
    assert b"No nutrition data available" in response.data
    assert b"No meal data available" in response.data
    assert b"No weekly data available" in response.data
    assert b"No category data available" in response.data


# --- tracking: analytics builders ---


def test_daily_nutrition_window_is_parameterised(auth_client_onboarded, app_with_db):
    """Only logs inside the requested window are reported."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="onboardeduser").one()
        _seed_analytics_data(user.id)

        recent = get_daily_nutrition_data(user.id, days=7)
        wide = get_daily_nutrition_data(user.id, days=30)

        assert [row["date"] for row in recent] == [TODAY - timedelta(days=3), TODAY]
        # The 400-day-old log stays outside both windows.
        assert [row["date"] for row in wide] == [TODAY - timedelta(days=3), TODAY]
        assert wide[-1]["calories"] == pytest.approx(150.0, abs=1.0)
        assert get_daily_nutrition_data(user.id + 4242) == []


def test_food_category_breakdown_covers_foods_and_recipes(
    auth_client_onboarded, app_with_db
):
    """191-216: both MyFood and Recipe rows contribute to the category split."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="onboardeduser").one()
        _seed_analytics_data(user.id)

        breakdown = get_food_category_breakdown(user.id, days=30)

    assert {row["category"] for row in breakdown} == {
        "Dairy and Egg Products",
        "Fruits and Vegetables",
    }
    assert sum(row["percentage"] for row in breakdown) == pytest.approx(100.0, abs=0.2)
    by_category = {row["category"]: row for row in breakdown}
    # 250 g of 60 kcal/100 g food plus 400 g of 120 kcal/100 g recipe today.
    # 250 g + 200 g of a 60 kcal/100 g food across the 30-day window.
    assert by_category["Dairy and Egg Products"]["calories"] == pytest.approx(270.0)
    assert by_category["Fruits and Vegetables"]["calories"] == pytest.approx(480.0)


def test_food_category_breakdown_ignores_uncategorised_rows(auth_client, app_with_db):
    """Logs whose rows carry no category yield an empty breakdown, not None."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        food = MyFood(
            user_id=user.id, description="No category", calories_per_100g=100.0
        )
        db.session.add(food)
        db.session.commit()
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=TODAY,
                my_food_id=food.id,
                amount_grams=100,
            )
        )
        db.session.commit()

        assert get_food_category_breakdown(user.id, days=30) == []


def test_remaining_analytics_builders(auth_client_onboarded, app_with_db):
    """The macro, trend, balance, goal and composition builders return plain data."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="onboardeduser").one()
        _seed_analytics_data(user.id)

        macros = get_macro_distribution_by_meal(user.id, days=7)
        assert macros, "expected at least one populated meal"
        assert set(macros["Breakfast"]) == {"protein", "carbs", "fat", "total_calories"}

        trends = get_weekly_trends(user.id)
        assert trends and trends[0]["calories"] > 0

        balance = get_exercise_vs_diet_balance(user.id, days=30)
        today_row = [row for row in balance if row["date"] == TODAY]
        assert today_row and today_row[0]["calories_out"] == 350
        assert today_row[0]["net"] < 0
        # A training day without any food log still shows up.
        swim_row = [row for row in balance if row["date"] == TODAY - timedelta(days=6)]
        assert swim_row[0]["calories_in"] == 0
        assert swim_row[0]["net"] == -280

        goals = get_nutrient_intake_vs_goals(user.id)
        assert goals["calories"]["goal"] == 2000
        assert goals["calories"]["intake"] > 0

        composition = get_body_composition_trends(user.id)
        assert composition[0]["weight_kg"] == 70.0
        assert composition[0]["date"] == TODAY.strftime("%Y-%m-%d")


def test_analytics_builders_for_a_user_without_data(app_with_db):
    """Every builder degrades to an empty structure for an unknown user."""
    with app_with_db.app_context():
        assert get_daily_nutrition_data(9999) == []
        assert get_macro_distribution_by_meal(9999) == {}
        assert get_weekly_trends(9999) == []
        assert get_food_category_breakdown(9999) == []
        assert get_exercise_vs_diet_balance(9999) == []
        assert get_nutrient_intake_vs_goals(9999) is None
        assert get_body_composition_trends(9999) == []


def test_progress_uses_user_local_today(auth_client, app_with_db):
    """The prefilled check-in date is the user's local today."""
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        user.timezone = "Pacific/Kiritimati"
        db.session.commit()
        expected = get_user_today("Pacific/Kiritimati").isoformat()

    response = auth_client.get("/tracking/progress")

    assert expected.encode() in response.data
