from models import db, User, UserGoal, CheckIn
from datetime import date


# Helper function to register and log in a new user
def register_and_login(client, username, password):
    client.post(
        "/auth/register",
        data={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "password2": password,
        },
        follow_redirects=True,
    )
    user = User.query.filter_by(username=username).first()
    if user:
        db.session.refresh(user)
    return user


# Test for Step 1: Measurement System
def test_onboarding_step1_get(client):
    register_and_login(client, "onboard_user_1", "password")
    response = client.get("/onboarding/step1")
    assert response.status_code == 200
    assert b"Step 1 of 3: Choose Your Measurement System" in response.data


def test_onboarding_step1_post(client):
    user = register_and_login(client, "onboard_user_2", "password")
    response = client.post(
        "/onboarding/step1",
        data={
            "email": "onboard_user_2@example.com",
            "measurement_system": "us",
            "theme_preference": "dark",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step2" in response.request.path
    db.session.refresh(user)
    assert user.measurement_system == "us"
    assert user.theme_preference == "dark"


def test_onboarding_redirect_if_completed(client):
    user = register_and_login(client, "completed_user", "password")
    user.has_completed_onboarding = True
    db.session.add(user)
    db.session.commit()

    response = client.get("/onboarding/step1", follow_redirects=True)
    assert "/dashboard" in response.request.path


# Test for Step 2: Personal Information
def test_onboarding_step2_get_metric(client):
    user = register_and_login(client, "metric_user", "password")
    user.measurement_system = "metric"
    db.session.add(user)
    db.session.commit()

    response = client.get("/onboarding/step2")
    assert response.status_code == 200
    assert b"Height (cm)" in response.data
    assert b"Weight (kg)" in response.data


def test_onboarding_step2_get_us(client):
    user = register_and_login(client, "us_user", "password")
    user.measurement_system = "us"
    db.session.add(user)
    db.session.commit()

    response = client.get("/onboarding/step2")
    assert response.status_code == 200
    assert b"Height (ft/in)" in response.data
    assert b"Weight (lbs)" in response.data


def test_onboarding_step2_post_metric(client):
    user = register_and_login(client, "metric_user_2", "password")
    user.measurement_system = "metric"
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/onboarding/step2",
        data={
            "age": 30,
            "gender": "Female",
            "height_cm": 170,
            "weight_kg": 65,
            "body_fat_percentage": 25,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step3" in response.request.path
    db.session.refresh(user)
    assert user.age == 30
    assert user.gender == "Female"
    assert user.height_cm == 170

    checkin = CheckIn.query.filter_by(user_id=user.id).first()
    assert checkin is not None
    assert checkin.weight_kg == 65
    assert checkin.body_fat_percentage == 25


def test_onboarding_step2_post_us(client):
    user = register_and_login(client, "us_user_2", "password")
    user.measurement_system = "us"
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/onboarding/step2",
        data={
            "age": 28,
            "gender": "Male",
            "height_ft": 5,
            "height_in": 10,
            "weight_lbs": 180,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step3" in response.request.path
    db.session.refresh(user)
    assert user.age == 28
    assert user.gender == "Male"
    assert round(user.height_cm) == 178  # 5'10" is approx 177.8 cm

    checkin = CheckIn.query.filter_by(user_id=user.id).first()
    assert checkin is not None
    assert round(checkin.weight_kg) == 82  # 180 lbs is approx 81.65 kg


# Test for Step 3: Initial Goals
def test_onboarding_step3_get(client):
    user = register_and_login(client, "goals_user", "password")
    user.measurement_system = "metric"
    user.age = 30
    user.gender = "Male"
    user.height_cm = 180
    db.session.add(user)
    db.session.add(CheckIn(user_id=user.id, checkin_date=date.today(), weight_kg=80))
    db.session.commit()

    response = client.get("/onboarding/step3")
    assert response.status_code == 200
    assert b"Set Your Initial Goals" in response.data
    assert b"Your estimated Basal Metabolic Rate (BMR) is:" in response.data


def test_onboarding_step3_post(client):
    user = register_and_login(client, "goals_user_2", "password")
    user.measurement_system = "metric"
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/onboarding/step3",
        data={
            "calories": 2000,
            "protein": 150,
            "carbs": 200,
            "fat": 80,
            "weight_goal_kg": 75,
        },
        follow_redirects=False,  # Do not follow the redirect yet
    )
    assert response.status_code == 302  # Check for redirect

    # Check for flash message in the session
    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Onboarding complete! Welcome to OpenNourish."

    # Now follow the redirect
    response = client.get(response.headers["Location"], follow_redirects=True)
    assert response.status_code == 200
    assert "/onboarding/step4" in response.request.path

    db.session.refresh(user)
    assert user.has_completed_onboarding is True
    user_goal = UserGoal.query.filter_by(user_id=user.id).first()
    assert user_goal is not None
    assert user_goal.calories == 2000
    assert user_goal.protein == 150
    assert user_goal.weight_goal_kg == 75


# Full workflow test
def test_full_onboarding_workflow(client):
    # Step 0: Register
    response = client.post(
        "/auth/register",
        data={
            "username": "full_workflow_user",
            "email": "full_workflow_user@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step1" in response.request.path

    # Step 1: Measurement System
    response = client.post(
        "/onboarding/step1",
        data={
            "email": "full_workflow_user@example.com",
            "measurement_system": "us",
            "theme_preference": "light",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step2" in response.request.path

    # Step 2: Personal Info
    response = client.post(
        "/onboarding/step2",
        data={
            "age": 35,
            "gender": "Female",
            "height_ft": 5,
            "height_in": 5,
            "weight_lbs": 150,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "/onboarding/step3" in response.request.path

    # Step 3: Goals
    response = client.post(
        "/onboarding/step3",
        data={
            "calories": 1800,
            "protein": 120,
            "carbs": 180,
            "fat": 60,
            "weight_goal_lbs": 140,
            "body_fat_percentage_goal": 20,
            "waist_in_goal": 30,
        },
        follow_redirects=False,  # Do not follow redirect
    )
    assert response.status_code == 302

    # Check for flash message
    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Onboarding complete! Welcome to OpenNourish."

    # Follow redirect
    response = client.get(response.headers["Location"], follow_redirects=True)
    assert response.status_code == 200
    assert "/onboarding/step4" in response.request.path

    # Verify user state
    user = User.query.filter_by(username="full_workflow_user").first()
    assert user.has_completed_onboarding is True
    assert user.measurement_system == "us"
    assert round(user.height_cm) == 165  # 5'5"

    checkin = (
        CheckIn.query.filter_by(user_id=user.id)
        .order_by(CheckIn.checkin_date.desc())
        .first()
    )
    assert round(checkin.weight_kg) == 68  # 150 lbs

    goal = UserGoal.query.filter_by(user_id=user.id).first()
    assert goal.calories == 1800
    assert round(goal.weight_goal_kg) == 64  # 140 lbs
