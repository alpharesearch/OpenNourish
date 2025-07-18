import pytest
from models import db, User, UserGoal, ExerciseLog, ExerciseActivity, CheckIn
from datetime import date, timedelta

def test_dashboard_exercise_goals_display(auth_client):
    """
    GIVEN a user with exercise goals and logged exercises
    WHEN the user visits the dashboard
    THEN the weekly exercise goals and progress should be displayed correctly.
    """
    client = auth_client
    with client.application.app_context():
        user = db.session.get(User, 1) # Assuming user with ID 1 is the testuser
        user.has_completed_onboarding = True
        db.session.add(user)

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
        activity1 = ExerciseActivity(name='Running', met_value=8.0)
        activity2 = ExerciseActivity(name='Weightlifting', met_value=3.0)
        db.session.add_all([activity1, activity2])
        db.session.commit()

        # Log exercises for the current week
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())

        # Log 1: Running, 40 mins, 400 kcal (example values)
        log1 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week,
            activity_id=activity1.id,
            duration_minutes=40,
            calories_burned=400
        )
        db.session.add(log1)

        # Log 2: Weightlifting, 50 mins, 250 kcal (example values)
        log2 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week + timedelta(days=1),
            activity_id=activity2.id,
            duration_minutes=50,
            calories_burned=250
        )
        db.session.add(log2)
        db.session.commit()

    # Visit the dashboard
    response = client.get('/dashboard/')
    assert response.status_code == 200

    # Assert that the weekly exercise goals section is displayed
    assert b'Weekly Exercise Goals' in response.data

    # Assert calories burned progress
    assert b'Calories Burned' in response.data
    assert b'Progress: 650 kcal' in response.data # 400 + 250

    # Assert workouts progress
    assert b'Workouts' in response.data
    assert b'Progress: 2' in response.data

    # Assert exercise minutes progress
    assert b'Exercise Minutes' in response.data
    assert b'Progress: 90 min' in response.data # 40 + 50
