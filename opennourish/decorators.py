from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)

    return decorated_function


def key_user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not (
            current_user.is_admin or current_user.is_key_user
        ):
            flash("This action requires special privileges.", "danger")
            return redirect(request.referrer or url_for("dashboard.index"))
        return f(*args, **kwargs)

    return decorated_function


def onboarding_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and not current_user.has_completed_onboarding:
            flash("Please complete the onboarding process.", "info")
            return redirect(url_for("onboarding.step1"))
        return f(*args, **kwargs)

    return decorated_function
