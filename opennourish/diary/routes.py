from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from . import diary_bp
from models import db, DailyLog, Food, MyFood, MyMeal, MyMealItem, Recipe, UserGoal, ExerciseLog, UnifiedPortion, User, Friendship
from datetime import date, timedelta
from opennourish.utils import calculate_nutrition_for_items, get_available_portions, remove_leading_one
from .forms import MealForm, DailyLogForm, MealItemForm
from sqlalchemy.orm import joinedload, selectinload

from types import SimpleNamespace
# ... (other imports)

@diary_bp.route('/diary/')
@diary_bp.route('/diary/<string:log_date_str>')
@login_required
def diary(log_date_str=None):
    if log_date_str:
        log_date = date.fromisoformat(log_date_str)
    else:
        log_date = date.today()

    user_goal = db.session.get(UserGoal, current_user.id)
    if not user_goal:
        # Create a temporary default goal if none exists
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(user_id=current_user.id, log_date=log_date).all()
    
    exercise_logs = ExerciseLog.query.filter_by(user_id=current_user.id, log_date=log_date).all()
    calories_burned = sum(log.calories_burned for log in exercise_logs)
    
    meals = {
        'Breakfast': [], 'Snack (morning)': [], 'Lunch': [], 
        'Snack (afternoon)': [], 'Dinner': [], 'Snack (evening)': [],
        'Unspecified': []
    }
    
    totals = calculate_nutrition_for_items(daily_logs)

    for log in daily_logs:
        food_item = None
        description_to_display = "Unknown Food"
        if log.fdc_id:
            food_item = db.session.query(Food).get(log.fdc_id)
        elif log.my_food_id:
            food_item = db.session.get(MyFood, log.my_food_id)
        elif log.recipe_id:
            food_item = db.session.get(Recipe, log.recipe_id)

        if food_item:
            available_portions = get_available_portions(food_item)
            current_app.logger.debug(f"Debug: Available portions for {description_to_display}: {[p.full_description_str if hasattr(p, 'full_description_str') else p.portion_description for p in available_portions]}")
            
            # Determine display_amount and selected_portion_id
            display_amount = log.amount_grams
            selected_portion_id = 'g' # Default to grams
            
            if log.portion_id_fk:
                selected_portion = db.session.get(UnifiedPortion, log.portion_id_fk)
                if selected_portion and selected_portion.gram_weight > 0:
                    display_amount = log.amount_grams / selected_portion.gram_weight
                    selected_portion_id = selected_portion.id
            
            nutrition = calculate_nutrition_for_items([log])
            description_to_display = food_item.description if hasattr(food_item, 'description') else food_item.name
            meals[log.meal_name].append({
                'log_id': log.id,
                'description': description_to_display,
                'amount': display_amount,
                'nutrition': nutrition,
                'portions': available_portions,
                'serving_type': log.serving_type,
                'selected_portion_id': selected_portion_id
            })

    prev_date = log_date - timedelta(days=1)
    next_date = log_date + timedelta(days=1)

    return render_template('diary/diary.html', date=log_date, meals=meals, totals=totals, prev_date=prev_date, next_date=next_date, goals=user_goal, calories_burned=calories_burned)








@diary_bp.route('/diary/log/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_log(log_id):
    log_entry = db.session.get(DailyLog, log_id)
    if log_entry and log_entry.user_id == current_user.id:
        log_date_str = log_entry.log_date.isoformat()
        db.session.delete(log_entry)
        db.session.commit()
        flash('Entry deleted.', 'success')
        return redirect(url_for('diary.diary', log_date_str=log_date_str))
    
    flash('Entry not found or you do not have permission to delete it.', 'danger')
    return redirect(url_for('diary.diary'))

@diary_bp.route('/my_meals/<int:meal_id>/delete', methods=['POST'])
@login_required
def delete_meal(meal_id):
    meal = db.session.get(MyMeal, meal_id)
    if meal and meal.user_id == current_user.id:
        db.session.delete(meal)
        db.session.commit()
        flash('Meal deleted.', 'success')
        return redirect(url_for('diary.my_meals'))
    
    flash('Meal not found or you do not have permission to delete it.', 'danger')
    return redirect(url_for('diary.my_meals'))


@diary_bp.route('/my_meals/<int:meal_id>/copy', methods=['POST'])
@login_required
def copy_meal(meal_id):
    original_meal = MyMeal.query.options(selectinload(MyMeal.items)).get_or_404(meal_id)

    friend_ids = [friend.id for friend in current_user.friends]
    if original_meal.user_id not in friend_ids:
        flash("You can only copy meals from your friends.", "danger")
        return redirect(request.referrer or url_for('diary.my_meals'))

    new_meal = MyMeal(
        user_id=current_user.id,
        name=original_meal.name
    )
    db.session.add(new_meal)
    db.session.flush()

    for orig_item in original_meal.items:
        new_item = MyMealItem(
            my_meal_id=new_meal.id,
            fdc_id=orig_item.fdc_id,
            my_food_id=orig_item.my_food_id,
            recipe_id=orig_item.recipe_id,
            amount_grams=orig_item.amount_grams
        )
        db.session.add(new_item)

    db.session.commit()
    flash(f"Successfully copied '{original_meal.name}' to your meals.", "success")
    return redirect(url_for('diary.my_meals'))


@diary_bp.route('/diary/update_entry/<int:log_id>', methods=['POST'])
@login_required
def update_entry(log_id):
    log_entry = db.session.get(DailyLog, log_id)
    if not log_entry or log_entry.user_id != current_user.id:
        flash('Entry not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.diary'))

    amount = request.form.get('amount', type=float)
    portion_id = request.form.get('portion_id')

    if amount and portion_id:
        if portion_id == 'g':
            log_entry.amount_grams = amount
            log_entry.serving_type = 'g'
            log_entry.portion_id_fk = None
        else:
            portion = db.session.get(UnifiedPortion, int(portion_id))
            if portion:
                log_entry.amount_grams = amount * portion.gram_weight
                log_entry.serving_type = portion.full_description_str
                log_entry.portion_id_fk = portion.id
            else:
                flash('Invalid portion selected.', 'danger')
                return redirect(url_for('diary.diary', log_date_str=log_entry.log_date.isoformat()))

        db.session.commit()
        flash('Entry updated successfully!', 'success')
    else:
        flash('Invalid data submitted.', 'danger')

    return redirect(url_for('diary.diary', log_date_str=log_entry.log_date.isoformat()))


@diary_bp.route('/my_meals/edit/<int:meal_id>', methods=['GET', 'POST'])
@login_required
def edit_meal(meal_id):
    meal = db.session.query(MyMeal).options(
        selectinload(MyMeal.items).selectinload(MyMealItem.my_food).selectinload(MyFood.portions),
        selectinload(MyMeal.items).selectinload(MyMealItem.recipe)
    ).filter_by(id=meal_id).first()

    if not meal or meal.user_id != current_user.id:
        flash('Meal not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.my_meals'))

    form = MealForm(obj=meal)
    if form.validate_on_submit():
        meal.name = form.name.data
        db.session.commit()
        flash('Meal name updated.', 'success')
        return redirect(url_for('diary.edit_meal', meal_id=meal.id))

    for item in meal.items:
        item.available_portions = get_available_portions(item.food or item.my_food or item.recipe)

        # Determine display_amount and selected_portion_id based on saved portion
        item.display_amount = item.amount_grams # Default to grams for display
        item.selected_portion_id = 'g' # Default to grams
        item.display_serving_type = 'g' # Default display type

        if item.portion_id_fk:
            selected_portion = db.session.get(UnifiedPortion, item.portion_id_fk)
            if selected_portion:
                if selected_portion.gram_weight > 0:
                    item.display_amount = item.amount_grams / selected_portion.gram_weight
                    item.selected_portion_id = selected_portion.id
                    item.display_serving_type = selected_portion.full_description_str
                else:
                    current_app.logger.warning(f"WARNING: edit_meal - Portion {selected_portion.id} has gram_weight 0. Cannot calculate display_amount.")
            else:
                current_app.logger.warning(f"WARNING: edit_meal - UnifiedPortion with ID {item.portion_id_fk} not found.")
        
        # Calculate nutrition for display
        # Create a temporary SimpleNamespace object to pass to calculate_nutrition_for_items
        # This mimics the structure of DailyLog or RecipeIngredient for calculation
        temp_item_for_nutrition = SimpleNamespace(
            fdc_id=item.fdc_id,
            my_food_id=item.my_food_id,
            recipe_id=item.recipe_id,
            amount_grams=item.amount_grams
        )
        item.nutrition_summary = calculate_nutrition_for_items([temp_item_for_nutrition])
    return render_template('diary/edit_meal.html', meal=meal, form=form)

@diary_bp.route('/my_meals/<int:meal_id>/edit_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_meal_item(meal_id, item_id):
    meal = db.session.get(MyMeal, meal_id)
    item = db.session.get(MyMealItem, item_id)

    if not meal or meal.user_id != current_user.id or not item or item.my_meal_id != meal.id:
        flash('Item not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.edit_meal', meal_id=meal_id))

    form = MealItemForm(obj=item)

    if form.validate_on_submit():
        item.amount_grams = form.amount.data
        db.session.commit()
        flash('Meal item updated.', 'success')
        return redirect(url_for('diary.edit_meal', meal_id=meal_id))
    elif request.method == 'GET':
        form.amount.data = item.amount_grams

    return render_template('diary/edit_meal_item.html', meal=meal, item=item, form=form)

@diary_bp.route('/my_meals/<int:meal_id>/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_meal_item(meal_id, item_id):
    meal = db.session.get(MyMeal, meal_id)
    item = db.session.get(MyMealItem, item_id)

    if not meal or meal.user_id != current_user.id or not item or item.my_meal_id != meal.id:
        flash('Item not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('diary.edit_meal', meal_id=meal_id))
    current_app.logger.debug(f"DEBUG: Attempting to delete item {item.id} from meal {meal.id}")
    current_app.logger.debug(f"DEBUG: Item state before delete: {db.inspect(item).persistent}")
    db.session.delete(item)
    current_app.logger.debug(f"DEBUG: Item state after db.session.delete: {db.inspect(item).deleted}")
    db.session.commit()
    current_app.logger.debug(f"DEBUG: Item {item.id} deleted and committed.")
    flash('Meal item deleted.', 'success')
    return redirect(url_for('diary.edit_meal', meal_id=meal_id))


@diary_bp.route('/diary/save_meal', methods=['POST'])
@login_required
def save_meal():
    log_date_str = request.form.get('log_date')
    meal_name = request.form.get('meal_name')
    new_meal_name = request.form.get('new_meal_name')

    if log_date_str and meal_name and new_meal_name:
        log_date = date.fromisoformat(log_date_str)
        
        new_meal = MyMeal(user_id=current_user.id, name=new_meal_name)
        db.session.add(new_meal)
        
        log_items = DailyLog.query.filter_by(user_id=current_user.id, log_date=log_date, meal_name=meal_name).all()
        
        for item in log_items:
            new_meal_item = MyMealItem(
                meal=new_meal,
                fdc_id=item.fdc_id,
                my_food_id=item.my_food_id,
                recipe_id=item.recipe_id,
                amount_grams=item.amount_grams
            )
            db.session.add(new_meal_item)
            
        db.session.commit()
        flash(f'Meal "{new_meal_name}" saved.', 'success')
        return redirect(url_for('diary.my_meals')) # This route doesn't exist yet, but we'll create it.

    flash('Invalid data.', 'danger')
    return redirect(url_for('diary.diary', log_date_str=log_date_str))

@diary_bp.route('/my_meals')
@login_required
def my_meals():
    page = request.args.get('page', 1, type=int)
    view_mode = request.args.get('view', 'user') # 'user' or 'friends'
    per_page = 5

    query = MyMeal.query
    if view_mode == 'friends':
        friend_ids = [friend.id for friend in current_user.friends]
        query = query.options(joinedload(MyMeal.user))
        if not friend_ids:
            query = query.filter(db.false())
        else:
            query = query.filter(MyMeal.user_id.in_(friend_ids))
    else: # Default to user's meals
        query = query.filter_by(user_id=current_user.id)

    meals_pagination = query.options(
        selectinload(MyMeal.items).selectinload(MyMealItem.my_food).selectinload(MyFood.portions),
        selectinload(MyMeal.items).selectinload(MyMealItem.recipe)
    ).paginate(page=page, per_page=per_page, error_out=False)

    # Collect all unique fdc_ids from all meal items across all meals
    all_usda_food_ids = {item.fdc_id for meal in meals_pagination.items for item in meal.items if item.fdc_id}

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
            item.display_serving_type = 'g'  # Default display type

            if item.portion_id_fk:
                selected_portion = db.session.get(UnifiedPortion, item.portion_id_fk)
                if selected_portion and selected_portion.gram_weight > 0:
                    item.display_amount = item.amount_grams / selected_portion.gram_weight
                    item.display_serving_type = selected_portion.full_description_str
            
            # Calculate nutrition for display for each item
            temp_item_for_nutrition = SimpleNamespace(
                fdc_id=item.fdc_id,
                my_food_id=item.my_food_id,
                recipe_id=item.recipe_id,
                amount_grams=item.amount_grams
            )
            item.nutrition_summary = calculate_nutrition_for_items([temp_item_for_nutrition])

        # Calculate total nutrition for the meal
        meal.totals = calculate_nutrition_for_items(meal.items)

    return render_template('diary/my_meals.html', meals=meals_pagination, view_mode=view_mode)

@diary_bp.route('/my_meals/update_item/<int:item_id>', methods=['POST'])
@login_required
def update_meal_item(item_id):
    item = db.session.get(MyMealItem, item_id)
    if not item or item.meal.user_id != current_user.id:
        flash('Item not found or you do not have permission to edit it.', 'danger')
        return redirect(request.referrer or url_for('diary.my_meals'))

    quantity = request.form.get('quantity', type=float)
    portion_id = request.form.get('portion_id')

    if quantity is not None and portion_id is not None:
        current_app.logger.debug(f"DEBUG: update_meal_item - quantity: {quantity}, portion_id: {portion_id}")
        if portion_id == 'g':
            item.amount_grams = quantity
            item.serving_type = 'g'
            item.portion_id_fk = None
            current_app.logger.debug(f"DEBUG: update_meal_item - Saved as grams. amount_grams: {item.amount_grams}")
        else:
            portion = db.session.get(UnifiedPortion, int(portion_id))
            if portion:
                item.amount_grams = quantity * portion.gram_weight
                item.serving_type = portion.full_description_str
                item.portion_id_fk = portion.id
                current_app.logger.debug(f"DEBUG: update_meal_item - Saved with portion. gram_weight: {portion.gram_weight}, calculated amount_grams: {item.amount_grams}")
            else:
                flash('Invalid portion selected.', 'danger')
                current_app.logger.warning(f"WARNING: update_meal_item - UnifiedPortion with ID {portion_id} not found.")
                return redirect(url_for('diary.edit_meal', meal_id=item.my_meal_id))
        
        db.session.commit()
        flash('Meal item updated.', 'success')
    else:
        flash('Invalid data.', 'danger')
        current_app.logger.warning(f"WARNING: update_meal_item - Invalid data submitted. quantity: {quantity}, portion_id: {portion_id}")

    return redirect(url_for('diary.edit_meal', meal_id=item.my_meal_id))


@diary_bp.route('/diary/copy_meal_from_friend', methods=['POST'])
@login_required
def copy_meal_from_friend():
    friend_username = request.form.get('friend_username')
    log_date_str = request.form.get('log_date')
    meal_name = request.form.get('meal_name')

    if not all([friend_username, log_date_str, meal_name]):
        flash("Missing data to copy the meal.", "danger")
        return redirect(url_for('dashboard.dashboard'))

    friend_user = User.query.filter_by(username=friend_username).first()
    if not friend_user:
        flash("Friend not found.", "danger")
        return redirect(url_for('dashboard.dashboard'))

    # Verify friendship
    is_friend = Friendship.query.filter(
        ((Friendship.requester_id == current_user.id) & (Friendship.receiver_id == friend_user.id) & (Friendship.status == 'accepted')) |
        ((Friendship.requester_id == friend_user.id) & (Friendship.receiver_id == current_user.id) & (Friendship.status == 'accepted'))
    ).first()

    if not is_friend:
        flash(f"You are not friends with {friend_username}.", "danger")
        return redirect(url_for('dashboard.dashboard'))

    log_date = date.fromisoformat(log_date_str)

    # Get the friend's log entries for that meal
    friend_logs = DailyLog.query.filter_by(
        user_id=friend_user.id,
        log_date=log_date,
        meal_name=meal_name
    ).all()

    if not friend_logs:
        flash(f"No items found in {friend_username}'s {meal_name} to copy.", "warning")
        return redirect(url_for('profile.diary', username=friend_username, log_date_str=log_date_str))

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
            portion_id_fk=friend_log.portion_id_fk
        )
        db.session.add(new_log)

    db.session.commit()
    flash(f"Successfully copied {meal_name} from {friend_username}'s diary.", "success")
    return redirect(url_for('diary.diary', log_date_str=log_date_str))