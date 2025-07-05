from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Recipe, RecipeIngredient, DailyLog, Food, MyFood, MyMeal, Portion, MyPortion, RecipePortion
from .forms import RecipeForm, IngredientForm, AddToLogForm, RecipePortionForm
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
            instructions=form.instructions.data,
            servings=form.servings.data
        )
        db.session.add(new_recipe)
        db.session.commit()
        flash('Recipe created successfully. Now add ingredients.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=new_recipe.id))
    return render_template('recipes/edit_recipe.html', form=form, recipe=None, portion_form=RecipePortionForm())

@recipes_bp.route("/recipe/edit/<int:recipe_id>", methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.options(
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.my_food).selectinload(MyFood.portions),
        selectinload(Recipe.portions)
    ).get_or_404(recipe_id)

    # Manually fetch USDA food data
    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    if usda_food_ids:
        usda_foods = Food.query.options(selectinload(Food.portions).selectinload(Portion.measure_unit)).filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}
        

    if recipe.user_id != current_user.id:
        flash('You are not authorized to edit this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = RecipeForm(obj=recipe)
    portion_form = RecipePortionForm()

    if form.validate_on_submit():
        recipe.name = form.name.data
        recipe.instructions = form.instructions.data
        recipe.servings = form.servings.data
        db.session.commit()
        flash('Recipe updated successfully.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

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

    return render_template(
        "recipes/edit_recipe.html",
        form=form,
        recipe=recipe,
        portion_form=portion_form,
        
        url_action='recipes.add_ingredient',
        url_params={'recipe_id': recipe.id}
    )


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

@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/update", methods=['POST'])
@login_required
def update_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    quantity = request.form.get('quantity', type=float)
    portion_id = request.form.get('portion_id', type=int)

    if quantity is None or quantity <= 0:
        flash('Quantity must be a positive number.', 'danger')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    gram_weight = 0
    if portion_id:
        if ingredient.fdc_id:
            portion = Portion.query.filter_by(id=portion_id, fdc_id=ingredient.fdc_id).first()
        elif ingredient.my_food_id:
            portion = MyPortion.query.filter_by(id=portion_id, my_food_id=ingredient.my_food_id).first()
        
        if portion:
            gram_weight = portion.gram_weight
        else:
            flash('Selected portion not found.', 'danger')
            return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))
    else:
        # If no portion selected, assume quantity is in grams
        gram_weight = 1 # 1 unit = 1 gram

    ingredient.amount_grams = quantity * gram_weight
    db.session.commit()
    flash('Ingredient updated successfully.', 'success')
    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))


@recipes_bp.route("/recipe/view/<int:recipe_id>")
@login_required
def view_recipe(recipe_id):
    recipe = Recipe.query.options(
        selectinload(Recipe.ingredients).joinedload(RecipeIngredient.my_food)
    ).filter_by(id=recipe_id, user_id=current_user.id).first_or_404()
    usda_food_ids = {ing.fdc_id for ing in recipe.ingredients if ing.fdc_id}

    # If there are any USDA foods, run ONE query against the 'usda' bind to get them all.
    if usda_food_ids:
        # This query correctly targets the 'usda' database via the Food model's bind key.
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        # Create a dictionary for fast lookups: {fdc_id: FoodObject}
        usda_foods_map = {food.fdc_id: food for food in usda_foods}
    else:
        usda_foods_map = {}

    # Step 3: Attach the pre-loaded data to each ingredient in Python.
    # This avoids any further database queries inside the loop.
    for ingredient in recipe.ingredients:
        if ingredient.fdc_id:
            ingredient.usda_food = usda_foods_map.get(ingredient.fdc_id)

    # The rest of the logic can now proceed as before.
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)

    ingredient_details = []
    for ingredient in recipe.ingredients:
        description = "Unknown Food"
        if hasattr(ingredient, 'usda_food') and ingredient.usda_food:
            description = ingredient.usda_food.description
        elif ingredient.my_food:
            description = ingredient.my_food.description

        ingredient_details.append({
            'description': description,
            'amount_grams': ingredient.amount_grams
        })

    form = AddToLogForm()
    return render_template(
        "recipes/view_recipe.html",
        recipe=recipe,
        ingredients=ingredient_details,
        totals=total_nutrition,
        form=form
    )


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


@recipes_bp.route("/recipe/portion/add/<int:recipe_id>", methods=['POST'])
@login_required
def add_recipe_portion(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    form = RecipePortionForm()
    if form.validate_on_submit():
        total_grams = sum(ing.amount_grams for ing in recipe.ingredients)
        if recipe.servings > 0 and total_grams > 0:
            gram_weight = total_grams / recipe.servings
            new_portion = RecipePortion(
                recipe_id=recipe.id,
                description=form.description.data,
                gram_weight=gram_weight
            )
            db.session.add(new_portion)
            db.session.commit()
            flash('Recipe portion added.', 'success')
        else:
            flash('Cannot create a portion for a recipe with 0 servings or no ingredients.', 'warning')
    else:
        flash('Invalid form submission.', 'danger')
    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))


@recipes_bp.route("/recipe/portion/delete/<int:portion_id>", methods=['POST'])
@login_required
def delete_recipe_portion(portion_id):
    portion = RecipePortion.query.get_or_404(portion_id)
    recipe = portion.recipe
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))
    
    db.session.delete(portion)
    db.session.commit()
    flash('Recipe portion deleted.', 'success')
    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))
