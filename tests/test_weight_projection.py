import pytest
from datetime import date, timedelta
from models import db, User, UserGoal, CheckIn, DailyLog, ExerciseLog
from opennourish.utils import calculate_weight_projection, calculate_bmr

@pytest.fixture
def user_with_projection_data(auth_client):
    """Fixture to create a user with baseline data for projection tests."""
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.age = 30
        user.gender = 'Male'
        user.height_cm = 180
        user.has_completed_onboarding = True
        db.session.add(user)

        checkin = CheckIn(user_id=user.id, weight_kg=131.5, checkin_date=date.today() - timedelta(days=1)) # Approx 290 lbs
        goal = UserGoal(user_id=user.id, weight_goal_kg=90.7) # Approx 200 lbs
        
        db.session.add(checkin)
        db.session.add(goal)
        db.session.commit()
        # Return the user ID to avoid detached instance errors
        return auth_client, user.id

def test_projection_no_activity_uses_goal(user_with_projection_data):
    """
    GIVEN a user with a weight goal but no logged activity.
    WHEN the weight projection is calculated.
    THEN it should return a projection based on the user's calorie goal.
    """
    client, user_id = user_with_projection_data
    with client.application.app_context():
        user = db.session.get(User, user_id)
        # Set a calorie goal that creates a deficit
        user.goals.calories = 1800
        db.session.commit()

        dates, weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(user)
        
        assert len(dates) > 1 # A projection should be made
        assert not trending_away
        assert not at_goal_and_maintaining
        assert weights[0] > weights[-1] # Weight should decrease
        assert weights[-1] == pytest.approx(user.goals.weight_goal_kg, abs=0.5)

def test_projection_correct_weight_loss(user_with_projection_data, monkeypatch):
    """
    GIVEN a user eating at a calorie deficit.
    WHEN the weight projection is calculated.
    THEN it should project a steady weight loss towards the goal.
    """
    client, user_id = user_with_projection_data
    with client.application.app_context():
        user = db.session.get(User, user_id)
        # BMR for this user is ~2150 kcal. A 500 kcal deficit.
        # Log 14 days of eating 1650 kcal
        for i in range(14):
            log = DailyLog(
                user_id=user.id,
                log_date=date.today() - timedelta(days=i+1),
                meal_name='Breakfast',
                amount_grams=1650 # Using grams field to store calories for test simplicity
            )
            db.session.add(log)
        db.session.commit()

        # Mock the nutrition calculation to return our simplified calorie data
        def mock_calculate_nutrition(items, **kwargs):
            return {'calories': sum(item.amount_grams for item in items)}
        
        monkeypatch.setattr('opennourish.utils.calculate_nutrition_for_items', mock_calculate_nutrition)

        dates, weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(user)

        assert len(dates) > 1 # A projection was made
        assert not trending_away # Should not be trending away
        assert not at_goal_and_maintaining
        assert weights[0] > weights[-1] # Weight should decrease
        assert weights[-1] == pytest.approx(user.goals.weight_goal_kg, abs=0.5) # Should end near goal

def test_projection_trending_away_from_loss_goal(user_with_projection_data, monkeypatch):
    """
    GIVEN a user with a weight loss goal who is eating at a surplus.
    WHEN the weight projection is calculated.
    THEN it should project for only 7 days and indicate trending_away is True.
    """
    client, user_id = user_with_projection_data
    with client.application.app_context():
        user = db.session.get(User, user_id)
        # BMR is ~2150. Log 14 days of eating 2500 kcal (surplus)
        for i in range(14):
            log = DailyLog(
                user_id=user.id,
                log_date=date.today() - timedelta(days=i+1),
                meal_name='Breakfast',
                amount_grams=2500
            )
            db.session.add(log)
        db.session.commit()

        def mock_calculate_nutrition(items, **kwargs):
            return {'calories': sum(item.amount_grams for item in items)}

        monkeypatch.setattr('opennourish.utils.calculate_nutrition_for_items', mock_calculate_nutrition)

        dates, weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(user)

    assert trending_away is True
    assert not at_goal_and_maintaining
    assert len(dates) == 8 # Projects for today + 7 days
    assert weights[0] < weights[-1] # Weight should increase

def test_projection_with_exercise(user_with_projection_data, monkeypatch):
    """
    GIVEN a user eating at a deficit which is enhanced by exercise.
    WHEN the weight projection is calculated.
    THEN it should project a faster weight loss.
    """
    client, user_id = user_with_projection_data
    with client.application.app_context():
        user = db.session.get(User, user_id)
        # BMR ~2150. Eating 2000 kcal, burning 300 kcal/day. Net deficit = 450.
        for i in range(14):
            diet_log = DailyLog(
                user_id=user.id,
                log_date=date.today() - timedelta(days=i+1),
                meal_name='Lunch',
                amount_grams=2000
            )
            exercise_log = ExerciseLog(
                user_id=user.id,
                log_date=date.today() - timedelta(days=i+1),
                calories_burned=300,
                duration_minutes=30
            )
            db.session.add_all([diet_log, exercise_log])
        db.session.commit()

        def mock_calculate_nutrition(items, **kwargs):
            return {'calories': sum(item.amount_grams for item in items)}

        monkeypatch.setattr('opennourish.utils.calculate_nutrition_for_items', mock_calculate_nutrition)

        dates, weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(user)

        assert len(dates) > 1
        assert not trending_away
        assert not at_goal_and_maintaining
        assert weights[0] > weights[-1]
        assert weights[-1] == pytest.approx(user.goals.weight_goal_kg, abs=0.5)

def test_projection_at_goal_and_maintaining(user_with_projection_data, monkeypatch):
    """
    GIVEN a user who is at their goal weight and maintaining their calorie intake.
    WHEN the weight projection is calculated.
    THEN it should indicate at_goal_and_maintaining is True and project for only 1 day.
    """
    client, user_id = user_with_projection_data
    with client.application.app_context():
        user = db.session.get(User, user_id)
        # Set current weight to goal weight
        latest_checkin = CheckIn.query.filter_by(user_id=user.id).order_by(CheckIn.checkin_date.desc()).first()
        latest_checkin.weight_kg = user.goals.weight_goal_kg
        db.session.commit()

        # Set calorie goal to BMR (maintenance)
        user.goals.calories = round(calculate_bmr(latest_checkin.weight_kg, user.height_cm, user.age, user.gender)[0])
        db.session.commit()

        # Ensure no recent diet or exercise logs to trigger the fallback to goal calories
        DailyLog.query.filter_by(user_id=user.id).delete()
        ExerciseLog.query.filter_by(user_id=user.id).delete()
        db.session.commit()

        dates, weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(user)

        assert at_goal_and_maintaining is True
        assert not trending_away
        assert len(dates) == 1 # Only today's date should be projected
        assert weights[0] == pytest.approx(user.goals.weight_goal_kg, abs=0.01)