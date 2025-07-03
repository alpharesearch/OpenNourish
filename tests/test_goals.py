import pytest
from models import UserGoal, User, db

def test_set_goals_for_new_user(auth_client):
    """
    GIVEN a logged-in user with no existing goals
    WHEN the user submits the goals form
    THEN a new UserGoal object should be created
    """
    response = auth_client.post('/goals/goals', data={
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
    response = auth_client.post('/goals/goals', data={
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

        # Verify there's only one goal entry for the user
        goal_count = UserGoal.query.filter_by(user_id=user.id).count()
        assert goal_count == 1
