import pytest
from models import db, User, ExerciseLog, ExerciseActivity, UserGoal
from datetime import date, timedelta

def test_weekly_exercise_progress_display(auth_client):
    """
    GIVEN a user with exercise goals and logged exercises
    WHEN the user visits the exercise log page
    THEN the weekly progress should be displayed correctly.
    """
    client = auth_client
    with client.application.app_context():
        user = User.query.filter_by(username='testuser').first()

        # Set up exercise goals for the user
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        if not user_goal:
            user_goal = UserGoal(user_id=user.id)
            db.session.add(user_goal)
        user_goal.calories_burned_goal_weekly = 1000
        user_goal.exercises_per_week_goal = 2
        user_goal.minutes_per_exercise_goal = 60
        db.session.commit()

        # Create some exercise activities
        activity1 = ExerciseActivity(name='Running', met_value=8.0)
        activity2 = ExerciseActivity(name='Cycling', met_value=6.0)
        db.session.add_all([activity1, activity2])
        db.session.commit()

        # Log exercises for the current week
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())

        # Log 1: Running, 45 mins, 300 kcal (example values)
        log1 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week,
            activity_id=activity1.id,
            duration_minutes=45,
            calories_burned=300
        )
        db.session.add(log1)

        # Log 2: Cycling, 60 mins, 400 kcal (example values)
        log2 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week + timedelta(days=1),
            activity_id=activity2.id,
            duration_minutes=60,
            calories_burned=400
        )
        db.session.add(log2)
        db.session.commit()

    # Visit the exercise log page
    response = client.get('/exercise/log')
    assert response.status_code == 200

    # Assert that the weekly progress is displayed correctly
    assert b'This Week\'s Progress' in response.data
    assert b'Calories Burned' in response.data
    assert b'700 / 1000' in response.data  # 300 + 400
    assert b'Workouts' in response.data
    assert b'2 / 2' in response.data
    assert b'Minutes' in response.data
    assert b'105 / 120' in response.data # (45 + 60) / (60 * 2)
