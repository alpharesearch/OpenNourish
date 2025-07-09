from flask import render_template, request, flash, redirect, url_for, current_app
from . import search_bp
from models import db, Food, MyFood, Recipe, MyMeal, DailyLog, RecipeIngredient, MyMealItem, UnifiedPortion, FoodNutrient
from flask_login import login_required, current_user
from datetime import date
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, selectinload
from opennourish.utils import calculate_recipe_nutrition_per_100g

@search_bp.route('/', methods=['GET', 'POST'])
@login_required
def search():
    search_term = request.form.get('search_term') or request.args.get('search_term', '')
    include_friends = request.form.get('include_friends') == 'true' or request.args.get('include_friends') == 'true'
    results = {
        "usda_foods": [],
        "my_foods": [],
        "recipes": [],
        "my_meals": []
    }
    target = request.args.get('target') or request.form.get('target')
    recipe_id = request.args.get('recipe_id') or request.form.get('recipe_id')
    log_date = request.args.get('log_date') or request.form.get('log_date')
    meal_name = request.args.get('meal_name') or request.form.get('meal_name')
    search_mode = request.form.get('search_mode') or request.args.get('search_mode', 'all') # 'all' or 'usda_only'
    current_app.logger.debug(f"Debug: search_mode in search route: {search_mode}")
    current_app.logger.debug(f"Debug: request.method: {request.method}, target: {target}, search_term: {search_term}")

    if search_term:
        current_app.logger.debug(f"Debug: Performing search for term: '{search_term}'")
        # Search USDA Foods
        usda_foods_query = Food.query.options(
            selectinload(Food.nutrients).selectinload(FoodNutrient.nutrient)
        ).filter(Food.description.ilike(f'%{search_term}%')).limit(10).all()
        current_app.logger.debug(f"Debug: USDA Foods found: {len(usda_foods_query)}")
        
        for food in usda_foods_query:
            # Manually fetch portions for USDA food
            usda_portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()
            results["usda_foods"].append({
                'fdc_id': food.fdc_id,
                'description': food.description,
                'has_portions': bool(usda_portions),
                'portions': usda_portions,
                'has_ingredients': bool(food.ingredients),
                'has_rich_nutrients': len(food.nutrients) > 20,
                'detail_url': url_for('main.food_detail', fdc_id=food.fdc_id)
            })

        if search_mode != 'usda_only':
            friend_ids = [friend.id for friend in current_user.friends]
            
            # Search MyFoods
            my_foods_query_builder = MyFood.query.options(selectinload(MyFood.portions), joinedload(MyFood.user))
            my_foods_filter = [MyFood.description.ilike(f'%{search_term}%')]
            if include_friends and friend_ids:
                my_foods_filter.append(or_(MyFood.user_id == current_user.id, MyFood.user_id.in_(friend_ids)))
            else:
                my_foods_filter.append(MyFood.user_id == current_user.id)
            
            my_foods_query = my_foods_query_builder.filter(*my_foods_filter).limit(10).all()
            current_app.logger.debug(f"Debug: MyFoods found: {len(my_foods_query)}")
            
            for food in my_foods_query:
                results["my_foods"].append({
                    'id': food.id,
                    'description': food.description,
                    'user_id': food.user_id,
                    'user': food.user,
                    'has_portions': bool(food.portions),
                    'portions': food.portions,
                    'has_ingredients': bool(food.ingredients)
                })

            # Search Recipes
            recipes_query_builder = Recipe.query.options(selectinload(Recipe.ingredients), selectinload(Recipe.portions), joinedload(Recipe.user))
            recipes_filter = [Recipe.name.ilike(f'%{search_term}%')]
            if include_friends and friend_ids:
                recipes_filter.append(or_(Recipe.user_id == current_user.id, Recipe.user_id.in_(friend_ids)))
            else:
                recipes_filter.append(or_(Recipe.user_id == current_user.id, Recipe.is_public == True))

            recipes_query = recipes_query_builder.filter(*recipes_filter).limit(10).all()
            current_app.logger.debug(f"Debug: Recipes found: {len(recipes_query)}")
            
            for recipe in recipes_query:
                nutrition_per_100g = calculate_recipe_nutrition_per_100g(recipe)
                results["recipes"].append({
                    'id': recipe.id,
                    'name': recipe.name,
                    'user_id': recipe.user_id,
                    'user': recipe.user,
                    'has_ingredients': bool(recipe.instructions),
                    'has_portions': bool(recipe.portions),
                    'portions': recipe.portions,
                    'calories_per_100g': nutrition_per_100g['calories'],
                    'protein_per_100g': nutrition_per_100g['protein'],
                    'carbs_per_100g': nutrition_per_100g['carbs'],
                    'fat_per_100g': nutrition_per_100g['fat']
                })

            # Search MyMeals (Friends content not applicable)
            my_meals_query = MyMeal.query.options(
                selectinload(MyMeal.items)
            ).filter(MyMeal.name.ilike(f'%{search_term}%'), MyMeal.user_id == current_user.id).limit(10).all()
            current_app.logger.debug(f"Debug: MyMeals found: {len(my_meals_query)}")
            
            for meal in my_meals_query:
                results["my_meals"].append({
                    'id': meal.id,
                    'name': meal.name,
                    'has_items': bool(meal.items)
                })
    elif request.method == 'GET' and not search_term and target == 'diary':
        # ... (rest of the function remains the same)
        # Get top 10 most used USDA Foods
        top_usda_foods_ids = db.session.query(DailyLog.fdc_id, db.func.count(DailyLog.fdc_id)).\
                            filter(DailyLog.user_id == current_user.id, DailyLog.fdc_id.isnot(None)).\
                            group_by(DailyLog.fdc_id).order_by(db.func.count(DailyLog.fdc_id).desc()).limit(10).all()
        
        usda_food_ids = [item[0] for item in top_usda_foods_ids]
        if usda_food_ids:
            usda_foods = Food.query.options(
                selectinload(Food.portions),
                selectinload(Food.nutrients).selectinload(FoodNutrient.nutrient)
            ).filter(Food.fdc_id.in_(usda_food_ids)).all()
            
            # Sort by usage count
            usda_foods_dict = {food.fdc_id: food for food in usda_foods}
            for fdc_id, _ in top_usda_foods_ids:
                food = usda_foods_dict.get(fdc_id)
                if food:
                    results["usda_foods"].append({
                        'fdc_id': food.fdc_id,
                        'description': food.description,
                        'has_portions': bool(UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).first()),
                        'has_ingredients': bool(food.ingredients),
                        'has_rich_nutrients': len(food.nutrients) > 20
                    })

        # Get top 10 most used MyFoods
        top_my_foods_ids = db.session.query(DailyLog.my_food_id, db.func.count(DailyLog.my_food_id)).\
                        filter(DailyLog.user_id == current_user.id, DailyLog.my_food_id.isnot(None)).\
                        group_by(DailyLog.my_food_id).order_by(db.func.count(DailyLog.my_food_id).desc()).limit(10).all()
        
        my_food_ids = [item[0] for item in top_my_foods_ids]
        if my_food_ids:
            my_foods = MyFood.query.options(
                selectinload(MyFood.portions)
            ).filter(MyFood.id.in_(my_food_ids), MyFood.user_id == current_user.id).all()
            
            my_foods_dict = {food.id: food for food in my_foods}
            for my_food_id, _ in top_my_foods_ids:
                food = my_foods_dict.get(my_food_id)
                if food:
                    results["my_foods"].append({
                        'id': food.id,
                        'description': food.description,
                        'has_portions': bool(UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).first()),
                        'has_ingredients': bool(food.ingredients)
                    })

        # Get top 10 most used Recipes
        top_recipes_ids = db.session.query(DailyLog.recipe_id, db.func.count(DailyLog.recipe_id)).\
                        filter(DailyLog.user_id == current_user.id, DailyLog.recipe_id.isnot(None)).\
                        group_by(DailyLog.recipe_id).order_by(db.func.count(DailyLog.recipe_id).desc()).limit(10).all()
        
        recipe_ids = [item[0] for item in top_recipes_ids]
        if recipe_ids:
            recipes = Recipe.query.options(
                selectinload(Recipe.ingredients),
                selectinload(Recipe.portions)
            ).filter(Recipe.id.in_(recipe_ids), Recipe.user_id == current_user.id).all()
            
            recipes_dict = {recipe.id: recipe for recipe in recipes}
            for recipe_id, _ in top_recipes_ids:
                recipe = recipes_dict.get(recipe_id)
                if recipe:
                    nutrition_per_100g = calculate_recipe_nutrition_per_100g(recipe)
                    results["recipes"].append({
                        'id': recipe.id,
                        'name': recipe.name,
                        'has_ingredients': bool(recipe.instructions),
                        'has_portions': bool(recipe.portions),
                        'calories_per_100g': nutrition_per_100g['calories'],
                        'protein_per_100g': nutrition_per_100g['protein'],
                        'carbs_per_100g': nutrition_per_100g['carbs'],
                        'fat_per_100g': nutrition_per_100g['fat']
                    })

        # Get top 10 most used MyMeals
        top_my_meals = MyMeal.query.filter_by(user_id=current_user.id).order_by(MyMeal.usage_count.desc()).limit(10).all()
        
        if top_my_meals:
            for meal in top_my_meals:
                results["my_meals"].append({
                    'id': meal.id,
                    'name': meal.name,
                    'has_items': bool(meal.items)
                })
    return render_template('search/index.html',
                           search_term=search_term,
                           results=results,
                           target=target,
                           recipe_id=recipe_id,
                           log_date=log_date,
                           meal_name=meal_name,
                           search_mode=search_mode,
                           include_friends=include_friends)

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
    quantity = float(request.form.get('quantity', 1))
    portion_id = request.form.get('portion_id')
    if portion_id is None:
        portion_id = 'g'

    amount_grams = 0
    serving_type = 'g'
    if portion_id == 'g':
        amount_grams = quantity
    else:
        portion = db.session.get(UnifiedPortion, int(portion_id))
        if portion:
            amount_grams = quantity * portion.gram_weight
            serving_type = portion.full_description_str
        else:
            flash('Invalid portion selected.', 'danger')
            return redirect(request.referrer)

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
                        portion_id_fk=int(portion_id) if portion_id != 'g' else None
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{food.description} added to your diary.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food and food.user_id == current_user.id:
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        my_food_id=food.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=int(portion_id) if portion_id != 'g' else None
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{food.description} added to your diary.', 'success')
                else:
                    flash('My Food not found or not authorized.', 'danger')
            elif food_type == 'recipe':
                recipe = db.session.get(Recipe, food_id)
                if recipe and (recipe.user_id == current_user.id or recipe.is_public):
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        recipe_id=recipe.id,
                        amount_grams=amount_grams,
                        serving_type=serving_type,
                        portion_id_fk=int(portion_id) if portion_id != 'g' else None
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{recipe.name} added to your diary.', 'success')
                else:
                    flash('Recipe not found or not authorized.', 'danger')
            elif food_type == 'my_meal':
                my_meal = db.session.get(MyMeal, food_id)
                if my_meal and my_meal.user_id == current_user.id:
                    my_meal.usage_count += 1
                    for item in my_meal.items:
                        daily_log = DailyLog(
                            user_id=current_user.id,
                            log_date=log_date,
                            meal_name=meal_name,
                            fdc_id=item.fdc_id,
                            my_food_id=item.my_food_id,
                            recipe_id=item.recipe_id,
                            amount_grams=item.amount_grams * (quantity / 100)
                        )
                        db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{my_meal.name} (expanded) added to your diary.', 'success')
                else:
                    flash('My Meal not found or not authorized.', 'danger')
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
                        amount_grams=amount_grams
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{food.description} added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food and food.user_id == current_user.id:
                    ingredient = RecipeIngredient(
                        recipe_id=target_recipe.id,
                        my_food_id=food.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{food.description} added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('My Food not found or not authorized.', 'danger')
            elif food_type == 'recipe':
                sub_recipe = db.session.get(Recipe, food_id)
                if sub_recipe and (sub_recipe.user_id == current_user.id or sub_recipe.is_public):
                    ingredient = RecipeIngredient(
                        recipe_id=target_recipe.id,
                        recipe_id_link=sub_recipe.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{sub_recipe.name} added as ingredient to recipe {target_recipe.name}.', 'success')
                else:
                    flash('Sub-recipe not found or not authorized.', 'danger')
            elif food_type == 'my_meal':
                my_meal = db.session.get(MyMeal, food_id)
                if my_meal and my_meal.user_id == current_user.id:
                    for item in my_meal.items:
                        ingredient = RecipeIngredient(
                            recipe_id=target_recipe.id,
                            fdc_id=item.fdc_id,
                            my_food_id=item.my_food_id,
                            amount_grams=item.amount_grams
                        )
                        db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{my_meal.name} (expanded) added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('My Meal not found or not authorized.', 'danger')
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
                        amount_grams=amount_grams
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{food.description} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('USDA Food not found.', 'danger')
            elif food_type == 'my_food':
                food = db.session.get(MyFood, food_id)
                if food and food.user_id == current_user.id:
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        my_food_id=food.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{food.description} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('My Food not found or not authorized.', 'danger')
            elif food_type == 'recipe':
                recipe = db.session.get(Recipe, food_id)
                if recipe and recipe.user_id == current_user.id:
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        recipe_id=recipe.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{recipe.name} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('Recipe not found or not authorized.', 'danger')
            elif food_type == 'my_meal':
                sub_my_meal = db.session.get(MyMeal, food_id)
                if sub_my_meal and sub_my_meal.user_id == current_user.id:
                    meal_item = MyMealItem(
                        my_meal_id=target_my_meal.id,
                        my_meal_id_link=sub_my_meal.id,
                        amount_grams=amount_grams
                    )
                    db.session.add(meal_item)
                    db.session.commit()
                    flash(f'{sub_my_meal.name} added to meal {target_my_meal.name}.', 'success')
                else:
                    flash('Sub-meal not found or not authorized.', 'danger')
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
