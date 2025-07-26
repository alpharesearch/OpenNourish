import pytest
from models import UserGoal, User, CheckIn, db
from datetime import date
from unittest.mock import MagicMock
from opennourish.goals.forms import GoalForm

def test_set_goals_for_new_user(auth_client):
    """
    GIVEN a logged-in user with no existing goals
    WHEN the user submits the goals form
    THEN a new UserGoal object should be created
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        db.session.add(user)
        db.session.commit()
    data = {
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'weight_kg': 80,
        'calories': 2500,
        'protein': 150,
        'carbs': 300,
        'fat': 80
    }
    

    response = auth_client.post('/goals/', data=data, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.calories == 2500
        assert user_goal.protein == 150

def test_update_existing_goals(auth_client):
    """
    GIVEN a logged-in user with an existing goal
    WHEN the user submits the goals form with new data
    THEN the existing UserGoal object should be updated
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        initial_goal = UserGoal(
            user_id=user.id,
            calories=2000,
            protein=120,
            carbs=250,
            fat=70,
            default_fasting_hours=20
        )
        db.session.add(user)
        db.session.add(initial_goal)
        db.session.commit()
        initial_goal_id = initial_goal.id

    data = {
        'age': 31,
        'gender': 'Female',
        'height_cm': 170,
        'weight_kg': 65,
        'calories': 2200,
        'protein': 140,
        'carbs': 280,
        'fat': 75,
        'default_fasting_hours': 18
    }
    

    response = auth_client.post('/goals/', data=data, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.calories == 2200
        assert user_goal.protein == 140
        assert user_goal.default_fasting_hours == 18
        assert user_goal.id == initial_goal_id

def test_goal_modifier_and_diet_preset_are_saved(auth_client):
    """
    GIVEN a logged-in user
    WHEN the user submits the goals form with a goal modifier and diet preset
    THEN the UserGoal object should be created with the selected values.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        db.session.add(user)
        db.session.commit()

    data = {
        'goal_modifier': 'moderate_loss',
        'diet_preset': 'Keto',
        'calories': '1800',
        'protein': '150',
        'carbs': '25',
        'fat': '125'
    }

    response = auth_client.post('/goals/', data=data, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.goal_modifier == 'moderate_loss'
        assert user_goal.diet_preset == 'Keto'
        assert user_goal.calories == 1800
        assert user_goal.protein == 150
        assert user_goal.carbs == 25
        assert user_goal.fat == 125

def test_exercise_goals_update(auth_client):
    """
    GIVEN a logged-in user with existing goals
    WHEN the user submits the goals form with new exercise goal data
    THEN the UserGoal object should be updated with the new exercise goal values.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        initial_goal = UserGoal(
            user_id=user.id,
            calories=2000,
            protein=120,
            carbs=250,
            fat=70,
            calories_burned_goal_weekly=1000,
            exercises_per_week_goal=3,
            minutes_per_exercise_goal=30
        )
        db.session.add(user)
        db.session.add(initial_goal)
        db.session.commit()
        initial_goal_id = initial_goal.id

    data = {
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'weight_kg': 80,
        'calories': 2000,
        'protein': 120,
        'carbs': 250,
        'fat': 70,
        'calories_burned_goal_weekly': 1500,
        'exercises_per_week_goal': 5,
        'minutes_per_exercise_goal': 45
    }

    response = auth_client.post('/goals/', data=data, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.id == initial_goal_id
        assert user_goal.calories_burned_goal_weekly == 1500
        assert user_goal.exercises_per_week_goal == 5
        assert user_goal.minutes_per_exercise_goal == 45

def test_body_composition_goals_update(auth_client):
    """
    GIVEN a logged-in user with existing goals
    WHEN the user submits the goals form with new body composition goal data
    THEN the UserGoal object should be updated with the new body composition goal values.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        initial_goal = UserGoal(
            user_id=user.id,
            calories=2000,
            protein=120,
            carbs=250,
            fat=70,
            weight_goal_kg=70,
            body_fat_percentage_goal=15,
            waist_cm_goal=80
        )
        db.session.add(user)
        db.session.add(initial_goal)
        db.session.commit()
        initial_goal_id = initial_goal.id

    data = {
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'weight_kg': 80,
        'calories': 2000,
        'protein': 120,
        'carbs': 250,
        'fat': 70,
        'weight_goal_kg': 75,
        'body_fat_percentage_goal': 12,
        'waist_cm_goal': 75
    }

    response = auth_client.post('/goals/', data=data, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.id == initial_goal_id
        assert user_goal.weight_goal_kg == 75
        assert user_goal.body_fat_percentage_goal == 12
        assert user_goal.waist_cm_goal == 75

def test_body_composition_goals_update_us_measurements(auth_client):
    """
    GIVEN a logged-in user with US measurement system
    WHEN the user submits the goals form with new body composition goal data in US units
    THEN the UserGoal object should be updated with the correct converted values.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.has_completed_onboarding = True
        user.measurement_system = 'us'
        db.session.add(user)
        db.session.commit()

        # Ensure a UserGoal exists for this user
        initial_goal = UserGoal(
            user_id=user.id,
            calories=2000,
            protein=120,
            carbs=250,
            fat=70,
            weight_goal_kg=70,
            body_fat_percentage_goal=15,
            waist_cm_goal=80
        )
        db.session.add(initial_goal)
        db.session.commit()

    data_us = {
        'age': 30,
        'gender': 'Male',
        'height_ft': 5,
        'height_in': 11,
        'weight_lbs': 180,
        'calories': 2000,
        'protein': 120,
        'carbs': 250,
        'fat': 70,
        'weight_goal_lbs': 170,
        'body_fat_percentage_goal': 10,
        'waist_in_goal': 30
    }

    response_us = auth_client.post('/goals/', data=data_us, follow_redirects=True)
    assert response_us.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.weight_goal_kg == pytest.approx(77.11, abs=0.01) # 170 lbs to kg
        assert user_goal.body_fat_percentage_goal == 10
        assert user_goal.waist_cm_goal == pytest.approx(76.2, abs=0.01) # 30 inches to cm

def test_calculate_bmr_api(auth_client):
    """
    GIVEN a logged-in user
    WHEN a POST request is made to the /calculate-bmr endpoint
    THEN the API should return the correct BMR and formula.
    """
    # Test with Mifflin-St Jeor
    response = auth_client.post('/goals/calculate-bmr', json={
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'weight_kg': 80
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data['bmr'] == 1780
    assert data['formula'] == 'Mifflin-St Jeor'

    # Test with Katch-McArdle
    response = auth_client.post('/goals/calculate-bmr', json={
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'weight_kg': 80,
        'body_fat_percentage': 20
    })
    assert response.status_code == 200
    data = response.get_json()
    # LBM = 80 * (1 - 0.20) = 64 kg
    # BMR = 370 + (21.6 * 64) = 1752.4
    assert round(data['bmr']) == 1752
    assert data['formula'] == 'Katch-McArdle'