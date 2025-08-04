import pytest
from models import db, User, ExerciseLog, ExerciseActivity, UserGoal, CheckIn
from datetime import date, timedelta
from opennourish.time_utils import get_user_today


def test_weekly_exercise_progress_display(auth_client):
    """
    GIVEN a user with exercise goals and logged exercises
    WHEN the user visits the exercise log page
    THEN the weekly progress should be displayed correctly.
    """
    client = auth_client
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()

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
        activity1 = ExerciseActivity(name="Running", met_value=8.0)
        activity2 = ExerciseActivity(name="Cycling", met_value=6.0)
        db.session.add_all([activity1, activity2])
        db.session.commit()

        # Log exercises for the current week
        today = get_user_today(user.timezone)
        start_of_week = today - timedelta(days=today.weekday())

        # Log 1: Running, 45 mins, 300 kcal (example values)
        log1 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week,
            activity_id=activity1.id,
            duration_minutes=45,
            calories_burned=300,
        )
        db.session.add(log1)

        # Log 2: Cycling, 60 mins, 400 kcal (example values)
        log2 = ExerciseLog(
            user_id=user.id,
            log_date=start_of_week + timedelta(days=1),
            activity_id=activity2.id,
            duration_minutes=60,
            calories_burned=400,
        )
        db.session.add(log2)
        db.session.commit()

    # Visit the exercise log page
    response = client.get("/exercise/log")
    assert response.status_code == 200

    # Assert that the weekly progress is displayed correctly
    assert b"This Week's Progress" in response.data
    assert b"Calories Burned" in response.data
    assert b"700 / 1000" in response.data  # 300 + 400
    assert b"Workouts" in response.data
    assert b"2 / 2" in response.data
    assert b"Minutes" in response.data
    assert b"105 / 120" in response.data  # (45 + 60) / (60 * 2)


def test_log_new_exercise_activity(auth_client):
    """
    GIVEN a logged-in user and an existing exercise activity
    WHEN the user submits the form to log a new exercise
    THEN a new ExerciseLog record is created with calculated calories.
    """
    client = auth_client
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # Ensure user has a weight check-in
        from models import CheckIn

        db.session.add(
            CheckIn(user_id=user.id, weight_kg=75.0, checkin_date=date.today())
        )
        activity = ExerciseActivity(name="Jumping Jacks", met_value=8.0)
        db.session.add(activity)
        db.session.commit()
        activity_id = activity.id

    response = client.post(
        "/exercise/log",
        data={
            "log_date": date.today().isoformat(),
            "activity": activity_id,
            "duration_minutes": "30",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Exercise logged successfully!" in response.data

    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        log = ExerciseLog.query.filter_by(user_id=user.id).first()
        assert log is not None
        assert log.activity_id == activity_id
        assert log.duration_minutes == 30
        # Expected calories = (8.0 * 3.5 * 75 / 200) * 30 = 315
        assert log.calories_burned == pytest.approx(315)


def test_edit_exercise_log(auth_client):
    """
    GIVEN an existing exercise log
    WHEN the user submits the form to edit the log
    THEN the ExerciseLog record is updated.
    """
    client = auth_client
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        db.session.add(
            CheckIn(user_id=user.id, weight_kg=75.0, checkin_date=date.today())
        )
        activity = ExerciseActivity(name="Push-ups", met_value=8.0)
        db.session.add(activity)
        db.session.commit()

        log = ExerciseLog(
            user_id=user.id,
            log_date=date.today(),
            activity_id=activity.id,
            duration_minutes=10,
            calories_burned=105,  # (8 * 3.5 * 75 / 200) * 10
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id
        activity_id = activity.id

    # Note: The form name prefix is required for editing items in the list
    response = client.post(
        f"/exercise/{log_id}/edit",
        data={
            f"form-{log_id}-log_date": date.today().isoformat(),
            f"form-{log_id}-activity": activity_id,
            f"form-{log_id}-duration_minutes": "20",  # Changed duration
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Exercise log updated successfully!" in response.data

    with client.application.app_context():
        updated_log = db.session.get(ExerciseLog, log_id)
        assert updated_log.duration_minutes == 20
        # Expected calories = (8.0 * 3.5 * 75 / 200) * 20 = 210
        assert updated_log.calories_burned == pytest.approx(210)


def test_delete_exercise_log(auth_client):
    """
    GIVEN an existing exercise log
    WHEN the user submits a request to delete the log
    THEN the ExerciseLog record is removed from the database.
    """
    client = auth_client
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        log = ExerciseLog(
            user_id=user.id,
            log_date=date.today(),
            manual_description="Test to delete",
            duration_minutes=15,
            calories_burned=100,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    response = client.post(f"/exercise/{log_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Exercise log deleted successfully!" in response.data

    with client.application.app_context():
        deleted_log = db.session.get(ExerciseLog, log_id)
        assert deleted_log is None


def test_exercise_log_authorization(auth_client_two_users):
    """
    GIVEN two users, where user_one has an exercise log
    WHEN user_two attempts to edit or delete user_one's log
    THEN the operations should be denied.
    """
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        # Create a log for user_one
        log_user_one = ExerciseLog(
            user_id=user_one.id,
            log_date=date.today(),
            manual_description="User One's Log",
            duration_minutes=30,
            calories_burned=150,
        )
        db.session.add(log_user_one)
        db.session.commit()
        log_id = log_user_one.id

    # Log in as user_two
    with client.session_transaction() as sess:
        sess["_user_id"] = user_two.id
        sess["_fresh"] = True

    # Attempt to edit user_one's log as user_two
    response_edit = client.post(
        f"/exercise/{log_id}/edit", data={}, follow_redirects=True
    )
    assert response_edit.status_code == 200
    assert (
        b"You do not have permission to edit this exercise log." in response_edit.data
    )

    # Attempt to delete user_one's log as user_two
    response_delete = client.post(
        f"/exercise/{log_id}/delete", data={}, follow_redirects=True
    )
    assert response_delete.status_code == 200
    assert (
        b"You do not have permission to delete this exercise log."
        in response_delete.data
    )

    # Verify the log still exists
    with client.application.app_context():
        assert db.session.get(ExerciseLog, log_id) is not None
