from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from . import diary_bp
from models import (
    db,
    DailyLog,
    Food,
    MyFood,
    MyMeal,
    MyMealItem,
    Recipe,
    RecipeIngredient,
    UserGoal,
    ExerciseLog,
    UnifiedPortion,
    User,
    Friendship,
    FastingSession,
)
from datetime import date, timedelta, datetime
from opennourish.time_utils import get_user_today
from opennourish.utils import (
    calculate_nutrition_for_items,
    get_available_portions,
    get_standard_meal_names_for_user,
    prepare_undo_and_delete,
)
from .forms import MealForm
from sqlalchemy.orm import joinedload, selectinload
from constants import ALL_MEAL_TYPES
from sqlalchemy import func

# Import the update_recipe_nutrition function from recipes module
from opennourish.recipes.routes import update_recipe_nutrition

from types import SimpleNamespace


@diary_bp.route("/diary/")
@diary_bp.route("/diary/<string:log_date_str>")
@login_required
def diary(log_date_str=None):
    if log_date_str:
        log_date = date.fromisoformat(log_date_str)
    else:
        if current_user.diary_default_view == "yesterday":
            log_date = get_user_today(current_user.timezone) - timedelta(days=1)
        else:
            log_date = get_user_today(current_user.timezone)

    active_fast = FastingSession.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()
    is_fasting = active_fast is not None

    user_goal = db.session.get(UserGoal, current_user.id)
    if not user_goal:
        # Create a temporary default goal if none exists
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(
        user_id=current_user.id, log_date=log_date
    ).all()

    exercise_logs = ExerciseLog.query.filter_by(
        user_id=current_user.id, log_date=log_date
    ).all()
    calories_burned = sum(log.calories_burned for log in exercise_logs)

    meals = {
        "Breakfast": [],
        "Snack (morning)": [],
        "Lunch": [],
        "Snack (afternoon)": [],
        "Dinner": [],
        "Snack (evening)": [],
        "Unspecified": [],
        "Water": [],
    }

    meal_totals = {
        meal_name: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}
        for meal_name in meals
    }

    totals = calculate_nutrition_for_items(daily_logs)

    for log in daily_logs:
        food_item = None
        description_to_display = "Unknown Food"
        display_amount = log.amount_grams
        selected_portion = None
        nutrition = calculate_nutrition_for_items([log])
        available_portions = []
        food_type = None
        food_id = None
        total_gram_weight = log.amount_grams

        if log.fdc_id:
            food_item = db.session.get(Food, log.fdc_id)
            food_type = "usda"
            food_id = log.fdc_id
        elif log.my_food_id:
            food_item = db.session.get(MyFood, log.my_food_id)
            food_type = "my_food"
            food_id = log.my_food_id
        elif log.recipe_id:
            food_item = db.session.get(Recipe, log.recipe_id)
            food_type = "recipe"
            food_id = log.recipe_id

        if food_item:
            available_portions = get_available_portions(food_item)
            gram_portion = next(
                (p for p in available_portions if p.gram_weight == 1.0), None
            )
            selected_portion = gram_portion

            if log.portion_id_fk:
                portion = db.session.get(UnifiedPortion, log.portion_id_fk)
                if portion and portion.gram_weight > 0:
                    display_amount = log.amount_grams / portion.gram_weight
                    selected_portion = portion

            nutrition = calculate_nutrition_for_items([log])
            description_to_display = (
                food_item.description
                if hasattr(food_item, "description")
                else food_item.name
            )

            if hasattr(food_item, "user_id"):
                if food_item.user_id is None:
                    description_to_display += " (deleted)"
                elif food_item.user_id != current_user.id:
                    owner = db.session.get(User, food_item.user_id)
                    if owner:
                        description_to_display += f" (from {owner.username})"
                    else:
                        description_to_display += " (deleted)"

        meal_key = log.meal_name or "Unspecified"
        if meal_key not in meals:
            meals[meal_key] = []

        meal_totals[meal_key]["calories"] += nutrition["calories"]
        meal_totals[meal_key]["protein"] += nutrition["protein"]
        meal_totals[meal_key]["carbs"] += nutrition["carbs"]
        meal_totals[meal_key]["fat"] += nutrition["fat"]
        meal_totals[meal_key]["fiber"] += nutrition["fiber"]

        meals[meal_key].append(
            {
                "log_id": log.id,
                "description": description_to_display,
                "amount": display_amount,
                "nutrition": nutrition,
                "portions": available_portions,
                "selected_portion": selected_portion,
                "total_gram_weight": total_gram_weight,
                "owner_id": food_item.user_id
                if hasattr(food_item, "user_id")
                else None,
                "food_type": food_type,
                "food_id": food_id,
            }
        )

    prev_date = log_date - timedelta(days=1)
    next_date = log_date + timedelta(days=1)

    # Determine the base meal names to always display based on user settings
    base_meals_to_show = get_standard_meal_names_for_user(current_user)

    # If fasting, only show water and hide other meals
    if is_fasting:
        base_meals_to_show = ["Water"]

    # Collect all meal names that actually have items logged for the day
    logged_meal_names = {meal_name for meal_name, items in meals.items() if items}

    # Combine base meals with any other meals that have logged items
    meal_names_to_render = sorted(
        list(set(base_meals_to_show) | logged_meal_names), key=ALL_MEAL_TYPES.index
    )

    # --- Water Quick-Add Setup ---
    # Ensure a "Water" food item exists for the user to log against, with all standard portions.
    water_food = MyFood.query.filter_by(
        user_id=current_user.id, description="Water"
    ).first()

    # Define standard water portions and their gram weights
    standard_water_portions = {
        "ml": 1.0,
        "fl oz": 29.5735,
        "cup": 236.59,
        "L": 1000.0,
        "gal": 3785.41,
        "Small Water Bottle (16.9oz)": 500.0,
        'Large "Smart" Bottle (1L)': 1000.0,
        "Standard Can (12oz)": 355.0,
        "Small Can (330ml)": 330.0,
        "Glass of Water (8oz)": 240.0,
        "Large Glass (16oz)": 475.0,
        "Coffee Mug (12oz)": 355.0,
        "Reusable Bottle (32oz)": 950.0,
    }

    if not water_food:
        # Create the water food item if it doesn't exist
        water_food = MyFood(
            user_id=current_user.id,
            description="Water",
            calories_per_100g=0,
            protein_per_100g=0,
            carbs_per_100g=0,
            fat_per_100g=0,
        )
        db.session.add(water_food)
        db.session.flush()  # Flush to get an ID for the portions

        # Create all standard portions
        portions_to_add = [
            UnifiedPortion(
                my_food_id=water_food.id,
                measure_unit_description=unit,
                gram_weight=gram_weight,
                amount=1.0,
            )
            for unit, gram_weight in standard_water_portions.items()
        ]
        db.session.add_all(portions_to_add)
        db.session.commit()
    else:
        # If water food exists, check for and create any missing standard portions
        existing_portions = {p.measure_unit_description for p in water_food.portions}
        portions_to_add = [
            UnifiedPortion(
                my_food_id=water_food.id,
                measure_unit_description=unit,
                gram_weight=gram_weight,
                amount=1.0,
            )
            for unit, gram_weight in standard_water_portions.items()
            if unit not in existing_portions
        ]

        if portions_to_add:
            db.session.add_all(portions_to_add)
            db.session.commit()

    # Calculate total water intake in grams
    water_total_grams = sum(
        log.amount_grams for log in daily_logs if log.meal_name == "Water"
    )

    return render_template(
        "diary/diary.html",
        date=log_date,
        meals=meals,
        totals=totals,
        prev_date=prev_date,
        next_date=next_date,
        goals=user_goal,
        calories_burned=calories_burned,
        meal_names_to_render=meal_names_to_render,
        is_fasting=is_fasting,
        water_total_grams=water_total_grams,
        water_food=water_food,
        meal_totals=meal_totals,
    )


@diary_bp.route("/diary/log/<int:log_id>/delete", methods=["POST"])
@login_required
def delete_log(log_id):
    log_entry = db.session.get(DailyLog, log_id)
    if log_entry and log_entry.user_id == current_user.id:
        log_date_str = log_entry.log_date.isoformat()
        meal_name = log_entry.meal_name or "Unspecified"
        anchor = f"meal-{meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"

        redirect_info = {
            "endpoint": "diary.diary",
            "params": {"log_date_str": log_date_str},
            "fragment": anchor,
        }
        prepare_undo_and_delete(
            log_entry, "dailylog", redirect_info, success_message="Entry deleted."
        )

        return redirect(
            url_for("diary.diary", log_date_str=log_date_str, _anchor=anchor)
        )

    flash("Entry not found or you do not have permission to delete it.", "danger")
    return redirect(url_for("diary.diary"))


@diary_bp.route("/my_meals/<int:meal_id>/delete", methods=["POST"])
@login_required
def delete_meal(meal_id):
    meal = db.session.get(MyMeal, meal_id)
    if meal and meal.user_id == current_user.id:
        redirect_info = {"endpoint": "diary.my_meals"}
        prepare_undo_and_delete(
            meal,
            "mymeal",
            redirect_info,
            delete_method="anonymize",
            success_message="Meal deleted.",
        )
        return redirect(url_for("diary.my_meals"))

    flash("Meal not found or you do not have permission to delete it.", "danger")
    return redirect(url_for("diary.my_meals"))


@diary_bp.route("/my_meals/<int:meal_id>/copy", methods=["POST"])
@login_required
def copy_meal(meal_id):
    original_meal = MyMeal.query.options(selectinload(MyMeal.items)).get_or_404(meal_id)

    # Allow cloning own meal, or copying from a friend
    if original_meal.user_id != current_user.id:
        friend_ids = [friend.id for friend in current_user.friends]
        if original_meal.user_id not in friend_ids:
            flash("You can only copy meals from your friends.", "danger")
            return redirect(request.referrer or url_for("diary.my_meals"))

    new_meal = MyMeal(user_id=current_user.id, name=f"{original_meal.name} (Copy)")
    db.session.add(new_meal)
    db.session.flush()

    for orig_item in original_meal.items:
        new_item = MyMealItem(
            my_meal_id=new_meal.id,
            fdc_id=orig_item.fdc_id,
            my_food_id=orig_item.my_food_id,
            recipe_id=orig_item.recipe_id,
            amount_grams=orig_item.amount_grams,
        )
        db.session.add(new_item)

    db.session.commit()
    flash(f"Successfully copied '{original_meal.name}' to your meals.", "success")
    return redirect(url_for("diary.my_meals"))


@diary_bp.route("/diary/update_entry/<int:log_id>", methods=["POST"])
@login_required
def update_entry(log_id):
    log_entry = db.session.get(DailyLog, log_id)
    if not log_entry or log_entry.user_id != current_user.id:
        flash("Entry not found or you do not have permission to edit it.", "danger")
        return redirect(url_for("diary.diary"))

    amount = request.form.get("amount", type=float)
    portion_id = request.form.get("portion_id", type=int)

    if amount and portion_id:
        portion = db.session.get(UnifiedPortion, portion_id)
        if portion:
            log_entry.amount_grams = amount * portion.gram_weight
            log_entry.serving_type = portion.full_description_str
            log_entry.portion_id_fk = portion.id
            db.session.commit()
            flash("Entry updated successfully!", "success")
        else:
            flash("Invalid portion selected.", "danger")
    else:
        flash("Invalid data submitted.", "danger")

    meal_name = log_entry.meal_name or "Unspecified"
    anchor = (
        f"meal-{meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
    )
    return redirect(
        url_for(
            "diary.diary", log_date_str=log_entry.log_date.isoformat(), _anchor=anchor
        )
    )


@diary_bp.route("/diary/move_entry", methods=["POST"])
@login_required
def move_entry():
    log_id = request.form.get("log_id")
    target_date_str = request.form.get("target_date")
    target_meal_name = request.form.get("target_meal_name")

    log_entry = db.session.get(DailyLog, log_id)

    if not log_entry or log_entry.user_id != current_user.id:
        flash(
            "Diary entry not found or you do not have permission to move it.", "danger"
        )
        return redirect(request.referrer or url_for("diary.diary"))

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        log_entry.log_date = target_date
        log_entry.meal_name = target_meal_name
        db.session.commit()
        flash("Diary entry moved successfully.", "success")
        anchor = f"meal-{target_meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
        return redirect(
            url_for("diary.diary", log_date_str=target_date_str, _anchor=anchor)
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error moving diary entry: {e}")
        flash("There was an error moving the diary entry.", "danger")
        return redirect(
            url_for("diary.diary", log_date_str=log_entry.log_date.isoformat())
        )


@diary_bp.route("/diary/copy_entry", methods=["POST"])
@login_required
def copy_entry():
    log_id = request.form.get("log_id")
    target_date_str = request.form.get("target_date")
    target_meal_name = request.form.get("target_meal_name")

    log_entry_to_copy = db.session.get(DailyLog, log_id)

    if not log_entry_to_copy or log_entry_to_copy.user_id != current_user.id:
        flash(
            "Diary entry not found or you do not have permission to copy it.", "danger"
        )
        return redirect(request.referrer or url_for("diary.diary"))

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        new_log_entry = DailyLog(
            user_id=current_user.id,
            log_date=target_date,
            meal_name=target_meal_name,
            fdc_id=log_entry_to_copy.fdc_id,
            my_food_id=log_entry_to_copy.my_food_id,
            recipe_id=log_entry_to_copy.recipe_id,
            amount_grams=log_entry_to_copy.amount_grams,
            serving_type=log_entry_to_copy.serving_type,
            portion_id_fk=log_entry_to_copy.portion_id_fk,
        )
        db.session.add(new_log_entry)
        db.session.commit()
        flash("Diary entry copied successfully.", "success")
        anchor = f"meal-{target_meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
        return redirect(
            url_for("diary.diary", log_date_str=target_date_str, _anchor=anchor)
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error copying diary entry: {e}")
        flash("There was an error copying the diary entry.", "danger")
        return redirect(
            url_for("diary.diary", log_date_str=log_entry_to_copy.log_date.isoformat())
        )


@diary_bp.route("/my_meals/new", methods=["GET", "POST"])
@login_required
def new_meal():
    new_meal = MyMeal(user_id=current_user.id, name="New Meal")
    db.session.add(new_meal)
    db.session.commit()
    flash("New meal created. You can now add items to it.", "success")
    return redirect(url_for("diary.edit_meal", meal_id=new_meal.id))


@diary_bp.route("/my_meals/edit/<int:meal_id>", methods=["GET", "POST"])
@login_required
def edit_meal(meal_id):
    meal = (
        db.session.query(MyMeal)
        .options(
            selectinload(MyMeal.items)
            .selectinload(MyMealItem.my_food)
            .selectinload(MyFood.portions),
            selectinload(MyMeal.items).selectinload(MyMealItem.recipe),
        )
        .filter_by(id=meal_id)
        .first()
    )

    if not meal or meal.user_id != current_user.id:
        flash("Meal not found or you do not have permission to edit it.", "danger")
        return redirect(url_for("diary.my_meals"))

    form = MealForm(obj=meal)
    if form.validate_on_submit():
        meal.name = form.name.data
        db.session.commit()
        flash("Meal name updated.", "success")
        return redirect(url_for("diary.edit_meal", meal_id=meal.id))

    for item in meal.items:
        item.available_portions = get_available_portions(
            item.food or item.my_food or item.recipe
        )

        # Determine display_amount and selected_portion_id based on saved portion
        item.display_amount = item.amount_grams  # Default to grams for display
        item.selected_portion_id = "g"  # Default to grams
        item.display_serving_type = "g"  # Default display type

        if item.portion_id_fk:
            selected_portion = db.session.get(UnifiedPortion, item.portion_id_fk)
            if selected_portion:
                if selected_portion.gram_weight > 0:
                    item.display_amount = (
                        item.amount_grams / selected_portion.gram_weight
                    )
                    item.selected_portion_id = selected_portion.id
                    item.display_serving_type = selected_portion.full_description_str
                else:
                    current_app.logger.warning(
                        f"WARNING: edit_meal - Portion {selected_portion.id} has gram_weight 0. Cannot calculate display_amount."
                    )
            else:
                current_app.logger.warning(
                    f"WARNING: edit_meal - UnifiedPortion with ID {item.portion_id_fk} not found."
                )

        # Calculate nutrition for display
        # Create a temporary SimpleNamespace object to pass to calculate_nutrition_for_items
        # This mimics the structure of DailyLog or RecipeIngredient for calculation
        temp_item_for_nutrition = SimpleNamespace(
            fdc_id=item.fdc_id,
            my_food_id=item.my_food_id,
            recipe_id=item.recipe_id,
            amount_grams=item.amount_grams,
        )
        item.nutrition_summary = calculate_nutrition_for_items(
            [temp_item_for_nutrition]
        )

    # Calculate total nutrition for the meal
    meal.totals = calculate_nutrition_for_items(meal.items)

    return render_template("diary/edit_meal.html", meal=meal, form=form)


@diary_bp.route("/my_meals/<int:meal_id>/delete_item/<int:item_id>", methods=["POST"])
@login_required
def delete_meal_item(meal_id, item_id):
    meal = db.session.get(MyMeal, meal_id)
    item = db.session.get(MyMealItem, item_id)

    if (
        not meal
        or meal.user_id != current_user.id
        or not item
        or item.my_meal_id != meal.id
    ):
        flash("Item not found or you do not have permission to delete it.", "danger")
        return redirect(url_for("diary.edit_meal", meal_id=meal_id))

    redirect_info = {
        "endpoint": "diary.edit_meal",
        "params": {"meal_id": meal_id},
    }
    prepare_undo_and_delete(
        item,
        "mymealitem",
        redirect_info,
        success_message="Meal item deleted.",
    )

    return redirect(url_for("diary.edit_meal", meal_id=meal_id))


@diary_bp.route("/diary/save_meal_and_edit", methods=["POST"])
@login_required
def save_meal_and_edit():
    log_date_str = request.form.get("log_date")
    meal_name = request.form.get("meal_name")

    if log_date_str and meal_name:
        log_date = date.fromisoformat(log_date_str)

        # Create a temporary name
        new_meal_name = f"New Meal from {meal_name} - {log_date.strftime('%Y-%m-%d')}"

        new_meal = MyMeal(user_id=current_user.id, name=new_meal_name)
        db.session.add(new_meal)

        db.session.flush()

        log_items = DailyLog.query.filter_by(
            user_id=current_user.id, log_date=log_date, meal_name=meal_name
        ).all()

        if not log_items:
            flash(f"There are no items in {meal_name} to save.", "warning")
            anchor = f"meal-{meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
            return redirect(
                url_for("diary.diary", log_date_str=log_date_str, _anchor=anchor)
            )

        for item in log_items:
            new_meal_item = MyMealItem(
                meal=new_meal,
                fdc_id=item.fdc_id,
                my_food_id=item.my_food_id,
                recipe_id=item.recipe_id,
                amount_grams=item.amount_grams,
                serving_type=item.serving_type,
                portion_id_fk=item.portion_id_fk,
            )
            db.session.add(new_meal_item)

        db.session.commit()
        flash("Meal saved with a temporary name. You can now edit it.", "success")
        return redirect(url_for("diary.edit_meal", meal_id=new_meal.id))

    flash("Invalid data.", "danger")
    return redirect(url_for("diary.diary", log_date_str=log_date_str))


@diary_bp.route("/diary/save_meal_as_recipe", methods=["POST"])
@login_required
def save_meal_as_recipe():
    log_date_str = request.form.get("log_date")
    meal_name = request.form.get("meal_name")

    if log_date_str and meal_name:
        log_date = date.fromisoformat(log_date_str)

        # Create a unique recipe name for the new recipe
        recipe_name = f"Recipe from {meal_name} - {log_date.strftime('%Y-%m-%d')}"

        # Create a new recipe with an empty description initially
        # The Recipe model expects 'name' and 'user_id', not 'description'
        new_recipe = Recipe(
            user_id=current_user.id,
            name=recipe_name,
            is_public=False,
        )
        db.session.add(new_recipe)

        db.session.flush()  # Get the ID for the new recipe

        log_items = DailyLog.query.filter_by(
            user_id=current_user.id, log_date=log_date, meal_name=meal_name
        ).all()

        if not log_items:
            flash(f"There are no items in {meal_name} to save as a recipe.", "warning")
            anchor = f"meal-{meal_name.lower().replace(' ', '-').replace('(', '').replace(')', '')}"
            return redirect(
                url_for("diary.diary", log_date_str=log_date_str, _anchor=anchor)
            )

        # Add each item from the diary meal to the recipe as ingredients
        for index, item in enumerate(log_items):
            # Calculate the next sequence number for the ingredient
            max_seq_num = (
                db.session.query(func.max(RecipeIngredient.seq_num))
                .filter(RecipeIngredient.recipe_id == new_recipe.id)
                .scalar()
            )
            next_seq_num = (max_seq_num or 0) + 1

            # Create a RecipeIngredient with the item's data
            ingredient = RecipeIngredient(
                recipe_id=new_recipe.id,
                fdc_id=item.fdc_id,
                my_food_id=item.my_food_id,
                recipe_id_link=item.recipe_id,
                amount_grams=item.amount_grams,
                serving_type=item.serving_type,
                portion_id_fk=item.portion_id_fk,
                seq_num=next_seq_num,
            )
            db.session.add(ingredient)

        # Create the default 1-gram portion for this recipe (required by Recipe model)
        gram_portion = UnifiedPortion(
            recipe_id=new_recipe.id,
            amount=1.0,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0,
        )
        db.session.add(gram_portion)

        # Update the nutrition information for the new recipe
        update_recipe_nutrition(new_recipe)

        db.session.commit()
        flash("Meal saved as a new recipe. You can now edit it.", "success")
        return redirect(url_for("recipes.edit_recipe", recipe_id=new_recipe.id))

    flash("Invalid data.", "danger")
    return redirect(url_for("diary.diary", log_date_str=log_date_str))


@diary_bp.route("/my_meals")
@login_required
def my_meals():
    page = request.args.get("page", 1, type=int)
    view_mode = request.args.get("view", "user")  # 'user' or 'friends'
    per_page = 5

    query = MyMeal.query
    if view_mode == "friends":
        friend_ids = [friend.id for friend in current_user.friends]
        query = query.options(joinedload(MyMeal.user))
        if not friend_ids:
            query = query.filter(db.false())
        else:
            query = query.filter(MyMeal.user_id.in_(friend_ids))
    else:  # Default to user's meals
        query = query.filter_by(user_id=current_user.id)

    meals_pagination = query.options(
        selectinload(MyMeal.items)
        .selectinload(MyMealItem.my_food)
        .selectinload(MyFood.portions),
        selectinload(MyMeal.items).selectinload(MyMealItem.recipe),
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Collect all unique fdc_ids from all meal items across all meals
    all_usda_food_ids = {
        item.fdc_id
        for meal in meals_pagination.items
        for item in meal.items
        if item.fdc_id
    }

    # Fetch all relevant USDA Food objects in one query
    usda_foods_map = {}
    if all_usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(all_usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}

    # Process each meal to calculate display values and nutrition
    for meal in meals_pagination.items:
        for item in meal.items:
            if item.fdc_id:
                # Attach the pre-loaded USDA food object to the meal item
                item.usda_food = usda_foods_map.get(item.fdc_id)

            # Determine display_amount and display_serving_type based on saved portion
            item.display_amount = item.amount_grams  # Default to grams
            item.display_serving_type = "g"  # Default display type

            if item.portion_id_fk:
                selected_portion = db.session.get(UnifiedPortion, item.portion_id_fk)
                if selected_portion and selected_portion.gram_weight > 0:
                    item.display_amount = (
                        item.amount_grams / selected_portion.gram_weight
                    )
                    item.display_serving_type = selected_portion.full_description_str

            # Calculate nutrition for display for each item
            temp_item_for_nutrition = SimpleNamespace(
                fdc_id=item.fdc_id,
                my_food_id=item.my_food_id,
                recipe_id=item.recipe_id,
                amount_grams=item.amount_grams,
            )
            item.nutrition_summary = calculate_nutrition_for_items(
                [temp_item_for_nutrition]
            )

        # Calculate total nutrition for the meal
        meal.totals = calculate_nutrition_for_items(meal.items)

    return render_template(
        "diary/my_meals.html", meals=meals_pagination, view_mode=view_mode
    )


@diary_bp.route("/my_meals/update_item/<int:item_id>", methods=["POST"])
@login_required
def update_meal_item(item_id):
    item = db.session.get(MyMealItem, item_id)
    if not item or item.meal.user_id != current_user.id:
        flash("Item not found or you do not have permission to edit it.", "danger")
        return redirect(request.referrer or url_for("diary.my_meals"))

    quantity = request.form.get("quantity", type=float)
    portion_id = request.form.get("portion_id", type=int)

    if quantity is not None and portion_id is not None:
        portion = db.session.get(UnifiedPortion, portion_id)
        if portion:
            item.amount_grams = quantity * portion.gram_weight
            item.serving_type = portion.full_description_str
            item.portion_id_fk = portion.id
            db.session.commit()
            flash("Meal item updated.", "success")
        else:
            flash("Invalid portion selected.", "danger")
    else:
        flash("Invalid data submitted.", "danger")

    return redirect(url_for("diary.edit_meal", meal_id=item.my_meal_id))


@diary_bp.route("/diary/copy_meal_from_friend", methods=["POST"])
@login_required
def copy_meal_from_friend():
    friend_username = request.form.get("friend_username")
    log_date_str = request.form.get("log_date")
    meal_name = request.form.get("meal_name")

    if not all([friend_username, log_date_str, meal_name]):
        flash("Missing data to copy the meal.", "danger")
        return redirect(url_for("dashboard.dashboard"))

    friend_user = User.query.filter_by(username=friend_username).first()
    if not friend_user:
        flash("Friend not found.", "danger")
        return redirect(url_for("dashboard.dashboard"))

    # Verify friendship
    is_friend = Friendship.query.filter(
        (
            (Friendship.requester_id == current_user.id)
            & (Friendship.receiver_id == friend_user.id)
            & (Friendship.status == "accepted")
        )
        | (
            (Friendship.requester_id == friend_user.id)
            & (Friendship.receiver_id == current_user.id)
            & (Friendship.status == "accepted")
        )
    ).first()

    if not is_friend:
        flash(f"You are not friends with {friend_username}.", "danger")
        return redirect(url_for("dashboard.dashboard"))

    log_date = date.fromisoformat(log_date_str)

    # Get the friend's log entries for that meal
    friend_logs = DailyLog.query.filter_by(
        user_id=friend_user.id, log_date=log_date, meal_name=meal_name
    ).all()

    if not friend_logs:
        flash(f"No items found in {friend_username}'s {meal_name} to copy.", "warning")
        return redirect(
            url_for(
                "profile.diary", username=friend_username, log_date_str=log_date_str
            )
        )

    # Copy each log entry to the current user
    for friend_log in friend_logs:
        new_log = DailyLog(
            user_id=current_user.id,
            log_date=friend_log.log_date,
            meal_name=friend_log.meal_name,
            fdc_id=friend_log.fdc_id,
            my_food_id=friend_log.my_food_id,
            recipe_id=friend_log.recipe_id,
            amount_grams=friend_log.amount_grams,
            serving_type=friend_log.serving_type,
            portion_id_fk=friend_log.portion_id_fk,
        )
        db.session.add(new_log)

    db.session.commit()
    flash(f"Successfully copied {meal_name} from {friend_username}'s diary.", "success")
    return redirect(url_for("diary.diary", log_date_str=log_date_str))
