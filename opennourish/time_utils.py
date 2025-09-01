from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask_login import current_user
from flask import current_app

# --- Pure, Testable Functions ---


def get_user_today(user_timezone_str="UTC"):
    """Returns the current date for a given timezone string."""
    try:
        user_tz = ZoneInfo(user_timezone_str)
    except ZoneInfoNotFoundError:
        user_tz = ZoneInfo("UTC")
    return datetime.now(user_tz).date()


def to_user_timezone(utc_dt, user_timezone_str="UTC"):
    """Converts a UTC datetime object to a specific local timezone."""
    if not utc_dt:
        return None

    try:
        user_tz = ZoneInfo(user_timezone_str)
    except ZoneInfoNotFoundError:
        user_tz = ZoneInfo("UTC")

    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=ZoneInfo("UTC"))

    return utc_dt.astimezone(user_tz)


def to_utc(naive_dt, user_timezone_str="UTC"):
    """Converts a naive datetime from a user's timezone to UTC."""
    if not naive_dt:
        return None

    try:
        local_tz = ZoneInfo(user_timezone_str)
    except ZoneInfoNotFoundError:
        local_tz = ZoneInfo("UTC")

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

    try:
        ZoneInfo(user_tz_str)
    except ZoneInfoNotFoundError:
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
