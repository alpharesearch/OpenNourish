"""Coverage tests for ``opennourish/onboarding/routes.py``.

Covers the wizard end to end for a fresh user, the GET pre-population branches
for both measurement systems, the BMR-derived goal pre-fill, the validation
re-render paths, and the ``settings`` restart switch that puts a completed user
back in front of the wizard.

``auth_client`` is NOT onboarded; ``auth_client_onboarded`` is (with a
``UserGoal`` of 2000 kcal and ``default_fasting_hours=16``).
"""

import re

from models import db, CheckIn, User, UserGoal
from opennourish.time_utils import get_user_today
from opennourish.utils import cm_to_ft_in, cm_to_in, kg_to_lbs

TODAY = get_user_today("UTC")


def collapsed_text(response):
    return re.sub(r"\s+", " ", response.data.decode("utf-8"))


def flash_messages(client):
    with client.session_transaction() as sess:
        return [message for _, message in sess.get("_flashes", [])]


# ------------------------------------------------------------- wizard, happy path


def test_wizard_happy_path_ends_at_the_dashboard(auth_client, app_with_db):
    """Each step POSTs to the next one and the chain ends on the dashboard."""
    user = User.query.filter_by(username="testuser").first()

    step1 = auth_client.post(
        "/onboarding/step1",
        data={"measurement_system": "metric", "theme_preference": "dark"},
        follow_redirects=False,
    )
    assert step1.status_code == 302
    assert step1.headers["Location"].endswith("/onboarding/step2")

    step2 = auth_client.post(
        "/onboarding/step2",
        data={
            "age": 34,
            "gender": "Female",
            "height_cm": 168,
            "weight_kg": 72.5,
            "body_fat_percentage": 28,
            "waist_cm": 84,
        },
        follow_redirects=False,
    )
    assert step2.status_code == 302
    assert step2.headers["Location"].endswith("/onboarding/step3")

    step3 = auth_client.post(
        "/onboarding/step3",
        data={
            "goal_modifier": "maintain",
            "diet_preset": "Balanced",
            "calories": 1900,
            "protein": 130,
            "carbs": 210,
            "fat": 60,
            "weight_goal_kg": 68,
            "waist_cm_goal": 80,
            "body_fat_percentage_goal": 24,
        },
        follow_redirects=False,
    )
    assert step3.status_code == 302
    assert step3.headers["Location"].endswith("/onboarding/step4")
    assert "Onboarding complete! Welcome to OpenNourish." in flash_messages(auth_client)

    db.session.refresh(user)
    assert user.measurement_system == "metric"
    assert user.theme_preference == "dark"
    assert user.age == 34
    assert user.height_cm == 168
    assert user.has_completed_onboarding is True

    checkin = CheckIn.query.filter_by(user_id=user.id).one()
    assert checkin.weight_kg == 72.5
    assert checkin.waist_cm == 84
    assert checkin.checkin_date == TODAY

    goal = UserGoal.query.filter_by(user_id=user.id).one()
    assert goal.calories == 1900
    assert goal.diet_preset == "Balanced"
    assert goal.weight_goal_kg == 68

    step4 = auth_client.get("/onboarding/step4")
    assert step4.status_code == 200
    assert "Welcome to OpenNourish!" in step4.data.decode("utf-8")

    dashboard = auth_client.get("/dashboard/", follow_redirects=True)
    assert dashboard.status_code == 200
    assert "/dashboard" in dashboard.request.path
    # Content, not just status: @onboarding_required bounces would still be 200.
    assert "Nutritional Summary" in dashboard.data.decode("utf-8")
    assert "Step 1 of 3" not in dashboard.data.decode("utf-8")


def test_us_wizard_conversions_and_finish_onboarding(auth_client):
    """US units convert on save; ``finish_onboarding`` is the step-4 exit."""
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "us"
    db.session.commit()

    step2 = auth_client.post(
        "/onboarding/step2",
        data={
            "age": 41,
            "gender": "Male",
            "height_ft": 6,
            "height_in": 1,
            "weight_lbs": 190,
            "waist_in": 34,
        },
        follow_redirects=False,
    )
    assert step2.status_code == 302
    assert step2.headers["Location"].endswith("/onboarding/step3")

    db.session.refresh(user)
    assert round(user.height_cm) == 185  # 6'1"
    checkin = CheckIn.query.filter_by(user_id=user.id).one()
    assert round(checkin.weight_kg) == 86  # 190 lb
    assert round(checkin.waist_cm) == 86  # 34 in

    step3 = auth_client.post(
        "/onboarding/step3",
        data={
            "calories": 2400,
            "protein": 170,
            "carbs": 240,
            "fat": 75,
            "weight_goal_lbs": 175,
            "waist_in_goal": 32,
        },
        follow_redirects=False,
    )
    assert step3.status_code == 302
    goal = UserGoal.query.filter_by(user_id=user.id).one()
    assert round(goal.weight_goal_kg) == 79  # 175 lb
    assert round(goal.waist_cm_goal) == 81  # 32 in

    finish = auth_client.get("/onboarding/finish_onboarding", follow_redirects=False)
    assert finish.status_code == 302
    assert finish.headers["Location"].endswith("/dashboard/")

    dashboard = auth_client.get("/dashboard/", follow_redirects=True)
    assert "Nutritional Summary" in dashboard.data.decode("utf-8")


def test_finish_onboarding_is_idempotent(auth_client):
    """The first call completes and flashes; the second changes nothing."""
    user = User.query.filter_by(username="testuser").first()

    first = auth_client.get("/onboarding/finish_onboarding", follow_redirects=False)
    assert first.status_code == 302
    assert first.headers["Location"].endswith("/dashboard/")
    db.session.refresh(user)
    assert user.has_completed_onboarding is True
    assert flash_messages(auth_client) == [
        "Onboarding complete! Welcome to OpenNourish."
    ]

    second = auth_client.get("/onboarding/finish_onboarding", follow_redirects=False)
    assert second.status_code == 302
    # No second "complete" flash on the already-completed branch.
    assert flash_messages(auth_client) == [
        "Onboarding complete! Welcome to OpenNourish."
    ]


# ------------------------------------------------------------ pre-population


def test_step1_and_step2_and_step3_redirect_when_already_onboarded(
    auth_client_onboarded,
):
    for step in ("step1", "step2", "step3"):
        response = auth_client_onboarded.get(f"/onboarding/{step}")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/dashboard/")

    follow = auth_client_onboarded.get("/onboarding/step1", follow_redirects=True)
    assert "Nutritional Summary" in follow.data.decode("utf-8")


def test_step2_get_prepopulates_metric_from_latest_checkin(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    user.height_cm = 171.0
    user.age = 45
    user.gender = "Male"
    db.session.commit()
    db.session.add(
        CheckIn(
            user_id=user.id,
            checkin_date=TODAY,
            weight_kg=88.5,
            body_fat_percentage=24.5,
            waist_cm=95.0,
        )
    )
    db.session.commit()

    response = auth_client.get("/onboarding/step2")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Step 2 of 3" in body
    assert 'value="88.5"' in body
    assert 'value="95.0"' in body
    assert 'value="171.0"' in body
    assert 'value="24.5"' in body


def test_step2_get_prepopulates_us_from_latest_checkin(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "us"
    user.height_cm = 180.0
    db.session.commit()
    db.session.add(
        CheckIn(
            user_id=user.id,
            checkin_date=TODAY,
            weight_kg=81.0,
            body_fat_percentage=18.0,
            waist_cm=82.0,
        )
    )
    db.session.commit()

    response = auth_client.get("/onboarding/step2")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Height (ft/in)" in body
    assert f'value="{kg_to_lbs(81.0)}"' in body
    assert f'value="{cm_to_in(82.0)}"' in body
    ft, inch = cm_to_ft_in(180.0)
    assert f'value="{ft}"' in body
    assert f'value="{inch}"' in body


def test_step2_post_without_weight_creates_no_checkin(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    db.session.commit()

    response = auth_client.post(
        "/onboarding/step2",
        data={"age": 22, "gender": "Female", "height_cm": 160},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/onboarding/step3")
    assert CheckIn.query.filter_by(user_id=user.id).count() == 0


def test_step3_get_prepopulates_metric_goal(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    db.session.commit()
    db.session.add(
        UserGoal(
            user_id=user.id,
            goal_modifier="moderate_loss",
            diet_preset="Low Carb",
            calories=1750.0,
            protein=140.0,
            carbs=120.0,
            fat=70.0,
            weight_goal_kg=70.0,
            waist_cm_goal=85.0,
            body_fat_percentage_goal=20.0,
        )
    )
    db.session.commit()

    response = auth_client.get("/onboarding/step3")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Step 3 of 3" in body
    assert 'value="1750.0"' in body
    assert 'value="70.0"' in body
    assert 'value="85.0"' in body


def test_step3_get_prepopulates_us_goal(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "us"
    db.session.commit()
    db.session.add(
        UserGoal(
            user_id=user.id,
            calories=2100.0,
            protein=150.0,
            carbs=200.0,
            fat=65.0,
            weight_goal_kg=75.0,
            waist_cm_goal=80.0,
        )
    )
    db.session.commit()

    response = auth_client.get("/onboarding/step3")

    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert f'value="{kg_to_lbs(75.0)}"' in body
    assert f'value="{cm_to_in(80.0)}"' in body


def test_step3_get_prefills_goals_calculated_from_bmr(auth_client):
    """With no stored goal the wizard must pre-fill the BMR-derived macros."""
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    user.age = 30
    user.gender = "Male"
    user.height_cm = 180.0
    db.session.commit()
    db.session.add(CheckIn(user_id=user.id, checkin_date=TODAY, weight_kg=80.0))
    db.session.commit()

    response = auth_client.get("/onboarding/step3")

    assert response.status_code == 200
    text = collapsed_text(response)
    # Mifflin-St Jeor: 10*80 + 6.25*180 - 5*30 + 5 = 1780 kcal.
    assert "Mifflin-St Jeor" in text
    assert 'value="1780"' in text


# ------------------------------------------------------- validation failures


def test_step2_validation_failure_renders_step2_again(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    db.session.commit()

    response = auth_client.post(
        "/onboarding/step2",
        data={"age": 200, "gender": "Female", "height_cm": 170},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.request.path == "/onboarding/step2"
    body = response.data.decode("utf-8")
    assert "Step 2 of 3" in body
    # The wizard re-rendered instead of redirecting, and nothing was written.
    assert b"Step 2 of 3: Personal Information" in response.data
    db.session.refresh(user)
    assert user.age is None
    assert CheckIn.query.filter_by(user_id=user.id).count() == 0


def test_step3_validation_failure_keeps_onboarding_incomplete(auth_client):
    user = User.query.filter_by(username="testuser").first()
    user.measurement_system = "metric"
    db.session.commit()

    response = auth_client.post(
        "/onboarding/step3",
        data={"calories": 100, "protein": 150, "carbs": 200, "fat": 60},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.request.path == "/onboarding/step3"
    assert "Step 3 of 3" in response.data.decode("utf-8")
    db.session.refresh(user)
    assert user.has_completed_onboarding is False
    assert UserGoal.query.filter_by(user_id=user.id).count() == 0


# --------------------------------------------------------------- restart path


def test_restart_onboarding_sends_user_back_to_the_wizard(auth_client_onboarded):
    user = User.query.filter_by(username="onboardeduser").first()
    assert user.has_completed_onboarding is True

    response = auth_client_onboarded.post(
        "/settings/restart-onboarding", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/onboarding/step1")
    assert "You have restarted the onboarding wizard." in flash_messages(
        auth_client_onboarded
    )

    db.session.refresh(user)
    assert user.has_completed_onboarding is False

    # A protected page now redirects back into the wizard, and the wizard is
    # really what renders (a 200 alone would also pass through the bounce).
    bounce = auth_client_onboarded.get("/dashboard/", follow_redirects=False)
    assert bounce.status_code == 302
    assert bounce.headers["Location"].endswith("/onboarding/step1")

    landing = auth_client_onboarded.get("/dashboard/", follow_redirects=True)
    assert landing.status_code == 200
    assert "/onboarding/step1" in landing.request.path
    assert "Step 1 of 3" in landing.data.decode("utf-8")

    # The stored goal survives the restart and pre-fills step 3 again.
    step3 = auth_client_onboarded.get("/onboarding/step3")
    assert step3.status_code == 200
    assert 'value="2000.0"' in step3.data.decode("utf-8")
