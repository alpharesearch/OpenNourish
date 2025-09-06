from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from opennourish.decorators import admin_required
from . import admin_bp
from .forms import AdminSettingsForm, EmailSettingsForm
import os
from models import (
    db,
    User,
    Recipe,
    MyFood,
    MyMeal,
    DailyLog,
    ExerciseLog,
    SystemSetting,
    RecipeIngredient,
    MyMealItem,
)
from opennourish.utils import encrypt_value


USER_NOT_FOUND_MSG = "User not found."
ADMIN_USERS_ROUTE = "admin.users"


@admin_bp.route("/")
@login_required
@admin_required
def index():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    total_users = db.session.query(User).count()
    total_recipes = db.session.query(Recipe).count()
    public_recipes = db.session.query(Recipe).filter_by(is_public=True).count()
    total_my_foods = db.session.query(MyFood).count()
    total_daily_logs = db.session.query(DailyLog).count()
    total_exercise_logs = db.session.query(ExerciseLog).count()
    recent_users = db.session.query(User).order_by(User.id.desc()).limit(5).all()

    context = {
        "total_users": total_users,
        "total_recipes": total_recipes,
        "public_recipes": public_recipes,
        "total_my_foods": total_my_foods,
        "total_daily_logs": total_daily_logs,
        "total_exercise_logs": total_exercise_logs,
        "recent_users": recent_users,
    }
    return render_template("admin/dashboard.html", **context)


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    form = AdminSettingsForm()
    if form.validate_on_submit():
        # When the form is submitted and valid, update the setting
        allow_registration_setting = SystemSetting.query.filter_by(
            key="allow_registration"
        ).first()

        # The data from the BooleanField is True or False
        new_value = str(form.allow_registration.data)

        if not allow_registration_setting:
            # If the setting doesn't exist, create it
            allow_registration_setting = SystemSetting(
                key="allow_registration", value=new_value
            )
            db.session.add(allow_registration_setting)
        else:
            # If it exists, update its value
            allow_registration_setting.value = new_value

        db.session.commit()
        flash("Settings have been saved.", "success")
        return redirect(url_for("admin.settings"))

    # For a GET request, populate the form with the current setting from the database
    allow_registration_setting = SystemSetting.query.filter_by(
        key="allow_registration"
    ).first()
    if allow_registration_setting:
        # The value in the DB is 'True' or 'False', so convert it back to a boolean for the form
        form.allow_registration.data = (
            allow_registration_setting.value.lower() == "true"
        )
    else:
        # Default to True if the setting is not in the database yet
        form.allow_registration.data = True

    return render_template("admin/settings.html", title="Admin Settings", form=form)


@admin_bp.route("/email", methods=["GET", "POST"])
@login_required
@admin_required
def email_settings():
    form = EmailSettingsForm()
    if form.validate_on_submit():
        current_app.logger.debug(
            "EmailSettingsForm validated successfully. Entering submission block."
        )
        # Always save the source selection
        source_setting = SystemSetting.query.filter_by(key="MAIL_CONFIG_SOURCE").first()
        if not source_setting:
            source_setting = SystemSetting(
                key="MAIL_CONFIG_SOURCE", value=form.MAIL_CONFIG_SOURCE.data
            )
            db.session.add(source_setting)
        else:
            source_setting.value = form.MAIL_CONFIG_SOURCE.data

        # These settings are only saved for 'database' mode, but we can save them anyway.
        # The app's startup logic in __init__.py will decide whether to use them.
        settings_to_save = {
            "MAIL_SERVER": form.MAIL_SERVER.data or "",
            "MAIL_PORT": str(form.MAIL_PORT.data)
            if form.MAIL_PORT.data is not None
            else "587",
            "MAIL_SECURITY_PROTOCOL": form.MAIL_SECURITY_PROTOCOL.data,
            "MAIL_USERNAME": form.MAIL_USERNAME.data or "",
            "MAIL_PASSWORD": form.MAIL_PASSWORD.data or "",
            "MAIL_FROM": form.MAIL_FROM.data or "no-reply@example.com",
            "MAIL_SUPPRESS_SEND": str(form.MAIL_SUPPRESS_SEND.data),
            "ENABLE_PASSWORD_RESET": str(form.ENABLE_PASSWORD_RESET.data),
            "ENABLE_EMAIL_VERIFICATION": str(form.ENABLE_EMAIL_VERIFICATION.data),
        }

        mail_use_tls = form.MAIL_SECURITY_PROTOCOL.data == "tls"
        mail_use_ssl = form.MAIL_SECURITY_PROTOCOL.data == "ssl"
        settings_to_save["MAIL_USE_TLS"] = str(mail_use_tls)
        settings_to_save["MAIL_USE_SSL"] = str(mail_use_ssl)

        for key, value in settings_to_save.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            value_to_save = value
            if key == "MAIL_PASSWORD" and value:
                encrypted_value = encrypt_value(
                    value, current_app.config["ENCRYPTION_KEY"]
                )
                value_to_save = encrypted_value

            if not setting:
                setting = SystemSetting(key=key, value=value_to_save)
                db.session.add(setting)
            else:
                setting.value = value_to_save
        db.session.commit()

        # Immediately reload the app's config to reflect the changes
        current_app.config["MAIL_CONFIG_SOURCE"] = form.MAIL_CONFIG_SOURCE.data
        if current_app.config["MAIL_CONFIG_SOURCE"] == "database":
            current_app.config.update(
                MAIL_SERVER=settings_to_save["MAIL_SERVER"],
                MAIL_PORT=int(settings_to_save["MAIL_PORT"])
                if settings_to_save["MAIL_PORT"]
                else 587,
                MAIL_USE_TLS=mail_use_tls,
                MAIL_USE_SSL=mail_use_ssl,
                MAIL_USERNAME=settings_to_save["MAIL_USERNAME"],
                MAIL_PASSWORD=settings_to_save["MAIL_PASSWORD"],
                MAIL_FROM=settings_to_save["MAIL_FROM"],
                MAIL_SUPPRESS_SEND=settings_to_save["MAIL_SUPPRESS_SEND"].lower()
                == "true",
                ENABLE_PASSWORD_RESET=settings_to_save["ENABLE_PASSWORD_RESET"].lower()
                == "true",
                ENABLE_EMAIL_VERIFICATION=settings_to_save[
                    "ENABLE_EMAIL_VERIFICATION"
                ].lower()
                == "true",
            )
        else:  # Reload from environment
            current_app.config.update(
                MAIL_SERVER=os.getenv("MAIL_SERVER", ""),
                MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
                MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "False").lower() == "true",
                MAIL_USE_SSL=os.getenv("MAIL_USE_SSL", "False").lower() == "true",
                MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
                MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
                MAIL_FROM=os.getenv("MAIL_FROM", "no-reply@example.com"),
                MAIL_SUPPRESS_SEND=os.getenv("MAIL_SUPPRESS_SEND", "True").lower()
                == "true",
                ENABLE_PASSWORD_RESET=os.getenv(
                    "ENABLE_PASSWORD_RESET", "False"
                ).lower()
                == "true",
                ENABLE_EMAIL_VERIFICATION=os.getenv(
                    "ENABLE_EMAIL_VERIFICATION", "False"
                ).lower()
                == "true",
            )

        flash(
            "Email settings have been saved. A restart may be required for all changes to take effect.",
            "success",
        )
        return redirect(url_for("admin.email_settings"))
    else:
        current_app.logger.debug(
            f"EmailSettingsForm validation failed. Errors: {form.errors}"
        )

    # Populate form for GET requests, always showing the values from the database.
    from config import get_setting_from_db

    form.MAIL_CONFIG_SOURCE.data = get_setting_from_db(
        current_app, "MAIL_CONFIG_SOURCE", "environment"
    )
    form.MAIL_SERVER.data = get_setting_from_db(current_app, "MAIL_SERVER", "")
    mail_port_from_db = get_setting_from_db(current_app, "MAIL_PORT", 587)
    form.MAIL_PORT.data = int(mail_port_from_db) if mail_port_from_db else None

    if get_setting_from_db(current_app, "MAIL_USE_TLS", "False").lower() == "true":
        form.MAIL_SECURITY_PROTOCOL.data = "tls"
    elif get_setting_from_db(current_app, "MAIL_USE_SSL", "False").lower() == "true":
        form.MAIL_SECURITY_PROTOCOL.data = "ssl"
    else:
        form.MAIL_SECURITY_PROTOCOL.data = "none"

    form.MAIL_USERNAME.data = get_setting_from_db(current_app, "MAIL_USERNAME", "")
    form.MAIL_FROM.data = get_setting_from_db(current_app, "MAIL_FROM", "")
    form.MAIL_SUPPRESS_SEND.data = (
        get_setting_from_db(current_app, "MAIL_SUPPRESS_SEND", "False").lower()
        == "true"
    )
    form.ENABLE_PASSWORD_RESET.data = (
        get_setting_from_db(current_app, "ENABLE_PASSWORD_RESET", "False").lower()
        == "true"
    )
    form.ENABLE_EMAIL_VERIFICATION.data = (
        get_setting_from_db(current_app, "ENABLE_EMAIL_VERIFICATION", "False").lower()
        == "true"
    )
    NOT_SET = "Not Set"
    # Pass environment variables to the template for display purposes
    env_vars = {
        "MAIL_SERVER": os.getenv("MAIL_SERVER", NOT_SET),
        "MAIL_PORT": os.getenv("MAIL_PORT", NOT_SET),
        "MAIL_USE_TLS": os.getenv("MAIL_USE_TLS", NOT_SET),
        "MAIL_USE_SSL": os.getenv("MAIL_USE_SSL", NOT_SET),
        "MAIL_USERNAME": os.getenv("MAIL_USERNAME", NOT_SET),
        "MAIL_PASSWORD": "********" if os.getenv("MAIL_PASSWORD") else NOT_SET,
        "MAIL_FROM": os.getenv("MAIL_FROM", NOT_SET),
        "MAIL_SUPPRESS_SEND": os.getenv("MAIL_SUPPRESS_SEND", NOT_SET),
        "ENABLE_PASSWORD_RESET": os.getenv("ENABLE_PASSWORD_RESET", NOT_SET),
        "ENABLE_EMAIL_VERIFICATION": os.getenv("ENABLE_EMAIL_VERIFICATION", NOT_SET),
    }

    return render_template(
        "admin/email_settings.html",
        title="Email Settings",
        form=form,
        env_vars=env_vars,
    )


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    users = User.query.paginate(page=page, per_page=20)
    return render_template("admin/users.html", users=users, title="User Management")


@admin_bp.route("/users/<int:user_id>/make-key-user", methods=["POST"])
@login_required
@admin_required
def make_key_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_key_user = True
        db.session.commit()
        flash(f"User {user.username} has been made a key user.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/remove-key-user", methods=["POST"])
@login_required
@admin_required
def remove_key_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_key_user = False
        db.session.commit()
        flash(f"User {user.username} is no longer a key user.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/disable", methods=["POST"])
@login_required
@admin_required
def disable_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        if user.id == current_user.id:
            flash("You cannot disable your own account.", "danger")
        else:
            user.is_active = False
            db.session.commit()
            flash(f"User {user.username} has been disabled.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/enable", methods=["POST"])
@login_required
@admin_required
def enable_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_active = True
        db.session.commit()
        flash(f"User {user.username} has been enabled.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/verify", methods=["POST"])
@login_required
@admin_required
def verify_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_verified = True
        db.session.commit()
        flash(f"User {user.username} has been marked as verified.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/unverify", methods=["POST"])
@login_required
@admin_required
def unverify_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_verified = False
        db.session.commit()
        flash(f"User {user.username} has been marked as unverified.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/make-public", methods=["POST"])
@login_required
@admin_required
def make_user_public(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_private = False
        db.session.commit()
        flash(f"User {user.username} has been made public.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/make-private", methods=["POST"])
@login_required
@admin_required
def make_user_private(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.is_private = True
        db.session.commit()
        flash(f"User {user.username} has been made private.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/complete_onboarding", methods=["POST"])
@login_required
@admin_required
def complete_onboarding(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.has_completed_onboarding = True
        db.session.commit()
        flash(
            f"User {user.username} has been marked as completed onboarding.", "success"
        )
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/users/<int:user_id>/reset_onboarding", methods=["POST"])
@login_required
@admin_required
def reset_onboarding(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.has_completed_onboarding = False
        db.session.commit()
        flash(f"User {user.username} has been marked as pending onboarding.", "success")
    else:
        flash(USER_NOT_FOUND_MSG, "danger")
    return redirect(url_for(ADMIN_USERS_ROUTE))


@admin_bp.route("/cleanup")
@login_required
@admin_required
def cleanup():
    # Find orphaned MyFood, Recipe, and MyMeal items
    orphaned_foods = MyFood.query.filter(MyFood.user_id.is_(None)).all()
    orphaned_recipes = Recipe.query.filter(Recipe.user_id.is_(None)).all()
    orphaned_meals = MyMeal.query.filter(MyMeal.user_id.is_(None)).all()

    # Get all referenced IDs
    referenced_my_food_ids = {
        row.my_food_id
        for row in db.session.query(DailyLog.my_food_id)
        .filter(DailyLog.my_food_id.isnot(None))
        .distinct()
    }
    referenced_my_food_ids.update(
        {
            row.my_food_id
            for row in db.session.query(RecipeIngredient.my_food_id)
            .filter(RecipeIngredient.my_food_id.isnot(None))
            .distinct()
        }
    )
    referenced_my_food_ids.update(
        {
            row.my_food_id
            for row in db.session.query(MyMealItem.my_food_id)
            .filter(MyMealItem.my_food_id.isnot(None))
            .distinct()
        }
    )

    referenced_recipe_ids = {
        row.recipe_id
        for row in db.session.query(DailyLog.recipe_id)
        .filter(DailyLog.recipe_id.isnot(None))
        .distinct()
    }
    referenced_recipe_ids.update(
        {
            row.recipe_id_link
            for row in db.session.query(RecipeIngredient.recipe_id_link)
            .filter(RecipeIngredient.recipe_id_link.isnot(None))
            .distinct()
        }
    )
    referenced_recipe_ids.update(
        {
            row.recipe_id
            for row in db.session.query(MyMealItem.recipe_id)
            .filter(MyMealItem.recipe_id.isnot(None))
            .distinct()
        }
    )

    safe_to_delete_orphans = []
    in_use_orphans = []

    for food in orphaned_foods:
        if food.id not in referenced_my_food_ids:
            safe_to_delete_orphans.append(food)
        else:
            in_use_orphans.append(food)

    for recipe in orphaned_recipes:
        if recipe.id not in referenced_recipe_ids:
            safe_to_delete_orphans.append(recipe)
        else:
            in_use_orphans.append(recipe)

    # Orphaned meals are always safe to delete as they are not directly referenced.
    safe_to_delete_orphans.extend(orphaned_meals)

    return render_template(
        "admin/cleanup.html",
        safe_to_delete_orphans=safe_to_delete_orphans,
        in_use_orphans=in_use_orphans,
    )


@admin_bp.route("/cleanup/run", methods=["POST"])
@login_required
@admin_required
def run_cleanup():
    # Re-run the scan to ensure we are deleting the correct items
    orphaned_foods = MyFood.query.filter(MyFood.user_id.is_(None)).all()
    orphaned_recipes = Recipe.query.filter(Recipe.user_id.is_(None)).all()
    orphaned_meals = MyMeal.query.filter(MyMeal.user_id.is_(None)).all()

    referenced_my_food_ids = {
        row.my_food_id
        for row in db.session.query(DailyLog.my_food_id)
        .filter(DailyLog.my_food_id.isnot(None))
        .distinct()
    }
    referenced_my_food_ids.update(
        {
            row.my_food_id
            for row in db.session.query(RecipeIngredient.my_food_id)
            .filter(RecipeIngredient.my_food_id.isnot(None))
            .distinct()
        }
    )
    referenced_my_food_ids.update(
        {
            row.my_food_id
            for row in db.session.query(MyMealItem.my_food_id)
            .filter(MyMealItem.my_food_id.isnot(None))
            .distinct()
        }
    )

    referenced_recipe_ids = {
        row.recipe_id
        for row in db.session.query(DailyLog.recipe_id)
        .filter(DailyLog.recipe_id.isnot(None))
        .distinct()
    }
    referenced_recipe_ids.update(
        {
            row.recipe_id_link
            for row in db.session.query(RecipeIngredient.recipe_id_link)
            .filter(RecipeIngredient.recipe_id_link.isnot(None))
            .distinct()
        }
    )
    referenced_recipe_ids.update(
        {
            row.recipe_id
            for row in db.session.query(MyMealItem.recipe_id)
            .filter(MyMealItem.recipe_id.isnot(None))
            .distinct()
        }
    )

    deleted_foods_count = 0
    deleted_recipes_count = 0
    deleted_meals_count = 0

    for food in orphaned_foods:
        if food.id not in referenced_my_food_ids:
            db.session.delete(food)
            deleted_foods_count += 1

    for recipe in orphaned_recipes:
        if recipe.id not in referenced_recipe_ids:
            db.session.delete(recipe)
            deleted_recipes_count += 1

    for meal in orphaned_meals:
        # Orphaned meals are always safe to delete.
        db.session.delete(meal)
        deleted_meals_count += 1

    db.session.commit()

    flash(
        f"Database cleanup complete. Removed {deleted_foods_count} orphaned food items, {deleted_recipes_count} orphaned recipes, and {deleted_meals_count} orphaned meals.",
        "success",
    )
    return redirect(url_for("admin.cleanup"))
