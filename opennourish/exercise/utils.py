from flask import flash
from flask_login import current_user
from models import CheckIn


def get_user_weight_kg(user_id=None):
    """Fetches the most recent weight for a given user or the current user."""
    if user_id is None:
        user_id = current_user.id

    last_checkin = (
        CheckIn.query.filter_by(user_id=user_id)
        .order_by(CheckIn.checkin_date.desc())
        .first()
    )
    if not last_checkin:
        # Avoid flashing a message if we are just checking for another user's weight silently
        if user_id == current_user.id:
            flash("Please add a weight check-in before logging an exercise.", "danger")
        return None
    return last_checkin.weight_kg


def calculate_calories_burned(activity, duration_minutes, user_weight_kg):
    """Calculates calories burned based on activity, duration, and user weight."""
    return (activity.met_value * user_weight_kg * 3.5) / 200 * duration_minutes
