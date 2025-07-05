from flask import render_template, request, flash, redirect, url_for
from . import search_bp
from models import db, Food, MyFood, Recipe, MyMeal, DailyLog, RecipeIngredient, MyMealItem, Portion, MyPortion, FoodNutrient
from flask_login import login_required, current_user
from datetime import date

@search_bp.route('/', methods=['GET', 'POST'])
@login_required
def search():
    search_term = ""
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

    if request.method == 'POST' or request.args.get('search_term'):
        search_term = request.form.get('search_term', '').strip() or request.args.get('search_term', '').strip()
        if search_term:
            # Search USDA Foods
            usda_foods_query = Food.query.filter(Food.description.ilike(f'%{search_term}%')).limit(10).all()
            results["usda_foods"] = [{'fdc_id': food.fdc_id, 'description': food.description} for food in usda_foods_query]

            # Search MyFoods
            my_foods_query = MyFood.query.filter(MyFood.description.ilike(f'%{search_term}%')).limit(10).all()
            results["my_foods"] = [{'id': food.id, 'description': food.description} for food in my_foods_query]

            # Search Recipes
            recipes_query = Recipe.query.filter(Recipe.name.ilike(f'%{search_term}%')).limit(10).all()
            results["recipes"] = [{'id': recipe.id, 'name': recipe.name} for recipe in recipes_query]

            # Search MyMeals
            my_meals_query = MyMeal.query.filter(MyMeal.name.ilike(f'%{search_term}%')).limit(10).all()
            results["my_meals"] = [{'id': meal.id, 'name': meal.name} for meal in my_meals_query]

    return render_template('search/index.html',
                           search_term=search_term,
                           results=results,
                           target=target,
                           recipe_id=recipe_id,
                           log_date=log_date,
                           meal_name=meal_name)

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
    quantity = float(request.form.get('quantity', 100))

    try:
        if target == 'diary':
            if not log_date_str:
                flash('Log date is required for diary entries.', 'danger')
                return redirect(url_for('search.search', target=target, recipe_id=recipe_id))
            log_date = date.fromisoformat(log_date_str)

            if food_type == 'usda':
                food = db.session.get(Food, food_id)
                if food:
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        fdc_id=food.fdc_id,
                        amount_grams=quantity
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
                        amount_grams=quantity
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{food.description} added to your diary.', 'success')
                else:
                    flash('My Food not found or not authorized.', 'danger')
            elif food_type == 'recipe':
                recipe = db.session.get(Recipe, food_id)
                if recipe and recipe.user_id == current_user.id:
                    daily_log = DailyLog(
                        user_id=current_user.id,
                        log_date=log_date,
                        meal_name=meal_name,
                        recipe_id=recipe.id,
                        amount_grams=quantity
                    )
                    db.session.add(daily_log)
                    db.session.commit()
                    flash(f'{recipe.name} added to your diary.', 'success')
                else:
                    flash('Recipe not found or not authorized.', 'danger')
            elif food_type == 'my_meal':
                my_meal = db.session.get(MyMeal, food_id)
                if my_meal and my_meal.user_id == current_user.id:
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
                        amount_grams=quantity
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
                        amount_grams=quantity
                    )
                    db.session.add(ingredient)
                    db.session.commit()
                    flash(f'{food.description} added to recipe {target_recipe.name}.', 'success')
                else:
                    flash('My Food not found or not authorized.', 'danger')
            elif food_type == 'recipe':
                sub_recipe = db.session.get(Recipe, food_id)
                if sub_recipe and sub_recipe.user_id == current_user.id:
                    ingredient = RecipeIngredient(
                        recipe_id=target_recipe.id,
                        recipe_id_link=sub_recipe.id,
                        amount_grams=quantity
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
                            amount_grams=item.amount_grams * (quantity / 100)
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
                        amount_grams=quantity
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
                        amount_grams=quantity
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
                        amount_grams=quantity
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
                        amount_grams=quantity
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
                    calories_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1008).with_entities(FoodNutrient.amount).scalar(),
                    protein_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1003).with_entities(FoodNutrient.amount).scalar(),
                    carbs_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1005).with_entities(FoodNutrient.amount).scalar(),
                    fat_per_100g=FoodNutrient.query.filter_by(fdc_id=food_id, nutrient_id=1004).with_entities(FoodNutrient.amount).scalar()
                )
                db.session.add(my_food)
                db.session.commit()

                # Copy portions
                for portion in usda_food.portions:
                    my_portion = MyPortion(
                        my_food_id=my_food.id,
                        description=portion.portion_description,
                        gram_weight=portion.gram_weight
                    )
                    db.session.add(my_portion)
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
