from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from . import diary_bp
from models import db, DailyLog, Food, MyFood, MyMeal, MyMealItem, Recipe
from datetime import date, timedelta
from opennourish.utils import calculate_nutrition_for_items
from .forms import MealForm, DailyLogForm, MealItemForm
from sqlalchemy.orm import joinedload, selectinload
from models import Portion, MyPortion

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

    daily_logs = DailyLog.query.filter_by(user_id=current_user.id, log_date=log_date).all()
    
    meals = {
        'Breakfast': [], 'Snack (morning)': [], 'Lunch': [], 
        'Snack (afternoon)': [], 'Dinner': [], 'Snack (evening)': []
    }
    
    totals = calculate_nutrition_for_items(daily_logs)

    for log in daily_logs:
        food_item = None
        available_portions = []
        
        if log.fdc_id:
            food_item = db.session.get(Food, log.fdc_id)
            if food_item:
                # Always add grams as an option
                available_portions.append(SimpleNamespace(display_text='g', value_string='g'))
                for p in food_item.portions:
                    display_text = f"{p.portion_description} ({p.gram_weight}g)"
                    available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))
        elif log.my_food_id:
            food_item = db.session.get(MyFood, log.my_food_id)
            if food_item:
                # Always add grams as an option
                available_portions.append(SimpleNamespace(display_text='g', value_string='g'))
                for p in food_item.portions:
                    display_text = f"{p.description} ({p.gram_weight}g)"
                    available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))
        elif log.recipe_id:
            food_item = db.session.get(Recipe, log.recipe_id)
            if food_item:
                # For recipes, portions are defined by RecipePortion
                available_portions.append(SimpleNamespace(display_text='g', value_string='g')) # Always allow grams
                for p in food_item.portions:
                    display_text = f"{p.description} ({p.gram_weight}g)"
                    available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))

        if food_item:
            # Calculate display amount based on serving type
            gram_weight = 1.0
            if log.serving_type and log.serving_type != 'g':
                try:
                    # Example serving_type string: "cup (128g)"
                    gram_weight = float(log.serving_type.split('(')[-1].replace('g)', ''))
                except (IndexError, ValueError):
                    gram_weight = 1.0 # Fallback

            display_amount = log.amount_grams / gram_weight if gram_weight > 0 else log.amount_grams
            
            nutrition = calculate_nutrition_for_items([log])
            description_to_display = food_item.description if hasattr(food_item, 'description') else food_item.name
            meals[log.meal_name].append({
                'log_id': log.id,
                'description': description_to_display,
                'amount': display_amount,
                'nutrition': nutrition,
                'portions': available_portions,
                'serving_type': log.serving_type
            })

    prev_date = log_date - timedelta(days=1)
    next_date = log_date + timedelta(days=1)

    return render_template('diary/diary.html', date=log_date, meals=meals, totals=totals, prev_date=prev_date, next_date=next_date)

@diary_bp.route('/diary/search/<string:log_date_str>/<string:meal_name>', methods=['GET', 'POST'])
@login_required
def search_for_diary(log_date_str, meal_name):
    log_date = date.fromisoformat(log_date_str)
    search_results = []
    search_term = request.form.get('search_term')

    if request.method == 'POST' and search_term:
        usda_results = db.session.query(Food).filter(Food.description.ilike(f'%{search_term}%')).options(selectinload(Food.portions).selectinload(Portion.measure_unit)).limit(20).all()
        my_food_results = MyFood.query.filter_by(user_id=current_user.id).filter(MyFood.description.ilike(f'%{search_term}%')).options(selectinload(MyFood.portions)).limit(20).all()
        my_meal_results = MyMeal.query.filter_by(user_id=current_user.id).filter(MyMeal.name.ilike(f'%{search_term}%')).limit(20).all()
    else:
        usda_results = []
        my_food_results = MyFood.query.filter_by(user_id=current_user.id).options(selectinload(MyFood.portions)).limit(20).all()
        my_meal_results = MyMeal.query.filter_by(user_id=current_user.id).limit(20).all()

    for item in usda_results:
        item.type = 'usda'
        search_results.append(item)
    for item in my_food_results:
        item.type = 'my_food'
        search_results.append(item)
    for item in my_meal_results:
        item.type = 'my_meal'
        search_results.append(item)

    url_action = 'diary.add_entry'
    url_params = {'log_date': log_date.isoformat(), 'meal_name': meal_name}

    return render_template('diary/search.html', log_date=log_date, meal_name=meal_name, search_results=search_results, search_term=search_term, url_action=url_action, url_params=url_params)

@diary_bp.route('/my_meals/search/<int:meal_id>', methods=['GET', 'POST'])
@login_required
def search_for_meal_item(meal_id):
    meal = db.session.get(MyMeal, meal_id)
    if not meal or meal.user_id != current_user.id:
        flash('Meal not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.my_meals'))

    search_results = []
    search_term = request.form.get('search_term')

    if request.method == 'POST' and search_term:
        usda_results = db.session.query(Food).filter(Food.description.ilike(f'%{search_term}%')).limit(20).all()
        my_food_results = MyFood.query.filter_by(user_id=current_user.id).filter(MyFood.description.ilike(f'%{search_term}%')).limit(20).all()
        # Exclude the current meal from the search results to prevent circular dependencies
        my_meal_results = MyMeal.query.filter_by(user_id=current_user.id).filter(MyMeal.name.ilike(f'%{search_term}%')).filter(MyMeal.id != meal_id).limit(20).all()
        recipe_results = Recipe.query.filter_by(user_id=current_user.id).filter(Recipe.name.ilike(f'%{search_term}%')).limit(20).all()
    else:
        usda_results = []
        my_food_results = MyFood.query.filter_by(user_id=current_user.id).limit(20).all()
        my_meal_results = MyMeal.query.filter_by(user_id=current_user.id).filter(MyMeal.id != meal_id).limit(20).all()
        recipe_results = Recipe.query.filter_by(user_id=current_user.id).limit(20).all()

    for item in usda_results:
        item.type = 'usda'
        search_results.append(item)
    for item in my_food_results:
        item.type = 'my_food'
        search_results.append(item)
    for item in my_meal_results:
        item.type = 'my_meal'
        search_results.append(item)
    for item in recipe_results:
        item.type = 'recipe'
        search_results.append(item)

    url_action = 'diary.add_meal_item'
    url_params = {'meal_id': meal_id}

    return render_template('diary/search.html', meal=meal, search_results=search_results, search_term=search_term, url_action=url_action, url_params=url_params)

@diary_bp.route('/diary/add_meal', methods=['POST'])
@login_required
def add_meal_to_diary():
    log_date_str = request.form.get('log_date')
    meal_name = request.form.get('meal_name')
    meal_id = request.form.get('meal_id', type=int)

    if log_date_str and meal_name and meal_id:
        log_date = date.fromisoformat(log_date_str)
        meal = db.session.get(MyMeal, meal_id)
        if meal and meal.user_id == current_user.id:
            for item in meal.items:
                new_log = DailyLog(
                    user_id=current_user.id,
                    log_date=log_date,
                    meal_name=meal_name,
                    amount_grams=item.amount_grams,
                    fdc_id=item.fdc_id,
                    my_food_id=item.my_food_id,
                    recipe_id=item.recipe_id
                )
                db.session.add(new_log)
            db.session.commit()
            flash(f'Meal "{meal.name}" added to diary.', 'success')
        else:
            flash('Meal not found or you do not have permission to add it.', 'danger')
    else:
        flash('Invalid data.', 'danger')

    return redirect(url_for('diary.diary', log_date_str=log_date_str))


@diary_bp.route('/diary/add_entry', methods=['POST'])
@login_required
def add_entry():
    log_date_str = request.form.get('log_date')
    meal_name = request.form.get('meal_name')
    quantity = request.form.get('quantity', type=float)
    portion_id = request.form.get('portion_id')
    fdc_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'usda' else None
    my_food_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'my_food' else None
    recipe_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'recipe' else None

    if log_date_str and meal_name and quantity and portion_id:
        log_date = date.fromisoformat(log_date_str)
        amount_grams = 0

        if portion_id == 'g':
            amount_grams = quantity
        else:
            if fdc_id:
                portion = db.session.get(Portion, int(portion_id))
                if portion:
                    amount_grams = portion.gram_weight * quantity
            elif my_food_id:
                portion = db.session.get(MyPortion, int(portion_id))
                if portion:
                    amount_grams = portion.gram_weight * quantity
            elif recipe_id:
                portion = db.session.get(RecipePortion, int(portion_id))
                if portion:
                    amount_grams = portion.gram_weight * quantity
        
        if amount_grams > 0:
            new_log = DailyLog(
                user_id=current_user.id,
                log_date=log_date,
                meal_name=meal_name,
                amount_grams=amount_grams,
                fdc_id=fdc_id,
                my_food_id=my_food_id,
                recipe_id=recipe_id
            )
            db.session.add(new_log)
            db.session.commit()
            flash('Food added to diary.', 'success')
        else:
            flash('Invalid portion selected.', 'danger')
    else:
        flash('Invalid data.', 'danger')

    return redirect(url_for('diary.diary', log_date_str=log_date_str))

@diary_bp.route('/my_meals/add_item/<int:meal_id>', methods=['POST'])
@login_required
def add_meal_item(meal_id):
    meal = db.session.get(MyMeal, meal_id)
    if not meal or meal.user_id != current_user.id:
        flash('Meal not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.my_meals'))

    fdc_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'usda' else None
    my_food_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'my_food' else None
    recipe_id = request.form.get('food_id', type=int) if request.form.get('food_type') == 'recipe' else None

    source_meal_id = request.form.get('source_meal_id', type=int)
    quantity = request.form.get('quantity', type=float) # Get quantity for multiplier

    # Force reload comment

    if source_meal_id:
        source_meal = db.session.get(MyMeal, source_meal_id)
        if source_meal and source_meal.user_id == current_user.id:
            for item in source_meal.items:
                new_item = MyMealItem(
                    meal=meal,
                    fdc_id=item.fdc_id,
                    my_food_id=item.my_food_id,
                    recipe_id=item.recipe_id,
                    amount_grams=item.amount_grams * quantity # Apply multiplier here
                )
                db.session.add(new_item)
            db.session.commit()
            flash(f'Items from meal "{source_meal.name}" added.', 'success')
        else:
            flash('Source meal not found or you do not have permission to add it.', 'danger')
    elif fdc_id or my_food_id or recipe_id:
        new_item = MyMealItem(
            meal=meal,
            fdc_id=fdc_id,
            my_food_id=my_food_id,
            recipe_id=recipe_id,
            amount_grams=quantity
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Item added to meal.', 'success')
    else:
        flash('Invalid food item.', 'danger')

    return redirect(url_for('diary.edit_meal', meal_id=meal.id))

@diary_bp.route('/diary/delete/<int:log_id>', methods=['POST'])
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

@diary_bp.route('/my_meals/delete/<int:meal_id>', methods=['POST'])
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

@diary_bp.route('/diary/update_entry/<int:log_id>', methods=['POST'])
@login_required
def update_entry(log_id):
    log_entry = db.session.get(DailyLog, log_id)
    if not log_entry or log_entry.user_id != current_user.id:
        flash('Entry not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('diary.diary'))

    amount = request.form.get('amount', type=float)
    serving_type = request.form.get('serving_type')

    if amount and serving_type:
        # Find the gram weight from the serving type string
        gram_weight = 1.0
        if serving_type != 'g':
            # Example serving_type string: "cup (128g)"
            try:
                # Extract the number from the parentheses
                gram_weight = float(serving_type.split('(')[1].split('g')[0])
            except (IndexError, ValueError):
                flash('Invalid serving type format.', 'danger')
                return redirect(url_for('diary.diary', log_date_str=log_entry.log_date.isoformat()))

        log_entry.amount_grams = amount * gram_weight
        log_entry.serving_type = serving_type
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
        item.available_portions = []
        if item.fdc_id:
            item.food = db.session.get(Food, item.fdc_id)
            if item.food:
                item.available_portions.append(SimpleNamespace(display_text='g', value_string='g'))
                for p in item.food.portions:
                    display_text = f"{p.portion_description} ({p.gram_weight}g)"
                    item.available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))
        elif item.my_food_id and item.my_food:
            item.available_portions.append(SimpleNamespace(display_text='g', value_string='g'))
            for p in item.my_food.portions:
                display_text = f"{p.description} ({p.gram_weight}g)"
                item.available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))
        elif item.recipe_id and item.recipe:
            item.available_portions.append(SimpleNamespace(display_text='g', value_string='g'))
            for p in item.recipe.portions:
                display_text = f"{p.description} ({p.gram_weight}g)"
                item.available_portions.append(SimpleNamespace(display_text=display_text, value_string=display_text))

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

    print(f"DEBUG: Attempting to delete item {item.id} from meal {meal.id}")
    print(f"DEBUG: Item state before delete: {db.inspect(item).persistent}")
    db.session.delete(item)
    print(f"DEBUG: Item state after db.session.delete: {db.inspect(item).deleted}")
    db.session.commit()
    print(f"DEBUG: Item {item.id} deleted and committed.")
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
    meals = MyMeal.query.filter_by(user_id=current_user.id).options(
        joinedload(MyMeal.items).joinedload(MyMealItem.my_food),
        joinedload(MyMeal.items).joinedload(MyMealItem.recipe)
    ).all()

    for meal in meals:
        for item in meal.items:
            if item.fdc_id:
                item.usda_food = db.session.get(Food, item.fdc_id)
    
    return render_template('diary/my_meals.html', meals=meals)

@diary_bp.route('/my_meals/update_item/<int:item_id>', methods=['POST'])
@login_required
def update_meal_item(item_id):
    item = db.session.get(MyMealItem, item_id)
    if not item or item.meal.user_id != current_user.id:
        flash('Item not found or you do not have permission to edit it.', 'danger')
        return redirect(request.referrer or url_for('diary.my_meals'))

    quantity = request.form.get('quantity', type=float)
    serving_type = request.form.get('serving_type')

    if quantity and serving_type:
        gram_weight = 1.0
        if serving_type != 'g':
            try:
                gram_weight = float(serving_type.split('(')[-1].split('g')[0])
            except (IndexError, ValueError):
                flash('Invalid serving type format.', 'danger')
                return redirect(url_for('diary.edit_meal', meal_id=item.my_meal_id))

        item.amount_grams = quantity * gram_weight
        db.session.commit()
        flash('Meal item updated.', 'success')
    else:
        flash('Invalid data.', 'danger')

    return redirect(url_for('diary.edit_meal', meal_id=item.my_meal_id))