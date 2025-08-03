import pytest
from models import (
    db,
    User,
    UserGoal,
    ExerciseLog,
    ExerciseActivity,
    CheckIn,
    DailyLog,
    Food,
    MyFood,
    FastingSession,
)
from datetime import timedelta, datetime
from opennourish.time_utils import get_user_today


def test_dashboard_exercise_goals_display(auth_client_onboarded):
    """
    GIVEN a user with exercise goals and logged exercises
    WHEN the user visits the dashboard
    THEN the weekly exercise goals and progress should be displayed correctly.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()

        # Set up exercise goals for the user
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        if not user_goal:
            user_goal = UserGoal(user_id=user.id)
            db.session.add(user_goal)
        user_goal.calories_burned_goal_weekly = 1500
        user_goal.exercises_per_week_goal = 3
        user_goal.minutes_per_exercise_goal = 45
        db.session.commit()

        # Create some exercise activities
        activity1 = ExerciseActivity(name="Running", met_value=8.0)
        activity2 = ExerciseActivity(name="Weightlifting", met_value=3.0)
        db.session.add_all([activity1, activity2])
        db.session.commit()

        # Log exercises for the current week
        today = get_user_today(user.timezone)
        start_of_week = today - timedelta(days=today.weekday())

        # Log 1: Running, 40 mins, 400 kcal (example values)
        log1 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week,
            activity_id=activity1.id,
            duration_minutes=40,
            calories_burned=400,
        )
        db.session.add(log1)

        # Log 2: Weightlifting, 50 mins, 250 kcal (example values)
        log2 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week + timedelta(days=1),
            activity_id=activity2.id,
            duration_minutes=50,
            calories_burned=250,
        )
        db.session.add(log2)
        db.session.commit()

    # Visit the dashboard
    response = client.get("/dashboard/")
    assert response.status_code == 200

    # Assert that the weekly exercise goals section is displayed
    assert b"Weekly Exercise Goals" in response.data

    # Assert calories burned progress
    assert b"Calories Burned" in response.data
    assert b"Progress: 650 kcal" in response.data  # 400 + 250

    # Assert workouts progress
    assert b"Workouts" in response.data
    assert b"Progress: 2" in response.data

    # Assert exercise minutes progress
    assert b"Exercise Minutes" in response.data
    assert b"Progress: 90 min" in response.data  # 40 + 50


def test_dashboard_weight_projection_display(auth_client_onboarded):
    """
    GIVEN a user with check-ins and a weight goal
    WHEN the user visits the dashboard
    THEN the weight projection chart and summary should be displayed.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()

        # Set a weight goal
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        if not user_goal:
            user_goal = UserGoal(user_id=user.id)
            db.session.add(user_goal)
        user_goal.weight_goal_kg = 70.0
        user_goal.calories = 2000
        user_goal.body_fat_percentage_goal = 15.0
        user_goal.waist_cm_goal = 80.0
        db.session.commit()

        # Create a series of check-ins showing weight loss
        today = get_user_today(user.timezone)
        # Add more check-ins to ensure projection is calculated
        checkin1 = CheckIn(
            user_id=user.id,
            checkin_date=today - timedelta(weeks=8),
            weight_kg=82.0,
            body_fat_percentage=22.0,
            waist_cm=92.0,
        )
        checkin2 = CheckIn(
            user_id=user.id,
            checkin_date=today - timedelta(weeks=6),
            weight_kg=80.0,
            body_fat_percentage=21.0,
            waist_cm=91.0,
        )
        checkin3 = CheckIn(
            user_id=user.id,
            checkin_date=today - timedelta(weeks=4),
            weight_kg=78.0,
            body_fat_percentage=20.0,
            waist_cm=90.0,
        )
        checkin4 = CheckIn(
            user_id=user.id,
            checkin_date=today - timedelta(weeks=2),
            weight_kg=76.0,
            body_fat_percentage=19.0,
            waist_cm=89.0,
        )
        checkin5 = CheckIn(
            user_id=user.id,
            checkin_date=today,
            weight_kg=75.0,
            body_fat_percentage=18.0,
            waist_cm=88.0,
        )
        db.session.add_all([checkin1, checkin2, checkin3, checkin4, checkin5])

        # Add recent diet and exercise logs to ensure projection is calculated
        food = Food(fdc_id=999999, description="Test Food")
        db.session.add(food)
        db.session.commit()
        for i in range(14):
            log_date = today - timedelta(days=i)
            db.session.add(
                DailyLog(
                    user_id=user.id,
                    log_date=log_date,
                    fdc_id=food.fdc_id,
                    amount_grams=100,
                )
            )
            db.session.add(
                ExerciseLog(
                    user_id=user.id,
                    log_date=log_date,
                    calories_burned=100,
                    duration_minutes=30,
                )
            )
        db.session.commit()

    # Visit the dashboard
    response = client.get("/dashboard/")
    assert response.status_code == 200

    # Assert that the weight projection section is displayed
    #
    assert b"you are projected to reach your goal" in response.data


def test_dashboard_with_specific_date(auth_client_onboarded):
    """
    GIVEN a logged-in user
    WHEN the user visits the dashboard for a specific date
    THEN the page should display that date.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()
        target_date = get_user_today(user.timezone) - timedelta(days=5)
    target_date_str = target_date.isoformat()

    response = client.get(f"/dashboard/{target_date_str}")
    assert response.status_code == 200

    # Check that the displayed date is correct
    assert bytes(target_date.strftime("%A, %B %d, %Y"), "utf-8") in response.data


def test_dashboard_no_user_goal(auth_client_onboarded):
    """
    GIVEN a user who has not set up any goals
    WHEN the user visits the dashboard
    THEN the dashboard should load with default goal values.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()
        # Ensure no goal exists
        UserGoal.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    response = client.get("/dashboard/")
    assert response.status_code == 200
    # Check for default calorie goal display
    assert b"Goal: 2000.0 kcal" in response.data


def test_dashboard_food_names_display(auth_client_onboarded):
    """
    GIVEN a user with diary entries for both USDA and MyFood items
    WHEN the user visits the dashboard
    THEN the correct food names should be displayed for each entry.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()

        # Create a MyFood item
        my_food = MyFood(
            user_id=user.id, description="My Test Food", calories_per_100g=100
        )
        db.session.add(my_food)
        db.session.commit()

        # Create a dummy USDA food entry for testing purposes
        usda_food = Food(fdc_id=12345, description="USDA Test Food")
        db.session.add(usda_food)
        db.session.commit()

        # Log both items in the diary for today
        today = get_user_today(user.timezone)
        log1 = DailyLog(
            user_id=user.id, log_date=today, my_food_id=my_food.id, amount_grams=100
        )
        log2 = DailyLog(
            user_id=user.id, log_date=today, fdc_id=usda_food.fdc_id, amount_grams=150
        )
        db.session.add_all([log1, log2])
        db.session.commit()

    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert b"My Test Food" in response.data
    assert b"USDA Test Food" in response.data


def _create_checkin_data(user_id, num_days_step, count):
    """Helper function to create check-in data for a user."""
    user = db.session.get(User, user_id)
    today = get_user_today(user.timezone)
    for i in range(count):
        checkin_date = today - timedelta(days=i * num_days_step)
        db.session.add(
            CheckIn(
                user_id=user_id,
                checkin_date=checkin_date,
                weight_kg=80 - i,
                body_fat_percentage=20 - i,
                waist_cm=90 - i,
            )
        )
    db.session.commit()


@pytest.mark.parametrize(
    "time_range,expected_checkins",
    [
        ("1_month", 2),
        ("3_month", 4),
        ("6_month", 7),
        ("1_year", 12),
        ("all_time", 12),
    ],
)
def test_dashboard_time_range_filter(
    auth_client_onboarded, time_range, expected_checkins
):
    """
    GIVEN a user with check-ins over a long period
    WHEN the user visits the dashboard with different time_range parameters
    THEN the chart should display the correct number of check-ins.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        if not user_goal:
            user_goal = UserGoal(user_id=user.id)
            db.session.add(user_goal)
        user_goal.weight_goal_kg = 70.0
        user_goal.calories = 2000  # Add calorie goal
        user_goal.body_fat_percentage_goal = 15.0  # Add body fat goal
        user_goal.waist_cm_goal = 80.0  # Add waist goal
        db.session.commit()

        # Clear existing check-ins and create new ones
        CheckIn.query.filter_by(user_id=user.id).delete()
        _create_checkin_data(user.id, 30, 12)  # Create 12 check-ins, one every 30 days

    response = client.get(f"/dashboard/?time_range={time_range}")
    assert response.status_code == 200

    # Use regex to reliably extract the chart labels array content
    import re

    assert b"Log a check-in to see your progress chart!" not in response.data
    match = re.search(rb"const labels = (.*?);", response.data, re.DOTALL)

    assert match, "Could not find chart_labels array in the response."

    chart_labels_data = match.group(1)

    # Count the number of items (labels) in the JavaScript array
    # A simple way is to count the number of quotes, and divide by 2
    num_items = chart_labels_data.count(b'"') / 2

    assert num_items == expected_checkins


def test_dashboard_fasting_status(auth_client_onboarded):
    """
    GIVEN a user with an active fasting session
    WHEN the user visits the dashboard
    THEN the fasting status should be displayed.
    """
    client = auth_client_onboarded
    with client.application.app_context():
        user = User.query.filter_by(username="onboardeduser").first()

        # Start an active fast
        FastingSession.query.filter_by(user_id=user.id).delete()  # Clear old fasts
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(hours=10),
            status="active",
            planned_duration_hours=24,  # Add required field
        )
        db.session.add(fast)
        db.session.commit()

    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert b"Fasting Status" in response.data
    assert b"Fast Started:" in response.data
    assert b"Planned Duration" in response.data
