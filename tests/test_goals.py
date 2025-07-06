import pytest
from models import UserGoal, User, CheckIn, db
from datetime import date

def test_set_goals_for_new_user(auth_client):
    """
    GIVEN a logged-in user with no existing goals
    WHEN the user submits the goals form
    THEN a new UserGoal object should be created
    """
    response = auth_client.post('/goals', data={
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'calories': 2500,
        'protein': 150,
        'carbs': 300,
        'fat': 80
    }, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.calories == 2500
        assert user_goal.protein == 150
        assert user.age == 30
        assert user.gender == 'Male'
        assert user.height_cm == 180

def test_update_existing_goals(auth_client):
    """
    GIVEN a logged-in user with an existing goal
    WHEN the user submits the goals form with new data
    THEN the existing UserGoal object should be updated
    """
    with auth_client.application.app_context():
        # First, create an initial goal for the user
        user = User.query.filter_by(username='testuser').first()
        initial_goal = UserGoal(
            user_id=user.id,
            calories=2000,
            protein=120,
            carbs=250,
            fat=70
        )
        db.session.add(initial_goal)
        db.session.commit()
        initial_goal_id = initial_goal.id # Store the ID before the context exits

    # Now, post new data to update the goal
    response = auth_client.post('/goals', data={
        'age': 31,
        'gender': 'Female',
        'height_cm': 170,
        'calories': 2200,
        'protein': 140,
        'carbs': 280,
        'fat': 75
    }, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first() # Re-query user
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal is not None
        assert user_goal.calories == 2200
        assert user_goal.protein == 140
        assert user_goal.id == initial_goal_id  # Ensure it's an update, not a new entry
        assert user.age == 31
        assert user.gender == 'Female'
        assert user.height_cm == 170

        # Verify there's only one goal entry for the user
        goal_count = UserGoal.query.filter_by(user_id=user.id).count()
        assert goal_count == 1

def test_initial_checkin_creation_and_bmr_calculation(auth_client):
    """
    GIVEN a logged-in user with no existing check-in data
    WHEN the user submits the goals form with personal info and weight
    THEN a new CheckIn entry should be created and BMR should be calculated and displayed.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        # Ensure no existing check-ins for the test user
        CheckIn.query.filter_by(user_id=user.id).delete()
        db.session.commit()

    response = auth_client.post('/goals/', data={
        'age': 25,
        'gender': 'Male',
        'height_cm': 175,
        'weight_kg': 70,
        'body_fat_percentage': 15,
        'calories': 2000,
        'protein': 150,
        'carbs': 200,
        'fat': 60
    })
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        check_in = CheckIn.query.filter_by(user_id=user.id).first()
        assert check_in is not None
        assert check_in.weight_kg == 70
        assert check_in.body_fat_percentage == 15
        assert check_in.checkin_date == date.today()

        # Verify BMR calculation (Mifflin-St Jeor for Male: 10*70 + 6.25*175 - 5*25 + 5 = 700 + 1093.75 - 125 + 5 = 1673.75)
        # The template displays it as an integer, so check for approximate value
        assert b'Your estimated Basal Metabolic Rate (BMR) is: <strong>1674 kcal/day</strong>' in response.data

def test_diet_preset_prefills_form(auth_client):
    """
    GIVEN a logged-in user on the goals page
    WHEN a diet preset is selected (simulated via POST)
    THEN the form fields should be pre-filled with the preset values.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        # Ensure a UserGoal exists for the user
        user_goal = UserGoal(user_id=user.id, calories=100, protein=10, carbs=10, fat=10)
        db.session.add(user_goal)
        db.session.commit()

    response = auth_client.post('/goals', data={
        'age': 30,
        'gender': 'Male',
        'height_cm': 180,
        'diet_preset': 'Keto', # Select Keto preset
        'calories': '', # These will be overwritten by preset
        'protein': '',
        'carbs': '',
        'fat': ''
    }, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        assert user_goal.calories == 1800
        assert user_goal.protein == 100
        assert user_goal.carbs == 20
        assert user_goal.fat == 150