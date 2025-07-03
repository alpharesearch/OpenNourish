from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Recipe, RecipeIngredient, DailyLog, Food, MyFood, MyMeal
from .forms import RecipeForm, IngredientForm, AddToLogForm
from sqlalchemy.orm import joinedload, selectinload
from datetime import date
from opennourish.utils import calculate_nutrition_for_items

recipes_bp = Blueprint('recipes', __name__, template_folder='templates')

@recipes_bp.route("/recipes")
@login_required
def recipes():
    user_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
    return render_template("recipes/recipes.html", recipes=user_recipes)

@recipes_bp.route("/recipe/new", methods=['GET', 'POST'])
@login_required
def new_recipe():
    form = RecipeForm()
    if form.validate_on_submit():
        new_recipe = Recipe(
            user_id=current_user.id,
            name=form.name.data,
            instructions=form.instructions.data
        )
        db.session.add(new_recipe)
        db.session.commit()
        flash('Recipe created successfully. Now add ingredients.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=new_recipe.id))
    return render_template('recipes/edit_recipe.html', form=form, recipe=None)

@recipes_bp.route("/recipe/edit/<int:recipe_id>", methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.options(joinedload(Recipe.ingredients).joinedload(RecipeIngredient.my_food)).get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to edit this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = RecipeForm(obj=recipe)
    ingredient_form = IngredientForm()

    if form.validate_on_submit():
        recipe.name = form.name.data
        recipe.instructions = form.instructions.data
        db.session.commit()
        flash('Recipe updated successfully.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    for ingredient in recipe.ingredients:
        if ingredient.fdc_id:
            ingredient.usda_food = db.session.get(Food, ingredient.fdc_id)

    # Search for ingredients
    query = request.args.get('q')
    search_results = []
    if query:
        usda_foods = Food.query.filter(Food.description.ilike(f'%{query}%')).limit(20).all()
        my_foods = MyFood.query.filter(MyFood.description.ilike(f'%{query}%'), MyFood.user_id == current_user.id).limit(20).all()
        my_meals = MyMeal.query.filter(MyMeal.name.ilike(f'%{query}%'), MyMeal.user_id == current_user.id).limit(20).all()
        
        for item in usda_foods:
            item.type = 'usda'
            search_results.append(item)
        for item in my_foods:
            item.type = 'my_food'
            search_results.append(item)
        for item in my_meals:
            item.type = 'my_meal'
            search_results.append(item)

    return render_template("recipes/edit_recipe.html", form=form, recipe=recipe, ingredient_form=ingredient_form, search_results=search_results, query=query)

@recipes_bp.route("/recipe/<int:recipe_id>/add_ingredient", methods=['POST'])
@login_required
def add_ingredient(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    food_id = request.form.get('food_id', type=int)
    food_type = request.form.get('food_type')
    amount = request.form.get('amount', type=float)
    meal_id = request.form.get('meal_id', type=int)

    if food_type == 'my_meal':
        meal = db.session.get(MyMeal, meal_id)
        if meal and meal.user_id == current_user.id:
            for item in meal.items:
                new_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    fdc_id=item.fdc_id,
                    my_food_id=item.my_food_id,
                    amount_grams=item.amount_grams
                )
                db.session.add(new_ingredient)
            db.session.commit()
            flash(f'All foods from meal "{meal.name}" added to recipe.', 'success')
        else:
            flash('Meal not found or you do not have permission to add it.', 'danger')
    elif food_id and food_type:
        if amount is None or amount <= 0:
            flash('Please enter a valid amount for the ingredient.', 'danger')
        else:
            # Check if ingredient already exists
            existing_ingredient = RecipeIngredient.query.filter_by(
                recipe_id=recipe_id,
                fdc_id=food_id if food_type == 'usda' else None,
                my_food_id=food_id if food_type == 'my_food' else None
            ).first()

            if existing_ingredient:
                existing_ingredient.amount_grams += amount
            else:
                new_ingredient = RecipeIngredient(
                    recipe_id=recipe.id,
                    fdc_id=food_id if food_type == 'usda' else None,
                    my_food_id=food_id if food_type == 'my_food' else None,
                    amount_grams=amount
                )
                db.session.add(new_ingredient)
            
            db.session.commit()
            flash('Ingredient added successfully.', 'success')
    else:
        flash('Invalid ingredient data.', 'danger')

    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/delete", methods=['POST'])
@login_required
def delete_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))
    
    db.session.delete(ingredient)
    db.session.commit()
    flash('Ingredient removed.', 'success')
    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))


@recipes_bp.route("/recipe/view/<int:recipe_id>")
@login_required
def view_recipe(recipe_id):
    recipe = Recipe.query.options(joinedload(Recipe.ingredients).joinedload(RecipeIngredient.my_food)).get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to view this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = RecipeForm(obj=recipe)
    ingredient_form = IngredientForm()

    if form.validate_on_submit():
        recipe.name = form.name.data
        recipe.instructions = form.instructions.data
        db.session.commit()
        flash('Recipe updated successfully.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    
    ingredient_details = []
    for ingredient in recipe.ingredients:
        description = ""
        if ingredient.food:
            description = ingredient.food.description
        elif ingredient.my_food:
            description = ingredient.my_food.description
            
        ingredient_details.append({
            'description': description,
            'amount_grams': ingredient.amount_grams
        })

    form = AddToLogForm()
    return render_template("recipes/view_recipe.html", recipe=recipe, ingredients=ingredient_details, totals=total_nutrition, form=form)

@recipes_bp.route("/recipe/add_to_log/<int:recipe_id>", methods=['POST'])
@login_required
def add_to_log(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to log this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = AddToLogForm()
    if form.validate_on_submit():
        total_grams = sum(ing.amount_grams for ing in recipe.ingredients)
        if total_grams == 0:
            flash('Cannot log a recipe with no ingredients.', 'danger')
            return redirect(url_for('recipes.view_recipe', recipe_id=recipe.id))
            
        servings_eaten = form.servings.data
        
        # For simplicity, we assume the recipe has 1 serving.
        # The user can specify how many servings they ate.
        # A more complex implementation could define servings in the recipe itself.
        amount_to_log = total_grams * servings_eaten

        new_log = DailyLog(
            user_id=current_user.id,
            log_date=date.today(),
            recipe_id=recipe.id,
            amount_grams=amount_to_log,
            meal_name='Snack' # Default meal name
        )
        db.session.add(new_log)
        db.session.commit()
        flash('Recipe added to your diary.', 'success')
        return redirect(url_for('diary.index')) # Assuming diary blueprint is named 'diary'

    flash('Invalid data for logging.', 'danger')
    return redirect(url_for('recipes.view_recipe', recipe_id=recipe.id))

@recipes_bp.route("/recipe/delete/<int:recipe_id>", methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to delete this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))
    
    db.session.delete(recipe)
    db.session.commit()
    flash('Recipe deleted.', 'success')
    return redirect(url_for('recipes.recipes'))