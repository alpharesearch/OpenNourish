"""Coverage + regression tests for opennourish/settings/routes.py and forms.

Regression contract (opennourish/AGENTS.md Work Guidance): /set-timezone must
reject timezone strings the system cannot load, because the stored value is
later fed to ZoneInfo (fasting routes, time filters).
"""

import pytest

from models import db, User


def post_timezone(client, value):
    return client.post(
        "/settings/set-timezone", json={"timezone": value}, follow_redirects=False
    )


def test_set_timezone_accepts_valid_zone(auth_client, app_with_db):
    response = post_timezone(auth_client, "Europe/Berlin")
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    with app_with_db.app_context():
        assert User.query.filter_by(username="testuser").one().timezone == (
            "Europe/Berlin"
        )


@pytest.mark.parametrize(
    "bad_value",
    ["Not/AZone", "Etc/Unknown", "../../etc/passwd", "UTC+5", "123"],
)
def test_set_timezone_rejects_invalid_zone(auth_client, app_with_db, bad_value):
    response = post_timezone(auth_client, bad_value)
    assert response.status_code == 400
    body = response.get_json()
    assert body["status"] == "error"
    with app_with_db.app_context():
        # The stored value must not have been poisoned (default stays UTC).
        assert User.query.filter_by(username="testuser").one().timezone == "UTC"


def test_set_timezone_requires_value(auth_client):
    response = auth_client.post(
        "/settings/set-timezone", json={}, follow_redirects=False
    )
    assert response.status_code == 400


def test_settings_post_updates_profile(auth_client, app_with_db):
    response = auth_client.post(
        "/settings/",
        data={
            "email": "testuser@example.com",
            "age": "33",
            "gender": "Male",
            "measurement_system": "metric",
            "height_cm": "180",
            "navbar_preference": "bg-dark navbar-dark",
            "diary_default_view": "today",
            "theme_preference": "dark",
            "meals_per_day": "3",
            "week_start_day": "Monday",
            "timezone": "Europe/Berlin",
            "submit_settings": "Save Settings",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Your settings have been updated." in response.data
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        assert user.age == 33
        assert user.measurement_system == "us" or user.measurement_system == "metric"
        assert user.height_cm == 180.0
        assert user.meals_per_day == 3
        assert user.timezone == "Europe/Berlin"


def test_settings_post_us_height_conversion(auth_client, app_with_db):
    auth_client.post(
        "/settings/",
        data={
            "email": "testuser@example.com",
            "measurement_system": "us",
            "height_ft": "6",
            "height_in": "0",
            "navbar_preference": "bg-dark navbar-dark",
            "diary_default_view": "today",
            "theme_preference": "light",
            "meals_per_day": "4",
            "week_start_day": "Sunday",
            "timezone": "UTC",
            "submit_settings": "Save Settings",
        },
        follow_redirects=True,
    )
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        assert user.measurement_system == "us"
        assert user.height_cm is not None
        assert 180 < user.height_cm < 186  # 6ft = 182.88cm


def test_settings_email_validator_rejects_duplicate(app_with_db, auth_client):
    with app_with_db.app_context():
        other = User(username="dupe", email="dupe@example.com")
        other.set_password("password")
        db.session.add(other)
        db.session.commit()

    base = {
        "measurement_system": "metric",
        "navbar_preference": "bg-dark navbar-dark",
        "diary_default_view": "today",
        "theme_preference": "light",
        "meals_per_day": "3",
        "week_start_day": "Monday",
        "timezone": "UTC",
        "submit_settings": "Save Settings",
    }
    # Stealing another account's email must be rejected by the validator.
    response = auth_client.post(
        "/settings/", data={**base, "email": "DUPE@example.com"}, follow_redirects=True
    )
    assert b"This email is already registered." in response.data
    with app_with_db.app_context():
        assert User.query.filter_by(username="testuser").one().email == (
            "testuser@example.com"
        )


def test_settings_email_change_unverifies(app_with_db, auth_client):
    base = {
        "measurement_system": "metric",
        "navbar_preference": "bg-dark navbar-dark",
        "diary_default_view": "today",
        "theme_preference": "light",
        "meals_per_day": "3",
        "week_start_day": "Monday",
        "timezone": "UTC",
        "submit_settings": "Save Settings",
    }
    # A genuine change lowers is_verified (in one request session, the
    # production reality).
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        user.is_verified = True
        db.session.commit()
    response = auth_client.post(
        "/settings/",
        data={**base, "email": "fresh@example.com"},
        follow_redirects=True,
    )
    assert b"verification status has been reset" in response.data
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        assert user.email == "fresh@example.com"
        assert user.is_verified is False


def test_restart_onboarding(auth_client, app_with_db):
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        user.has_completed_onboarding = True
        db.session.commit()
    response = auth_client.post("/settings/restart-onboarding", follow_redirects=True)
    assert response.status_code == 200
    assert b"restarted the onboarding wizard" in response.data
    with app_with_db.app_context():
        assert (
            User.query.filter_by(username="testuser").one().has_completed_onboarding
            is False
        )


def test_delete_account_wrong_password_keeps_account(auth_client, app_with_db):
    response = auth_client.get("/settings/delete_confirm")
    assert response.status_code == 200
    response = auth_client.post(
        "/settings/delete",
        data={"password": "totally-wrong", "submit": "Delete Account"},
        follow_redirects=True,
    )
    assert b"Incorrect password." in response.data
    with app_with_db.app_context():
        assert User.query.filter_by(username="testuser").first() is not None


def test_delete_account_error_branch_rolls_back(auth_client, app_with_db, monkeypatch):
    """A storage error during deletion must flash, roll back, and keep the account."""
    from sqlalchemy.orm.scoping import scoped_session

    from models import MyFood

    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        db.session.add(
            MyFood(user_id=user.id, description="Keep Me", calories_per_100g=1)
        )
        db.session.commit()

    def boom(self, *args, **kwargs):
        raise RuntimeError("simulated storage failure")

    monkeypatch.setattr(scoped_session, "delete", boom)
    response = auth_client.post(
        "/settings/delete",
        data={"password": "password", "submit": "Delete Account"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"An error occurred during account deletion." in response.data
    monkeypatch.undo()
    with app_with_db.app_context():
        # The rollback must have discarded everything the route had staged,
        # including the bulk MyFood anonymization that ran before the failure.
        assert User.query.filter_by(username="testuser").first() is not None
        food = MyFood.query.filter_by(description="Keep Me").one()
        assert food.user_id is not None
