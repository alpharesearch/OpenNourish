from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Recipe, RecipeIngredient, DailyLog, Food, MyFood, MyMeal, UnifiedPortion
from opennourish.recipes.forms import RecipeForm
from opennourish.diary.forms import AddToLogForm
from opennourish.recipes.forms import RecipeForm
from opennourish.recipes.forms import RecipeForm
from opennourish.recipes.forms import RecipeForm
from opennourish.my_foods.forms import PortionForm
from sqlalchemy.orm import joinedload, selectinload
from datetime import date
from opennourish.utils import calculate_nutrition_for_items, calculate_recipe_nutrition_per_100g, get_available_portions

recipes_bp = Blueprint('recipes', __name__, template_folder='templates')

@recipes_bp.route("/recipes")
@login_required
def recipes():
    page = request.args.get('page', 1, type=int)
    per_page = 8  # Or get from config
    recipes_pagination = Recipe.query.filter_by(user_id=current_user.id).paginate(page=page, per_page=per_page, error_out=False)
    for recipe in recipes_pagination.items:
        recipe.nutrition_per_100g = calculate_recipe_nutrition_per_100g(recipe)
    return render_template("recipes/recipes.html", recipes=recipes_pagination)

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
    return render_template('recipes/edit_recipe.html', form=form, recipe=None, portion_form=PortionForm())

@recipes_bp.route('/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.options(
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.my_food).selectinload(MyFood.portions),
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.linked_recipe), # Load linked recipes
        selectinload(Recipe.portions)
    ).get_or_404(recipe_id)

    # Manually fetch USDA food data
    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}
        
    for ing in recipe.ingredients:
        if ing.fdc_id:
            ing.usda_food = usda_foods_map.get(ing.fdc_id)
        
        # Calculate nutrition for each individual ingredient
        # calculate_nutrition_for_items expects a list of items, so wrap the single ingredient
        ingredient_nutrition = calculate_nutrition_for_items([ing])
        ing.calories = ingredient_nutrition['calories']
        ing.protein = ingredient_nutrition['protein']
        ing.carbs = ingredient_nutrition['carbs']
        ing.fat = ingredient_nutrition['fat']

    if recipe.user_id != current_user.id:
        flash('You are not authorized to edit this recipe.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = RecipeForm(obj=recipe)
    servings_param = request.args.get('servings_param', type=float)
    name_param = request.args.get('name_param', type=str)
    instructions_param = request.args.get('instructions_param', type=str)

    if servings_param is not None:
        form.servings.data = servings_param
    if name_param is not None:
        form.name.data = name_param
    if instructions_param is not None:
        form.instructions.data = instructions_param

    portion_form = PortionForm()

    if form.validate_on_submit():
        form.populate_obj(recipe)
        db.session.commit()
        flash('Recipe updated successfully.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    # If it's a POST request but not a form submission (e.g., auto_add_portion), 
    # or if form validation fails, ensure form fields are populated from request.form
    # to retain user input.
    if request.method == 'POST':
        form = RecipeForm(request.form, obj=recipe)
        if servings_param is not None:
            form.servings.data = servings_param
        if name_param is not None:
            form.name.data = name_param
        if instructions_param is not None:
            form.instructions.data = instructions_param

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
        get_available_portions=get_available_portions,
        search_term=query
    )


@recipes_bp.route('/ingredients/<int:ingredient_id>/delete', methods=['POST'])
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
            portion = UnifiedPortion.query.filter_by(id=portion_id, fdc_id=ingredient.fdc_id).first()
        elif ingredient.my_food_id:
            portion = UnifiedPortion.query.filter_by(id=portion_id, my_food_id=ingredient.my_food_id).first()
        
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


@recipes_bp.route('/<int:recipe_id>')
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


@recipes_bp.route('/<int:recipe_id>/delete', methods=['POST'])
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


@recipes_bp.route("/recipe/portion/auto_add/<int:recipe_id>", methods=['POST'])
@login_required
def auto_add_recipe_portion(recipe_id):
    recipe = Recipe.query.options(selectinload(Recipe.ingredients)).get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    servings_from_form = request.form.get('servings', type=float)
    if servings_from_form is None or servings_from_form <= 0:
        flash('Invalid servings value provided.', 'danger')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    total_gram_weight = sum(ing.amount_grams for ing in recipe.ingredients)
    gram_weight_per_serving = total_gram_weight / servings_from_form

    new_portion = UnifiedPortion(
        recipe_id=recipe.id,
        my_food_id=None,
        fdc_id=None,
        amount=1.0,
        measure_unit_description="serving",
        portion_description=None,
        modifier=None,
        gram_weight=gram_weight_per_serving
    )
    db.session.add(new_portion)
    db.session.commit()
    name_from_form = request.form.get('name', type=str)
    instructions_from_form = request.form.get('instructions', type=str)

    # ... (existing code)

    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id, servings_param=servings_from_form, name_param=name_from_form, instructions_param=instructions_from_form))


@recipes_bp.route("/recipe/portion/add/<int:recipe_id>", methods=['POST'])
@login_required
def add_recipe_portion(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash('You are not authorized to modify this recipe.', 'danger')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))

    form = PortionForm()
    if form.validate_on_submit():
        new_portion = UnifiedPortion(
            recipe_id=recipe.id,
            my_food_id=None,
            fdc_id=None,
            portion_description=form.portion_description.data,
            amount=form.amount.data,
            measure_unit_description=form.measure_unit_description.data,
            modifier=form.modifier.data,
            gram_weight=form.gram_weight.data
        )
        db.session.add(new_portion)
        db.session.commit()
        flash('Recipe portion added.', 'success')
    else:
        # Collect and flash form errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return redirect(url_for('recipes.edit_recipe', recipe_id=recipe.id))


@recipes_bp.route("/recipe/portion/update/<int:portion_id>", methods=['POST'])
@login_required
def update_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or portion.recipe.user_id != current_user.id:
        flash('Portion not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('recipes.recipes'))

    form = PortionForm(request.form, obj=portion)
    if form.validate_on_submit():
        form.populate_obj(portion)
        db.session.commit()
        flash('Portion updated successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')
    return redirect(url_for('recipes.edit_recipe', recipe_id=portion.recipe_id))


@recipes_bp.route("/recipe/portion/delete/<int:portion_id>", methods=['POST'])
@login_required
def delete_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if portion and portion.recipe and portion.recipe.user_id == current_user.id:
        recipe_id = portion.recipe_id
        db.session.delete(portion)
        db.session.commit()
        flash('Recipe portion deleted.', 'success')
        return redirect(url_for('recipes.edit_recipe', recipe_id=recipe_id))
    else:
        flash('Portion not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('recipes.recipes'))
