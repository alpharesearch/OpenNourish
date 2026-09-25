from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask_login import current_user
from flask import current_app

# --- Pure, Testable Functions ---


def utcnow_naive():
    """Return the current UTC time as a *naive* datetime.

    Naive UTC is the currency of every ``db.DateTime`` column in this app: the
    values are written naive (``fasting/routes.py`` calls it "Store as naive
    UTC") and read back naive, and pages compare them against a server-supplied
    ``now`` — ``fasting/fasting.html`` and ``dashboard.html`` both do
    ``(now - active_fast.start_time).total_seconds()``. Handing those templates
    an *aware* ``now`` raises ``TypeError: can't subtract offset-naive and
    offset-aware datetimes``, which surfaces as a 500 on both pages. Writing an
    aware value does not fix that either: SQLite drops ``tzinfo`` silently on
    the way in (measured on SQLAlchemy 2.0.54 — even a ``DateTime(timezone=True)``
    column reads back naive), so an aware value only *looks* stored.

    ``datetime.utcnow()`` said this same thing and is deprecated on 3.12, so
    ruff's ``DTZ003`` bans it outright. Reach for this instead of
    ``datetime.now(timezone.utc)`` whenever the value is stored or compared with
    something stored; use ``datetime.now(timezone.utc)`` only for an aware-only
    comparison like ``fasting/routes.py:114``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_valid_timezone(user_timezone_str=None):
    """Return True when user_timezone_str names a zone this system can load.

    Missing and unusable values return False instead of raising: the column can
    hold None, and a browser's `Intl` API can report names such as
    ``Etc/Unknown`` or a relative-path-looking string that ``ZoneInfo`` rejects
    with something other than ``ZoneInfoNotFoundError``.
    """
    if not isinstance(user_timezone_str, str) or not user_timezone_str:
        return False
    try:
        ZoneInfo(user_timezone_str)
    except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
        return False
    return True


def resolve_timezone(user_timezone_str="UTC"):
    """Return a ZoneInfo for a user timezone string, falling back to UTC.

    Never raises, so request handlers can pass whatever is stored on the user
    row. ZoneInfo caches its instances, so calling this per request is cheap.
    """
    if is_valid_timezone(user_timezone_str):
        return ZoneInfo(user_timezone_str)
    return ZoneInfo("UTC")


def get_user_today(user_timezone_str="UTC"):
    """Returns the current date for a given timezone string."""
    return datetime.now(resolve_timezone(user_timezone_str)).date()


def to_user_timezone(utc_dt, user_timezone_str="UTC"):
    """Converts a UTC datetime object to a specific local timezone."""
    if not utc_dt:
        return None

    user_tz = resolve_timezone(user_timezone_str)

    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=ZoneInfo("UTC"))

    return utc_dt.astimezone(user_tz)


def to_utc(naive_dt, user_timezone_str="UTC"):
    """Converts a naive datetime from a user's timezone to UTC."""
    if not naive_dt:
        return None

    local_tz = resolve_timezone(user_timezone_str)

    local_dt = naive_dt.replace(tzinfo=local_tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


def get_start_of_week(today, start_day="Monday"):
    """Calculates the start of the week for a given date."""
    if start_day == "Sunday":
        # In Python, Sunday is 6, but we want it to be the start.
        start_of_week_offset = (today.weekday() + 1) % 7
    elif start_day == "Saturday":
        start_of_week_offset = (today.weekday() + 2) % 7
    else:  # Default to Monday
        start_of_week_offset = today.weekday()

    return today - timedelta(days=start_of_week_offset)


# --- Flask-aware Jinja Filters ---


def _get_user_timezone_for_filter():
    """
    Gets the timezone string from the current user for Jinja filters.
    It defaults to UTC and logs a warning for invalid timezones.
    """
    user_tz_str = "UTC"
    if (
        current_user.is_authenticated
        and hasattr(current_user, "timezone")
        and current_user.timezone
    ):
        user_tz_str = current_user.timezone

    if not is_valid_timezone(user_tz_str):
        current_app.logger.warning(
            f"Invalid timezone '{user_tz_str}' for user {getattr(current_user, 'id', 'anonymous')}. "
            "Falling back to UTC for formatting."
        )
        user_tz_str = "UTC"  # Fallback

    return user_tz_str


def user_time_format(utc_dt, format="%Y-%m-%d %H:%M:%S"):
    """Jinja2 filter to format a UTC datetime into the user's local time string."""
    user_tz_str = _get_user_timezone_for_filter()
    local_dt = to_user_timezone(utc_dt, user_timezone_str=user_tz_str)
    return local_dt.strftime(format) if local_dt else ""


def user_date_format(utc_dt, format="%Y-%m-%d"):
    """Jinja2 filter to format a UTC datetime into the user's local date string."""
    user_tz_str = _get_user_timezone_for_filter()
    local_dt = to_user_timezone(utc_dt, user_timezone_str=user_tz_str)
    return local_dt.strftime(format) if local_dt else ""


def register_template_filters(app):
    """Registers the custom template filters with the Flask app."""
    app.jinja_env.filters["user_time"] = user_time_format
    app.jinja_env.filters["user_date"] = user_date_format
