from flask import session, flash, redirect, url_for
from flask_login import login_required
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
)
from sqlalchemy import inspect
from sqlalchemy.types import Date, DateTime
from datetime import date, datetime

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
}


@undo_bp.route("/undo", methods=["GET"])
@login_required
def undo_last_action():
    last_deleted = session.pop("last_deleted", None)

    if not last_deleted:
        flash("No action to undo.", "info")
        return redirect(url_for("diary.diary"))

    undo_method = last_deleted.get("undo_method")
    item_type = last_deleted.get("type")
    item_data = last_deleted.get("data")
    redirect_info = last_deleted.get("redirect_info", {"endpoint": "diary.index"})

    restored = False

    if undo_method == "reinsert":
        ModelClass = MODEL_MAP.get(item_type)
        if ModelClass:
            # For reinsert, item_data is the dictionary of the object's attributes
            # Convert date/datetime strings back to objects
            mapper = inspect(ModelClass)
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
            new_item = ModelClass(**item_data)
            db.session.add(new_item)
            db.session.commit()
            restored = True
        else:
            flash(f"Unknown item type '{item_type}' for re-insertion.", "danger")

    elif undo_method == "reassign_owner":
        ModelClass = MODEL_MAP.get(item_type)
        if ModelClass:
            # For reassign_owner, item_data contains 'item_id' and 'original_user_id'
            item_id = item_data.get("item_id")
            original_user_id = item_data.get("original_user_id")

            item_to_restore = db.session.get(ModelClass, item_id)
            if item_to_restore:
                item_to_restore.user_id = original_user_id
                db.session.commit()
                restored = True
            else:
                flash("Could not find the item to restore.", "danger")
        else:
            flash(f"Unknown item type '{item_type}' for re-assigning owner.", "danger")

    else:
        flash(f"Unknown undo method: {undo_method}", "danger")

    if restored:
        flash("Item restored.", "success")

    # Redirect user back to the original page
    endpoint = redirect_info.get("endpoint", "diary.index")
    params = redirect_info.get("params", {})
    fragment = redirect_info.get("fragment")

    redirect_url = url_for(endpoint, **params, _anchor=fragment)
    return redirect(redirect_url)
