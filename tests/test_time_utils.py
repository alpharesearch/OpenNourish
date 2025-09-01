import pytest
from datetime import datetime, date, timezone
from flask_login import login_user

from opennourish.time_utils import (
    get_user_today,
    to_user_timezone,
    to_utc,
    get_start_of_week,
)
from models import User, db

# ---
# Tests for Pure Functions
# ---


def test_get_start_of_week():
    """Test the get_start_of_week function."""
    # Test with a Wednesday
    wednesday = date(2025, 7, 30)

    # Test with Monday as the start of the week
    assert get_start_of_week(wednesday, "Monday") == date(2025, 7, 28)

    # Test with Sunday as the start of the week
    assert get_start_of_week(wednesday, "Sunday") == date(2025, 7, 27)

    # Test with Saturday as the start of the week
    assert get_start_of_week(wednesday, "Saturday") == date(2025, 7, 26)


def test_get_user_today_with_timezone(monkeypatch):
    """Test get_user_today with a specific timezone."""
    mock_now_utc = datetime(2025, 7, 30, 2, 0, 0, tzinfo=timezone.utc)

    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return mock_now_utc.astimezone(tz) if tz else mock_now_utc

    monkeypatch.setattr("opennourish.time_utils.datetime", MockDateTime)
    today = get_user_today(user_timezone_str="America/New_York")
    assert today == date(2025, 7, 29)


def test_get_user_today_utc(monkeypatch):
    """Test get_user_today with the default UTC timezone."""
    mock_now_utc = datetime(2025, 7, 30, 2, 0, 0, tzinfo=timezone.utc)

    class MockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return mock_now_utc.astimezone(tz) if tz else mock_now_utc

    monkeypatch.setattr("opennourish.time_utils.datetime", MockDateTime)
    today = get_user_today()
    assert today == date(2025, 7, 30)


def test_to_user_timezone():
    """Test converting a UTC datetime to a specific timezone."""
    utc_dt = datetime(2025, 7, 29, 12, 0, 0)
    local_dt = to_user_timezone(utc_dt, user_timezone_str="America/New_York")
    assert local_dt.tzinfo.key == "America/New_York"
    assert local_dt.hour == 8


def test_to_utc():
    """Test converting a naive local datetime to UTC."""
    naive_local_dt = datetime(2025, 7, 29, 8, 0, 0)
    utc_dt = to_utc(naive_local_dt, user_timezone_str="America/New_York")
    assert utc_dt.tzinfo.key == "UTC"
    assert utc_dt.hour == 12


def test_invalid_timezone_fallback():
    """Test that an invalid timezone string falls back to UTC."""
    utc_dt = datetime(2025, 7, 29, 12, 0, 0)
    local_dt = to_user_timezone(utc_dt, user_timezone_str="Invalid/Timezone")
    assert local_dt.tzinfo.key == "UTC"
    assert local_dt.hour == 12


# ---
# Tests for Flask-aware Jinja Filters
# ---


@pytest.fixture
def logged_in_user_with_timezone(app_with_db):
    """Creates and logs in a user with a specific timezone."""
    with app_with_db.app_context():
        user = User(
            username="testuser_tz",
            email="test_tz@example.com",
            timezone="America/New_York",
        )
        user.set_password("password")
        db.session.add(user)
        db.session.commit()

        with app_with_db.test_request_context("/"):
            login_user(user)
            yield user


@pytest.fixture
def logged_in_user_invalid_tz(app_with_db):
    """Creates and logs in a user with an invalid timezone."""
    with app_with_db.app_context():
        user = User(
            username="testuser_invalid_tz",
            email="test_invalid_tz@example.com",
            timezone="Invalid/Zone",
        )
        user.set_password("password")
        db.session.add(user)
        db.session.commit()

        with app_with_db.test_request_context("/"):
            login_user(user)
            yield user


def test_jinja_filters_with_timezone(app_with_db, logged_in_user_with_timezone):
    """Test Jinja filters with a logged-in user who has a valid timezone."""
    app = app_with_db
    utc_dt = datetime(2025, 7, 29, 12, 0, 0)

    with app.test_request_context("/"):
        login_user(logged_in_user_with_timezone)
        rendered_time = app.jinja_env.from_string("{{ my_date | user_time }}").render(
            my_date=utc_dt
        )
        rendered_date = app.jinja_env.from_string("{{ my_date | user_date }}").render(
            my_date=utc_dt
        )

        assert rendered_time == "2025-07-29 08:00:00"
        assert rendered_date == "2025-07-29"


def test_jinja_filters_unauthenticated(app_with_db):
    """Test Jinja filters for an unauthenticated user (should default to UTC)."""
    app = app_with_db
    utc_dt = datetime(2025, 7, 29, 12, 0, 0)

    with app.test_request_context("/"):
        rendered_time = app.jinja_env.from_string("{{ my_date | user_time }}").render(
            my_date=utc_dt
        )
        assert rendered_time == "2025-07-29 12:00:00"


def test_jinja_filters_invalid_tz_fallback(
    app_with_db, logged_in_user_invalid_tz, caplog
):
    """Test that Jinja filters fall back to UTC and log a warning for an invalid timezone."""
    app = app_with_db
    utc_dt = datetime(2025, 7, 29, 12, 0, 0)

    with app.test_request_context("/"):
        login_user(logged_in_user_invalid_tz)
        rendered_time = app.jinja_env.from_string("{{ my_date | user_time }}").render(
            my_date=utc_dt
        )

        # Should fall back to UTC
        assert rendered_time == "2025-07-29 12:00:00"

        # Check that a warning was logged
        assert "Invalid timezone 'Invalid/Zone'" in caplog.text
        assert "Falling back to UTC" in caplog.text
