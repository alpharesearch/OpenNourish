from flask import render_template, request, flash, redirect, url_for, current_app, jsonify
from . import search_bp
from models import db, Food, MyFood, Recipe, MyMeal, DailyLog, RecipeIngredient, MyMealItem, UnifiedPortion, FoodNutrient, FoodCategory
from flask_login import login_required, current_user
from datetime import date
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload, selectinload
import math
from opennourish.utils import calculate_recipe_nutrition_per_100g, remove_leading_one

class ManualPagination:
    """A duck-typed pagination object for manual pagination."""
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
        if self.per_page > 0:
            self.pages = math.ceil(total / per_page)
        else:
            self.pages = 0

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    def iter_pages(self, left_edge=1, left_current=1, right_current=2, right_edge=1):
        last = 0
        for num in range(1, self.pages + 1):
            if (
                num <= left_edge
                or (self.page - left_current - 1 < num < self.page + right_current)
                or num > self.pages - right_edge
            ):
                if last + 1 != num:
                    yield None
                yield num
                last = num

@search_bp.route('/by_upc', methods=['GET'])
@login_required
def search_by_upc():
    upc = request.args.get('upc', '')
    if not upc:
        return jsonify({'error': 'UPC code is required'}), 400

    friend_ids = [friend.id for friend in current_user.friends]

    # Priority 1: Current user's MyFood
    user_food = MyFood.query.filter_by(user_id=current_user.id, upc=upc).first()
    if user_food:
        user_food_portions = UnifiedPortion.query.filter_by(my_food_id=user_food.id).all()
        portions_data = [{'id': p.id, 'description': p.full_description_str, 'gram_weight': p.gram_weight} for p in user_food_portions]
        return jsonify({
            'status': 'found',
            'source': 'my_food',
            'food': {
                'id': user_food.id,
                'description': user_food.description,
                'type': 'my_food',
                'portions': portions_data
            }
        })

    # Priority 2: Current user's Recipes
    user_recipe = Recipe.query.filter_by(user_id=current_user.id, upc=upc).first()
    if user_recipe:
        user_recipe_portions = UnifiedPortion.query.filter_by(recipe_id=user_recipe.id).all()
        portions_data = [{'id': p.id, 'description': p.full_description_str, 'gram_weight': p.gram_weight} for p in user_recipe_portions]
        return jsonify({
            'status': 'found',
            'source': 'my_recipe',
            'food': {
                'id': user_recipe.id,
                'description': user_recipe.name,
                'type': 'recipe',
                'portions': portions_data
            }
        })

    # Priority 3: Friends' MyFood
    if friend_ids:
        friends_food = MyFood.query.filter(MyFood.user_id.in_(friend_ids), MyFood.upc==upc).first()
        if friends_food:
            friends_food_portions = UnifiedPortion.query.filter_by(my_food_id=friends_food.id).all()
            portions_data = [{'id': p.id, 'description': p.full_description_str, 'gram_weight': p.gram_weight} for p in friends_food_portions]
            return jsonify({
                'status': 'found',
                'source': 'friend_food',
                'food': {
                    'id': friends_food.id,
                    'description': friends_food.description,
                    'type': 'my_food',
                    'portions': portions_data
                }
            })

    # Priority 4: Friends' Recipes (public)
    if friend_ids:
        friends_recipe = Recipe.query.filter(
            Recipe.user_id.in_(friend_ids),
            Recipe.upc==upc,
            Recipe.is_public == True
        ).first()
        if friends_recipe:
            friends_recipe_portions = UnifiedPortion.query.filter_by(recipe_id=friends_recipe.id).all()
            portions_data = [{'id': p.id, 'description': p.full_description_str, 'gram_weight': p.gram_weight} for p in friends_recipe_portions]
            return jsonify({
                'status': 'found',
                'source': 'friend_recipe',
                'food': {
                    'id': friends_recipe.id,
                    'description': friends_recipe.name,
                    'type': 'recipe',
                    'portions': portions_data
                }
            })

    # Priority 5: USDA Database
    usda_food = Food.query.filter_by(upc=upc).first()
    if usda_food:
        # Ensure a 1-gram portion exists for this USDA food
        one_gram_portion = UnifiedPortion.query.filter_by(fdc_id=usda_food.fdc_id, gram_weight=1.0).first()
        if not one_gram_portion:
            one_gram_portion = UnifiedPortion(
                fdc_id=usda_food.fdc_id,
                amount=1.0,
                measure_unit_description="g",
                portion_description="",
                modifier="",
                gram_weight=1.0
            )
            db.session.add(one_gram_portion)
            db.session.commit()
            current_app.logger.debug(f"Created 1-gram portion for USDA food FDC_ID: {usda_food.fdc_id} during UPC scan.")

        usda_food_portions = UnifiedPortion.query.filter_by(fdc_id=usda_food.fdc_id).all()
        portions_data = [{'id': p.id, 'description': p.full_description_str, 'gram_weight': p.gram_weight} for p in usda_food_portions]
        return jsonify({
            'status': 'found',
            'source': 'usda',
            'food': {
                'fdc_id': usda_food.fdc_id,
                'description': usda_food.description,
                'type': 'usda',
                'portions': portions_data,
                'nutrition_label_svg_url': url_for('main.nutrition_label_svg', fdc_id=usda_food.fdc_id)
            }
        })

    return jsonify({'status': 'not_found'}), 404

@search_bp.route('/', methods=['GET', 'POST'])
@login_required
def search():
    search_term = request.values.get('search_term', '')
    per_page = request.values.get('per_page', 10, type=int)
    selected_category_id = request.values.get('food_category_id', type=int)

    # Fetch all food categories for the dropdown
    food_categories = FoodCategory.query.order_by(FoodCategory.description).all()

    # Separate page parameters for each category
    usda_page = request.values.get('usda_page', 1, type=int)
    my_foods_page = request.values.get('my_foods_page', 1, type=int)
    recipes_page = request.values.get('recipes_page', 1, type=int)
    my_meals_page = request.values.get('my_meals_page', 1, type=int)
    
    # Determine which categories to search
    search_my_foods = request.values.get('search_my_foods', 'false') == 'true'
    search_my_meals = request.values.get('search_my_meals', 'false') == 'true'
    search_recipes = request.values.get('search_recipes', 'false') == 'true'
    search_usda = request.values.get('search_usda', 'false') == 'true'
    search_friends = request.values.get('search_friends', 'false') == 'true'
    search_public = request.values.get('search_public', 'false') == 'true'

    # If no category boxes are checked, default to checking them all.
    # The 'friends' checkbox is treated as a separate modifier and is not defaulted to True.
    if not any([search_my_foods, search_my_meals, search_recipes, search_usda]):
        search_my_foods = search_my_meals = search_recipes = search_usda = True

    usda_foods_pagination = None
    my_foods_pagination = None
    recipes_pagination = None
    my_meals_pagination = None

    target = request.values.get('target')
    recipe_id = request.values.get('recipe_id')
    log_date = request.values.get('log_date')
    meal_name = request.values.get('meal_name')

    if search_term:
        user_ids_to_search = [current_user.id]
        if search_friends:
            friend_ids = [friend.id for friend in current_user.friends]
            if friend_ids:
                user_ids_to_search.extend(friend_ids)

        if search_usda:
            # Step 1: Get all matching food IDs from the USDA database first.
            usda_query = Food.query.filter(
                Food.description.ilike(f'%{search_term}%')
            )
            if selected_category_id:
                usda_query = usda_query.filter(Food.food_category_id == selected_category_id)
            
            all_matching_foods_query = usda_query.with_entities(Food.fdc_id, Food.description).all()

            if all_matching_foods_query:
                matching_fdc_ids = [food.fdc_id for food in all_matching_foods_query]
                food_descriptions = {food.fdc_id: food.description for food in all_matching_foods_query}

                # Step 2: Get portion counts for those IDs from the user database.
                portion_counts = dict(db.session.query(
                    UnifiedPortion.fdc_id,
                    func.count(UnifiedPortion.id)
                ).filter(
                    UnifiedPortion.fdc_id.in_(matching_fdc_ids)
                ).group_by(UnifiedPortion.fdc_id).all())

                # Step 3: Manually sort the food IDs in Python based on the desired logic.
                def sort_key(fdc_id):
                    description = food_descriptions[fdc_id].lower()
                    search_term_lower = search_term.lower()
                    
                    # Primary sort key: Portion count (descending)
                    portion_count = portion_counts.get(fdc_id, 0)
                    
                    # Secondary sort key: Relevance
                    if description == search_term_lower:
                        relevance = 1
                    elif description.startswith(search_term_lower):
                        relevance = 2
                    elif f' {search_term_lower} ' in f' {description} ':
                        relevance = 3
                    else:
                        relevance = 4
                    
                    # Tertiary sort key: Description length (ascending)
                    length = len(description)
                    
                    return (-portion_count, relevance, length)

                sorted_fdc_ids = sorted(matching_fdc_ids, key=sort_key)

                # Step 4: Paginate the sorted list of IDs.
                start = (usda_page - 1) * per_page
                end = start + per_page
                paginated_fdc_ids = sorted_fdc_ids[start:end]

                # Step 5: Fetch the full Food objects for the paginated IDs.
                if paginated_fdc_ids:
                    paginated_foods = Food.query.filter(Food.fdc_id.in_(paginated_fdc_ids)).all()
                    # Preserve the sorted order
                    food_map = {food.fdc_id: food for food in paginated_foods}
                    ordered_foods = [food_map[fdc_id] for fdc_id in paginated_fdc_ids]
                else:
                    ordered_foods = []

                # Step 6: Create a manual pagination object.
                usda_foods_pagination = ManualPagination(
                    page=usda_page,
                    per_page=per_page,
                    total=len(sorted_fdc_ids),
                    items=ordered_foods
                )
            else:
                usda_foods_pagination = ManualPagination(page=usda_page, per_page=per_page, total=0, items=[])
            # Manually add the detail_url to each item
            for food in usda_foods_pagination.items:
                food.detail_url = url_for('main.food_detail', fdc_id=food.fdc_id)
                
                # Ensure a 1-gram portion exists for this USDA food
                one_gram_portion = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id, gram_weight=1.0).first()
                if not one_gram_portion:
                    one_gram_portion = UnifiedPortion(
                        fdc_id=food.fdc_id,
                        amount=1.0,
                        measure_unit_description="g",
                        portion_description="",
                        modifier="",
                        gram_weight=1.0
                    )
                    db.session.add(one_gram_portion)
                    db.session.commit()
                    current_app.logger.debug(f"Created 1-gram portion for USDA food FDC_ID: {food.fdc_id} during search display.")
                
                # Fetch all portions, including the guaranteed 1-gram portion
                food.portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()

        if search_my_foods:
            my_foods_query = MyFood.query.filter(
                MyFood.description.ilike(f'%{search_term}%'),
                or_(MyFood.user_id.in_(user_ids_to_search), MyFood.user_id == None)
            )
            if selected_category_id:
                my_foods_query = my_foods_query.filter(MyFood.food_category_id == selected_category_id)
            my_foods_pagination = my_foods_query.paginate(page=my_foods_page, per_page=per_page, error_out=False)

        if search_recipes:
            recipe_query_filter = [Recipe.name.ilike(f'%{search_term}%')]
            
            # Construct the part of the query that handles ownership and public status
            user_and_public_filter = []
            user_and_public_filter.append(Recipe.user_id.in_(user_ids_to_search))
            user_and_public_filter.append(Recipe.user_id == None) # Include orphaned recipes
            if search_public:
                user_and_public_filter.append(Recipe.is_public == True)
            
            recipe_query_filter.append(or_(*user_and_public_filter))

            recipes_query = Recipe.query.filter(*recipe_query_filter)
            if selected_category_id:
                recipes_query = recipes_query.filter(Recipe.food_category_id == selected_category_id)
            recipes_pagination = recipes_query.paginate(page=recipes_page, per_page=per_page, error_out=False)

        if search_my_meals:
            my_meals_pagination = MyMeal.query.filter(
                MyMeal.name.ilike(f'%{search_term}%'),
                MyMeal.user_id == current_user.id
            ).paginate(page=my_meals_page, per_page=per_page, error_out=False)
    else:
        # No search term, so show frequently used items
        if search_my_foods:
            frequent_my_foods_subquery = db.session.query(
                DailyLog.my_food_id,
                func.count(DailyLog.my_food_id).label('count')
            ).filter(
                DailyLog.user_id == current_user.id,
                DailyLog.my_food_id.isnot(None)
            ).group_by(DailyLog.my_food_id).order_by(func.count(DailyLog.my_food_id).desc()).subquery()

            my_foods_pagination = MyFood.query.join(
                frequent_my_foods_subquery, MyFood.id == frequent_my_foods_subquery.c.my_food_id
            ).order_by(
                frequent_my_foods_subquery.c.count.desc()
            ).paginate(page=my_foods_page, per_page=per_page, error_out=False)

        if search_recipes:
            if search_public and not search_term:
                # If public is checked without a search term, find popular public recipes
                # by counting their occurrences in the DailyLog across all users.
                popular_recipes_subquery = db.session.query(
                    DailyLog.recipe_id,
                    func.count(DailyLog.recipe_id).label('count')
                ).filter(
                    DailyLog.recipe_id.isnot(None)
                ).group_by(DailyLog.recipe_id).order_by(func.count(DailyLog.recipe_id).desc()).subquery()

                recipes_pagination = Recipe.query.join(
                    popular_recipes_subquery, Recipe.id == popular_recipes_subquery.c.recipe_id
                ).filter(
                    Recipe.is_public == True
                ).order_by(
                    popular_recipes_subquery.c.count.desc()
                ).paginate(page=recipes_page, per_page=per_page, error_out=False)
            else:
                # Original behavior: frequently used from user's own log
                frequent_recipes_subquery = db.session.query(
                    DailyLog.recipe_id,
                    func.count(DailyLog.recipe_id).label('count')
                ).filter(
                    DailyLog.user_id == current_user.id,
                    DailyLog.recipe_id.isnot(None)
                ).group_by(DailyLog.recipe_id).order_by(func.count(DailyLog.recipe_id).desc()).subquery()

                recipes_pagination = Recipe.query.join(
                    frequent_recipes_subquery, Recipe.id == frequent_recipes_subquery.c.recipe_id
                ).order_by(
                    frequent_recipes_subquery.c.count.desc()
                ).paginate(page=recipes_page, per_page=per_page, error_out=False)

        if search_usda:
            # Step 1: Get paginated, ordered fdc_ids from the user database
            frequent_usda_ids_paginated = db.session.query(
                DailyLog.fdc_id
            ).filter(
                DailyLog.user_id == current_user.id,
                DailyLog.fdc_id.isnot(None)
            ).group_by(DailyLog.fdc_id).order_by(
                func.count(DailyLog.fdc_id).desc()
            ).paginate(page=usda_page, per_page=per_page, error_out=False)

            fdc_ids = [item.fdc_id for item in frequent_usda_ids_paginated.items]

            # Step 2: Fetch the actual Food objects from the USDA database
            if fdc_ids:
                usda_foods = Food.query.filter(Food.fdc_id.in_(fdc_ids)).all()
                # Preserve the order from the frequency query
                foods_map = {food.fdc_id: food for food in usda_foods}
                ordered_foods = [foods_map.get(fdc_id) for fdc_id in fdc_ids if foods_map.get(fdc_id)]
            else:
                ordered_foods = []

            # Step 3: Manually create a pagination object for the template
            usda_foods_pagination = ManualPagination(
                page=usda_page,
                per_page=per_page,
                total=frequent_usda_ids_paginated.total,
                items=ordered_foods
            )

            # Attach extra info needed by the template
            if usda_foods_pagination:
                for food in usda_foods_pagination.items:
                    food.detail_url = url_for('main.food_detail', fdc_id=food.fdc_id)
                    
                    # Ensure a 1-gram portion exists for this USDA food
                    one_gram_portion = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id, gram_weight=1.0).first()
                    if not one_gram_portion:
                        one_gram_portion = UnifiedPortion(
                            fdc_id=food.fdc_id,
                            amount=1.0,
                            measure_unit_description="g",
                            portion_description="",
                            modifier="",
                            gram_weight=1.0
                        )
                        db.session.add(one_gram_portion)
                        db.session.commit()
                        current_app.logger.debug(f"Created 1-gram portion for USDA food FDC_ID: {food.fdc_id} during search display (frequent). ")
                    
                    # Fetch all portions, including the guaranteed 1-gram portion
                    food.portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()
        
        if search_my_meals:
            my_meals_pagination = MyMeal.query.filter(
                MyMeal.user_id == current_user.id,
                MyMeal.usage_count > 0
            ).order_by(MyMeal.usage_count.desc()).paginate(page=my_meals_page, per_page=per_page, error_out=False)

    return render_template('search/index.html',
                           search_term=search_term,
                           usda_foods_pagination=usda_foods_pagination,
                           my_foods_pagination=my_foods_pagination,
                           recipes_pagination=recipes_pagination,
                           my_meals_pagination=my_meals_pagination,
                           target=target,
                           recipe_id=recipe_id,
                           log_date=log_date,
                           meal_name=meal_name,
                           search_my_foods=search_my_foods,
                           search_my_meals=search_my_meals,
                           search_recipes=search_recipes,
                           search_usda=search_usda,
                           search_friends=search_friends,
                           search_public=search_public,
                           usda_page=usda_page,
                           my_foods_page=my_foods_page,
                           recipes_page=recipes_page,
                           my_meals_page=my_meals_page,
                           food_categories=food_categories,
                           selected_category_id=selected_category_id)

@search_bp.route('/add_item', methods=['POST'])
@login_required
def add_item():
    food_id = request.form.get('food_id')
    food_type = request.form.get('food_type')
    target = request.form.get('target')
    if not target or target == 'None':
        target = 'my_foods'
    recipe_id = request.form.get('recipe_id')
    log_date_str = request.form.get('log_date')
    meal_name = request.form.get('meal_name')
    amount = float(request.form.get('amount', 1))
    portion_id_str = request.form.get('portion_id')

    # Ensure a 1-gram portion exists for USDA foods when they are added.
    # This is crucial for consistency across the application.
    if food_type == 'usda':
        food_id_int = int(food_id)
        one_gram_portion = UnifiedPortion.query.filter_by(fdc_id=food_id_int, gram_weight=1.0).first()
        if not one_gram_portion:
            one_gram_portion = UnifiedPortion(
                fdc_id=food_id_int,
                amount=1.0,
                measure_unit_description="g",
                portion_description="",
                modifier="",
                gram_weight=1.0
            )
            db.session.add(one_gram_portion)
            db.session.commit()
            current_app.logger.debug(f"Created 1-gram portion for USDA food FDC_ID: {food_id_int} during add_item.")

    if food_type == 'my_meal':
        my_meal = db.session.get(MyMeal, food_id)
        if not my_meal:
            flash('My Meal not found.', 'danger')
            return redirect(request.referrer or url_for('diary.diary'))

        # Check if the user is trying to access a meal that is not theirs
        # and the owner has been deleted.
        if my_meal.user_id != current_user.id and not my_meal.user:
             flash('This meal belongs to a deleted user and cannot be added.', 'info')
             return redirect(request.referrer or url_for('diary.diary'))
        
        if my_meal.user_id != current_user.id:
            flash('You are not authorized to add this meal.', 'danger')
            return redirect(request.referrer or url_for('diary.diary'))

        if target == 'diary':
            log_date = date.fromisoformat(log_date_str) if log_date_str else date.today()
            my_meal.usage_count += 1
            for item in my_meal.items:
                daily_log = DailyLog(
                    user_id=current_user.id,
                    log_date=log_date,
                    meal_name=meal_name,
                    fdc_id=item.fdc_id,
                    my_food_id=item.my_food_id,
                    recipe_id=item.recipe_id,
                    amount_grams=item.amount_grams,
                    serving_type=item.serving_type,
                    portion_id_fk=item.portion_id_fk
                )
                db.session.add(daily_log)
            db.session.commit()
            flash(f'"{my_meal.name}" (expanded) added to your diary.', 'success')
            return redirect(url_for('diary.diary', log_date_str=log_date_str))

        elif target == 'recipe':
            target_recipe = db.session.get(Recipe, recipe_id)
            if not target_recipe or target_recipe.user_id != current_user.id:
                flash('Recipe not found or not authorized.', 'danger')
                return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))
            
            for item in my_meal.items:
                ingredient = RecipeIngredient(
                    recipe_id=target_recipe.id,
                    fdc_id=item.fdc_id,
                    my_food_id=item.my_food_id,
                    recipe_id_link=item.recipe_id,
                    amount_grams=item.amount_grams,
                    serving_type=item.serving_type,
                    portion_id_fk=item.portion_id_fk
                )
                db.session.add(ingredient)
            db.session.commit()
            flash(f'"{my_meal.name}" (expanded) added to recipe {target_recipe.name}.', 'success')
            return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))
        
        else:
            flash(f'Cannot add a meal to the selected target: {target}.', 'danger')
            return redirect(request.referrer or url_for('diary.diary'))

    portion = None
    if portion_id_str:
        try:
            portion_id_int = int(portion_id_str)
            portion = db.session.get(UnifiedPortion, portion_id_int)
        except (ValueError, TypeError):
            flash('Invalid portion ID.', 'danger')
            return redirect(request.referrer)
    
    # If no portion was selected (portion_id_str is empty) and it's a USDA food,
    # default to the 1-gram portion that was just ensured to exist.
    if not portion and food_type == 'usda':
        portion = UnifiedPortion.query.filter_by(fdc_id=food_id_int, gram_weight=1.0).first()
        if not portion: # This should ideally not happen if the above logic worked
            flash('Could not find or create a default 1-gram portion for USDA food.', 'danger')
            return redirect(request.referrer)
    elif not portion: # For non-USDA foods, or if a portion_id_str was provided but invalid
        flash('Invalid portion selected.', 'danger')
        return redirect(request.referrer)

    amount_grams = amount * portion.gram_weight
    serving_type = portion.full_description_str
    portion_id_fk_value = portion.id

    try:
        if target == 'diary':
            if not log_date_str:
                flash('Log date is required for diary entries.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id, log_date=log_date_str, meal_name=meal_name))
            log_date = date.fromisoformat(log_date_str)

            if food_type == 'usda':
                food = db.session.get(Food, food_id)
                if food:
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        fdc_id=food.fdc_id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{food.description} added to your diary.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food:
                    if food.user_id != current_user.id and not food.user:
                        flash('This food belongs to a deleted user and cannot be added.', 'info')
                        return redirect(url_for('diary.diary', log_date_str=log_date_str))
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        my_food_id=food.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{food.description} added to your diary.', 'success')
                else:
                    flash('My Food not found.', 'danger')
            elif food_type == 'recipe':
                recipe = db.session.get(Recipe, food_id)
                if recipe:
                    if recipe.user_id != current_user.id and not recipe.user:
                        flash('This recipe belongs to a deleted user and cannot be added.', 'info')
                        return redirect(url_for('diary.diary', log_date_str=log_date_str))
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        recipe_id=recipe.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{recipe.name} added to your diary.', 'success')
                else:
                    flash('Recipe not found.', 'danger')
            else:
                flash('Invalid food type for diary.', 'danger')
            return redirect(url_for('diary.diary', log_date_str=log_date_str))

        elif target == 'recipe':
            if not recipe_id:
                flash('Recipe ID is required to add to a recipe.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
            
            target_recipe = db.session.get(Recipe, recipe_id)
            if not target_recipe or target_recipe.user_id != current_user.id:
                flash('Recipe not found or not authorized.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))

            if food_type == 'usda':
                food = db.session.get(Food, food_id)
                if food:
                    ingredient = RecipeIngredient(
                        recipe_id=target_recipe.id,
                        fdc_id=food.fdc_id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{food.description} added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food:
                    if food.user_id != current_user.id and not food.user:
                        flash('This food belongs to a deleted user and cannot be added as an ingredient.', 'info')
                        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))
                    ingredient = RecipeIngredient(
                        recipe_id=target_recipe.id,
                        my_food_id=food.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{food.description} added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('My Food not found.', 'danger')
            elif food_type == 'recipe':
                sub_recipe = db.session.get(Recipe, food_id)
                if not sub_recipe:
                    flash('Sub-recipe not found.', 'danger')
                    return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
                
                if sub_recipe.user_id != current_user.id and not sub_recipe.user:
                    flash('This recipe belongs to a deleted user and cannot be added as an ingredient.', 'info')
                    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))

                if sub_recipe.id == target_recipe.id:
                    flash('A recipe cannot be an ingredient of itself.', 'danger')
                    return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
                
                # If we reach here, it's a valid sub-recipe and not self-nesting
                ingredient = RecipeIngredient(
                    recipe_id=target_recipe.id,
                    recipe_id_link=sub_recipe.id,
                    amount_grams=amount_grams,
                    serving_type=serving_type,
                    portion_id_fk=portion_id_fk_value
                )
                db.session.add(ingredient)
                db.session.commit()
                flash(f'{sub_recipe.name} added as ingredient to recipe {target_recipe.name}.', 'success')
                return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))
            else:
                flash('Invalid food type for recipe.', 'danger')
            return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))

        elif target == 'meal':
            my_meal_id = recipe_id
            if not my_meal_id:
                flash('Meal ID is required to add to a meal.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
            
            target_my_meal = db.session.get(MyMeal, my_meal_id)
            if not target_my_meal or target_my_meal.user_id != current_user.id:
                flash('My Meal not found or not authorized.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))

            if food_type == 'usda':
                food = db.session.get(Food, food_id)
                if food:
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        fdc_id=food.fdc_id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{food.description} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food:
                    if food.user_id != current_user.id and not food.user:
                        flash('This food belongs to a deleted user and cannot be added to a meal.', 'info')
                        return redirect(url_for('diary.edit_meal', meal_id=my_meal_id))
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        my_food_id=food.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{food.description} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('My Food not found.', 'danger')
            elif food_type == 'recipe':
                recipe = db.session.get(Recipe, food_id)
                if recipe:
                    if recipe.user_id != current_user.id and not recipe.user:
                        flash('This recipe belongs to a deleted user and cannot be added to a meal.', 'info')
                        return redirect(url_for('diary.edit_meal', meal_id=my_meal_id))
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        recipe_id=recipe.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=portion_id_fk_value
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{recipe.name} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('Recipe not found.', 'danger')
            elif food_type == 'my_meal':
                sub_my_meal = db.session.get(MyMeal, food_id)
                if sub_my_meal:
                    if sub_my_meal.user_id != current_user.id and not sub_my_meal.user:
                        flash('This meal belongs to a deleted user and cannot be added to another meal.', 'info')
                        return redirect(url_for('diary.edit_meal', meal_id=my_meal_id))
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        my_meal_id_link=sub_my_meal.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{sub_my_meal.name} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('Sub-meal not found.', 'danger')
            else:
                flash('Invalid food type for meal.', 'danger')
            return redirect(url_for('diary.edit_meal', meal_id=my_meal_id))

        elif target == 'my_foods':
            if food_type == 'usda':
                usda_food = Food.query.filter_by(fdc_id=food_id).first_or_404()

                # Create a new MyFood object from the USDA food data
                my_food = MyFood(
                    user_id=current_user.id,
                    description=usda_food.description,
                    ingredients=usda_food.ingredients,
                    fdc_id=usda_food.fdc_id,
                    upc=usda_food.upc,
                    calories_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1008).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    protein_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1003).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    carbs_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1005).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    fat_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1004).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    saturated_fat_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1258).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    trans_fat_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1257).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    cholesterol_mg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1253).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    sodium_mg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1093).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    fiber_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1079).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    sugars_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=2000).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    vitamin_d_mcg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1110).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    calcium_mg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1087).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    iron_mg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1089).with_entities(FoodNutrient.amount).scalar() or 0.0,
                    potassium_mg_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1092).with_entities(FoodNutrient.amount).scalar() or 0.0
                )
                db.session.add(my_food)
                db.session.commit()

                flash(f'{usda_food.description} has been added to your foods.', 'success')
                return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))
            else:
                flash('Only USDA foods can be copied to My Foods via this method.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))

        else:
            flash('Invalid target for adding item.', 'danger')
            return redirect(url_for('search.search', target=target, recipe_id=recipe_id))

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')
        return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
