from flask import session, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.types import Date, DateTime
from werkzeug.routing import BuildError
from datetime import date, datetime
from . import undo_bp
from models import (
    db,
    DailyLog,
    RecipeIngredient,
    MyFood,
    MyMeal,
    MyMealItem,
    Recipe,
    ExerciseLog,
    CheckIn,
    FastingSession,
    Friendship,
    UnifiedPortion,
    FoodCategory,
)

# Map item type strings to their corresponding model classes
MODEL_MAP = {
    "dailylog": DailyLog,
    "recipe_ingredient": RecipeIngredient,
    "my_food": MyFood,
    "recipe": Recipe,
    "mymeal": MyMeal,
    "mymealitem": MyMealItem,
    "exercise_log": ExerciseLog,
    "check_in": CheckIn,
    "fasting_session": FastingSession,
    "friendship": Friendship,
    "portion": UnifiedPortion,
    "food_category": FoodCategory,
}

# Fallback target for every undo. The real diary endpoint is ``diary.diary``
# (``diary.index`` does not exist and made the fallback path raise BuildError).
DIARY_ENDPOINT = "diary.diary"

UNAUTHORIZED_RESTORE_MSG = "You do not have permission to restore that item."

_MALFORMED_RECORD_MSG = "The stored undo record is malformed; nothing was restored."

_MISSING_PRIMARY_KEY_MSG = "Cannot restore the item: its stored id is invalid."

_ID_COLLISION_MSG = "An item with that id already exists; nothing was restored."

_RESTORE_FAILED_MSG = "Could not restore the item."

_NO_TARGET_MSG = "Could not build the original page URL."

# Sentinel for models that have no user_id column at all (e.g. FoodCategory).
_ROW_HAS_NO_OWNER_COLUMN = object()


def _redirect_target(redirect_info):
    """Build the post-undo URL from session data, falling back to the diary.

    ``redirect_info`` is attacker-editable session data, so an unknown endpoint
    or malformed params must degrade to the diary page instead of raising
    ``BuildError`` (a 500 on a mutating GET).
    """
    endpoint = DIARY_ENDPOINT
    params = {}
    fragment = None

    if isinstance(redirect_info, dict):
        endpoint = redirect_info.get("endpoint") or DIARY_ENDPOINT
        params = redirect_info.get("params") or {}
        fragment = redirect_info.get("fragment")

    if not isinstance(endpoint, str) or not isinstance(params, dict):
        endpoint, params = DIARY_ENDPOINT, {}

    try:
        return url_for(endpoint, **params, _anchor=fragment)
    except (BuildError, TypeError, ValueError):
        flash(_NO_TARGET_MSG, "danger")
        return url_for(DIARY_ENDPOINT)


def _normalize_item_id(item_data, key="id"):
    """Return ``item_data[key]`` as an int, or None when absent or unusable."""
    item_id = item_data.get(key)
    if item_id is None:
        return None
    if isinstance(item_id, bool) or not isinstance(item_id, (int, str)):
        return False
    if isinstance(item_id, str):
        if not item_id.isdigit():
            return False
        item_id = int(item_id)
        item_data[key] = item_id
    return item_id


def _owner_id_for_payload(item_type, item_data):
    """Resolve which user a session-supplied payload belongs to.

    Returns the owning user id, or ``None`` when ownership cannot be proven.
    The answer is derived from the payload's own foreign keys resolved against
    rows already in the database, never taken on faith from a tampered blob: a
    session cannot claim a row for a user it is not logged in as.
    """
    if "user_id" in item_data:
        # Every owned row carries its owner; this is the value that must match.
        return item_data["user_id"]

    if item_type == "friendship":
        parties = (item_data.get("requester_id"), item_data.get("receiver_id"))
        return current_user.id if current_user.id in parties else None

    if item_type == "recipe_ingredient":
        recipe_id = item_data.get("recipe_id")
        if isinstance(recipe_id, int):
            recipe = db.session.get(Recipe, recipe_id)
            return recipe.user_id if recipe else None
        return None

    if item_type == "mymealitem":
        meal_id = item_data.get("my_meal_id")
        if isinstance(meal_id, int):
            meal = db.session.get(MyMeal, meal_id)
            return meal.user_id if meal else None
        return None

    if item_type == "portion":
        # UnifiedPortion has no owner column; ownership comes from its parent.
        my_food_id = item_data.get("my_food_id")
        if isinstance(my_food_id, int):
            my_food = db.session.get(MyFood, my_food_id)
            return my_food.user_id if my_food else None
        recipe_id = item_data.get("recipe_id")
        if isinstance(recipe_id, int):
            recipe = db.session.get(Recipe, recipe_id)
            return recipe.user_id if recipe else None
        if item_data.get("fdc_id"):
            # USDA portions are shared reference data; only key users may edit
            # them, which is what the delete route already enforced.
            return current_user.id if current_user.is_key_user else None
        return None

    return None


def _apply_session_types(model_class, item_data):
    """Convert the ISO strings produced by the session serializer back."""
    mapper = inspect(model_class)
    for key, value in item_data.items():
        if isinstance(value, str):
            column = mapper.columns.get(key)
            if column is not None:
                if isinstance(column.type, DateTime):
                    try:
                        item_data[key] = datetime.fromisoformat(value)
                    except ValueError:
                        # Handle cases where it might be just a date string for a datetime field
                        item_data[key] = date.fromisoformat(value)
                elif isinstance(column.type, Date):
                    item_data[key] = date.fromisoformat(value)


def _restore_by_reinsert(item_type, item_data):
    """Re-create a hard-deleted row from the session payload.

    The payload supplies both the primary key and the owner, so both are
    verified against ``current_user`` and the live table before anything is
    written; otherwise a tampered ``last_deleted`` blob could plant or hijack
    another user's row.
    """
    model_class = MODEL_MAP.get(item_type)
    if not model_class:
        flash(f"Unknown item type '{item_type}' for re-insertion.", "danger")
        return False

    if _owner_id_for_payload(item_type, item_data) != current_user.id:
        flash(UNAUTHORIZED_RESTORE_MSG, "danger")
        return False

    item_id = _normalize_item_id(item_data)
    if item_id is False:
        flash(_MISSING_PRIMARY_KEY_MSG, "danger")
        return False

    if item_id is not None and db.session.get(model_class, item_id) is not None:
        flash(_ID_COLLISION_MSG, "danger")
        return False

    try:
        # Conversion lives INSIDE the guard: the session blob is user-editable,
        # and an unparseable date string must flash and abort, not 500.
        _apply_session_types(model_class, item_data)
        new_item = model_class(**item_data)
        db.session.add(new_item)
        db.session.commit()
    except (SQLAlchemyError, TypeError, ValueError):
        db.session.rollback()
        flash(_RESTORE_FAILED_MSG, "danger")
        return False

    return True


def _restore_by_reassigning_owner(item_type, item_data):
    """Hand an anonymized row back to its original owner.

    Only allowed when the claim is the caller's own (``original_user_id`` is
    ``current_user.id``) or the row is currently orphaned; otherwise a tampered
    session could re-title a row that still belongs to somebody else.
    """
    model_class = MODEL_MAP.get(item_type)
    if not model_class:
        flash(f"Unknown item type '{item_type}' for re-assigning owner.", "danger")
        return False

    item_id = _normalize_item_id(item_data, key="item_id")
    original_user_id = _normalize_item_id(item_data, key="original_user_id")
    if item_id is False or original_user_id is False:
        flash(_MISSING_PRIMARY_KEY_MSG, "danger")
        return False

    item_to_restore = db.session.get(model_class, item_id) if item_id else None
    if not item_to_restore:
        flash("Could not find the item to restore.", "danger")
        return False

    current_owner = getattr(item_to_restore, "user_id", _ROW_HAS_NO_OWNER_COLUMN)
    if current_owner is _ROW_HAS_NO_OWNER_COLUMN:
        # The model is not owner-addressable, so this row can never be restored
        # by reassigning a user_id.
        flash(UNAUTHORIZED_RESTORE_MSG, "danger")
        return False

    if original_user_id != current_user.id and current_owner is not None:
        flash(UNAUTHORIZED_RESTORE_MSG, "danger")
        return False

    item_to_restore.user_id = original_user_id
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash(_RESTORE_FAILED_MSG, "danger")
        return False

    return True


@undo_bp.route("/undo", methods=["GET"])
@login_required
def undo_last_action():
    last_deleted = session.pop("last_deleted", None)

    if not last_deleted:
        flash("No action to undo.", "info")
        return redirect(url_for(DIARY_ENDPOINT))

    if not isinstance(last_deleted, dict):
        flash(_MALFORMED_RECORD_MSG, "danger")
        return redirect(url_for(DIARY_ENDPOINT))

    undo_method = last_deleted.get("undo_method")
    item_type = last_deleted.get("type")
    item_data = last_deleted.get("data")
    redirect_info = last_deleted.get("redirect_info") or {"endpoint": DIARY_ENDPOINT}

    restored = False

    if not isinstance(item_data, dict):
        flash(_MALFORMED_RECORD_MSG, "danger")
    elif undo_method == "reinsert":
        restored = _restore_by_reinsert(item_type, item_data)
    elif undo_method == "reassign_owner":
        restored = _restore_by_reassigning_owner(item_type, item_data)
    else:
        flash(f"Unknown undo method: {undo_method}", "danger")

    if restored:
        flash("Item restored.", "success")

    # Redirect user back to the original page
    return redirect(_redirect_target(redirect_info))
