import pytest
from datetime import date
from opennourish.utils import calculate_bmi
from models import db, User, CheckIn, UserGoal


def test_calculate_bmi_valid():
    """Test BMI calculation with typical valid inputs."""
    # 100kg weight, 180cm height -> BMI = 100 / (1.8 * 1.8) = 30.86
    assert calculate_bmi(weight_kg=100, height_cm=180) == pytest.approx(30.86, 0.01)
    # 75kg weight, 175cm height -> BMI = 75 / (1.75 * 1.75) = 24.49
    assert calculate_bmi(weight_kg=75, height_cm=175) == pytest.approx(24.49, 0.01)


def test_calculate_bmi_invalid_inputs():
    """Test BMI calculation with invalid or edge-case inputs."""
    assert calculate_bmi(weight_kg=0, height_cm=180) is None
    assert calculate_bmi(weight_kg=100, height_cm=0) is None
    assert calculate_bmi(weight_kg=None, height_cm=180) is None
    assert calculate_bmi(weight_kg=100, height_cm=None) is None
    assert calculate_bmi(weight_kg=None, height_cm=None) is None


def test_goals_route_bmi_display(auth_client):
    """
    Test that the goals page correctly calculates and displays
    the user's current BMI and target BMI.
    """
    # Setup: Ensure user has necessary data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user.has_completed_onboarding = True
        user.height_cm = 180
        db.session.add(user)

        # Create a check-in for current BMI
        checkin = CheckIn(
            user_id=user.id, weight_kg=85, checkin_date=date.today()
        )  # BMI should be 85 / 1.8^2 = 26.2
        db.session.add(checkin)

        # Create a goal for target BMI
        goal = UserGoal(
            user_id=user.id, weight_goal_kg=75
        )  # Target BMI should be 75 / 1.8^2 = 23.1
        db.session.add(goal)
        db.session.commit()

    # Action: Access the goals page
    response = auth_client.get("/goals/")
    assert response.status_code == 200

    # Assertion: Check if the BMI values are in the rendered HTML
    # Current BMI: 26.2
    assert (
        b'Your estimated Body Mass Index (BMI) is: <strong id="bmi-value">26.2</strong>'
        in response.data
    )
    # Target BMI: 23.1
    assert b"(Target BMI: 23.1)" in response.data
