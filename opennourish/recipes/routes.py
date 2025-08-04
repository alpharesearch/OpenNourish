from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required, current_user
from models import (
    db,
    Recipe,
    RecipeIngredient,
    Food,
    MyFood,
    MyMeal,
    UnifiedPortion,
    FoodCategory,
    User,
)
from opennourish.recipes.forms import RecipeForm
from opennourish.diary.forms import AddToLogForm
from opennourish.my_foods.forms import PortionForm
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from opennourish.utils import (
    calculate_nutrition_for_items,
    calculate_recipe_nutrition_per_100g,
    ensure_portion_sequence,
    get_available_portions,
    remove_leading_one,
    update_recipe_nutrition,
    generate_recipe_label_pdf,
)

recipes_bp = Blueprint("recipes", __name__, template_folder="templates")


@recipes_bp.route("/")
@login_required
def recipes():
    page = request.args.get("page", 1, type=int)
    view_mode = request.args.get("view", "user")  # 'user', 'friends', or 'public'
    per_page = 8

    query = Recipe.query.options(joinedload(Recipe.user))
    if view_mode == "friends":
        friend_ids = [friend.id for friend in current_user.friends]
        if not friend_ids:
            query = query.filter(db.false())  # No friends, so no results
        else:
            query = query.filter(Recipe.user_id.in_(friend_ids))
    elif view_mode == "public":
        query = query.filter(Recipe.is_public)
    else:  # Default to user's recipes
        query = query.filter_by(user_id=current_user.id)

    recipes_pagination = query.order_by(Recipe.name).paginate(
        page=page, per_page=per_page, error_out=False
    )

    for recipe in recipes_pagination.items:
        recipe.nutrition_per_100g = calculate_recipe_nutrition_per_100g(recipe)
        recipe.total_grams = sum(ing.amount_grams for ing in recipe.ingredients)

    return render_template(
        "recipes/recipes.html", recipes=recipes_pagination, view_mode=view_mode
    )


@recipes_bp.route("/recipe/new", methods=["GET", "POST"])
@login_required
def new_recipe():
    form = RecipeForm()
    form.food_category.choices = [("", "-- Select a Category --")] + [
        (c.id, c.description) for c in FoodCategory.query.order_by(FoodCategory.code)
    ]
    if form.validate_on_submit():
        new_recipe = Recipe(
            user_id=current_user.id,
            name=form.name.data,
            instructions=form.instructions.data,
            servings=form.servings.data,
            is_public=form.is_public.data,
            food_category_id=form.food_category.data
            if form.food_category.data
            else None,
        )
        if (
            current_app.config.get("ENABLE_EMAIL_VERIFICATION", False)
            and not current_user.is_verified
            and new_recipe.is_public
        ):
            new_recipe.is_public = False
            flash("Your email must be verified to make recipes public.", "warning")

        db.session.add(new_recipe)
        db.session.flush()  # Flush to get the new_recipe.id

        # Create the default 1-gram portion
        gram_portion = UnifiedPortion(
            recipe_id=new_recipe.id,
            amount=1.0,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0,
        )
        db.session.add(gram_portion)

        db.session.commit()
        flash("Recipe created successfully. Now add ingredients.", "success")
        return redirect(url_for("recipes.edit_recipe", recipe_id=new_recipe.id))
    return render_template(
        "recipes/edit_recipe.html", form=form, recipe=None, portion_form=PortionForm()
    )


@recipes_bp.route("/<int:recipe_id>/edit", methods=["GET", "POST"])
@login_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.options(
        selectinload(Recipe.ingredients)
        .selectinload(RecipeIngredient.my_food)
        .selectinload(MyFood.portions),
        selectinload(Recipe.ingredients).selectinload(
            RecipeIngredient.linked_recipe
        ),  # Load linked recipes
        selectinload(Recipe.portions),
    ).get_or_404(recipe_id)

    # Ensure all portions have a seq_num
    if any(p.seq_num is None for p in recipe.portions):
        portions_to_update = sorted(recipe.portions, key=lambda p: p.gram_weight)
        for i, p in enumerate(portions_to_update):
            p.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all portions.", "info")

    # Manually fetch USDA food data
    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}

    for ing in recipe.ingredients:
        if ing.fdc_id:
            ing.usda_food = usda_foods_map.get(ing.fdc_id)

        # Calculate nutrition for each individual ingredient
        ingredient_nutrition = calculate_nutrition_for_items([ing])
        ing.calories = ingredient_nutrition["calories"]
        ing.protein = ingredient_nutrition["protein"]
        ing.carbs = ingredient_nutrition["carbs"]
        ing.fat = ingredient_nutrition["fat"]

        # Calculate quantity and portion description
        food_object = None
        if hasattr(ing, "usda_food") and ing.usda_food:
            food_object = ing.usda_food
        elif ing.my_food:
            food_object = ing.my_food
        elif ing.linked_recipe:
            food_object = ing.linked_recipe

        ing.quantity = ing.amount_grams
        ing.portion_description = "g"

        if food_object:
            available_portions = get_available_portions(food_object)
            available_portions.sort(key=lambda p: p.gram_weight, reverse=True)

            for p in available_portions:
                if p.gram_weight > 0.1:
                    if (
                        abs(ing.amount_grams % p.gram_weight) < 0.01
                        or abs(p.gram_weight - (ing.amount_grams % p.gram_weight))
                        < 0.01
                    ):
                        ing.quantity = round(ing.amount_grams / p.gram_weight, 2)
                        ing.portion_description = p.full_description_str
                        break

    if recipe.user_id != current_user.id:
        flash("You are not authorized to edit this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))

    # Ensure all portions have a seq_num
    if any(p.seq_num is None for p in recipe.portions):
        portions_to_update = sorted(recipe.portions, key=lambda p: p.gram_weight)
        for i, p in enumerate(portions_to_update):
            p.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all portions. Please try again.", "info")

    form = RecipeForm(obj=recipe)
    form.food_category.choices = [("", "-- Select a Category --")] + [
        (c.id, c.description) for c in FoodCategory.query.order_by(FoodCategory.code)
    ]

    if request.method == "GET" and recipe.food_category_id:
        form.food_category.data = recipe.food_category_id

    servings_param = request.args.get("servings_param", type=float)
    name_param = request.args.get("name_param", type=str)
    instructions_param = request.args.get("instructions_param", type=str)

    if servings_param is not None:
        form.servings.data = servings_param
    if name_param is not None:
        form.name.data = name_param
    if instructions_param is not None:
        form.instructions.data = instructions_param

    portion_form = PortionForm()

    if form.validate_on_submit():
        # Manually handle populating the object to avoid the relationship error
        recipe.name = form.name.data
        recipe.instructions = form.instructions.data
        recipe.servings = form.servings.data
        recipe.upc = form.upc.data

        # Handle is_public based on email verification status
        if (
            current_app.config.get("ENABLE_EMAIL_VERIFICATION", False)
            and not current_user.is_verified
            and form.is_public.data
        ):
            recipe.is_public = False
            flash("Your email must be verified to make recipes public.", "warning")
        else:
            recipe.is_public = form.is_public.data

        # Fetch the FoodCategory object based on the form's ID
        food_category_id = form.food_category.data
        if food_category_id:
            recipe.food_category = db.session.get(FoodCategory, food_category_id)
        else:
            recipe.food_category = None

        update_recipe_nutrition(recipe)
        db.session.commit()
        flash("Recipe updated successfully.", "success")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    # If it's a POST request but not a form submission (e.g., auto_add_portion),
    # or if form validation fails, ensure form fields are populated from request.form
    # to retain user input.
    if request.method == "POST":
        form = RecipeForm(request.form, obj=recipe)
        if servings_param is not None:
            form.servings.data = servings_param
        if name_param is not None:
            form.name.data = name_param
        if instructions_param is not None:
            form.instructions.data = instructions_param

    query = request.args.get("q")
    search_results = []
    if query:
        usda_foods = (
            Food.query.filter(Food.description.ilike(f"%{query}%")).limit(20).all()
        )
        my_foods = (
            MyFood.query.filter(
                MyFood.description.ilike(f"%{query}%"),
                MyFood.user_id == current_user.id,
            )
            .limit(20)
            .all()
        )
        my_meals = (
            MyMeal.query.filter(
                MyMeal.name.ilike(f"%{query}%"), MyMeal.user_id == current_user.id
            )
            .limit(20)
            .all()
        )

        for item in usda_foods:
            item.type = "usda"
            search_results.append(item)
        for item in my_foods:
            item.type = "my_food"
            search_results.append(item)
        for item in my_meals:
            item.type = "my_meal"
            search_results.append(item)

    return render_template(
        "recipes/edit_recipe.html",
        form=form,
        recipe=recipe,
        portion_form=portion_form,
        get_available_portions=get_available_portions,
        search_term=query,
    )


@recipes_bp.route("/ingredients/<int:ingredient_id>/delete", methods=["POST"])
@login_required
def delete_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))

    db.session.delete(ingredient)
    update_recipe_nutrition(recipe)
    db.session.commit()
    flash("Ingredient removed.", "success")
    return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id) + "#ingredients-section")


@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/update", methods=["POST"])
@login_required
def update_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))

    amount = request.form.get("amount", type=float)
    portion_id = request.form.get("portion_id", type=int)

    if amount is None or amount <= 0:
        flash("Amount must be a positive number.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    if portion_id is None:
        flash("Portion is required.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    portion_obj = db.session.get(UnifiedPortion, portion_id)
    if not portion_obj:
        flash("Selected portion not found.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    ingredient.amount_grams = amount * portion_obj.gram_weight
    ingredient.serving_type = portion_obj.full_description_str
    ingredient.portion_id_fk = portion_obj.id
    update_recipe_nutrition(recipe)
    db.session.commit()
    flash("Ingredient updated successfully.", "success")
    return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id) + "#ingredients-section")


@recipes_bp.route("/<int:recipe_id>")
@login_required
def view_recipe(recipe_id):
    recipe = Recipe.query.options(
        selectinload(Recipe.ingredients)
        .joinedload(RecipeIngredient.my_food)
        .selectinload(MyFood.portions),
        selectinload(Recipe.ingredients).joinedload(RecipeIngredient.linked_recipe),
        joinedload(Recipe.user),  # Eager load the user
    ).get_or_404(recipe_id)

    # Authorization check
    user = db.session.get(User, current_user.id)
    is_friend = recipe.user and recipe.user in user.friends
    if not recipe.is_public and recipe.user_id != user.id and not is_friend:
        flash("You are not authorized to view this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))

    # Ensure portions have sequence numbers before passing to the template
    ensure_portion_sequence([recipe])

    usda_food_ids = {ing.fdc_id for ing in recipe.ingredients if ing.fdc_id}
    usda_foods_map = {}
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}

    for ingredient in recipe.ingredients:
        if ingredient.fdc_id:
            ingredient.usda_food = usda_foods_map.get(ingredient.fdc_id)

    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)

    ingredient_details = []
    for ingredient in recipe.ingredients:
        description = "Unknown Food"
        food_object = None
        if hasattr(ingredient, "usda_food") and ingredient.usda_food:
            description = ingredient.usda_food.description
            food_object = ingredient.usda_food
        elif ingredient.my_food:
            description = ingredient.my_food.description
            food_object = ingredient.my_food
        elif ingredient.linked_recipe:
            description = ingredient.linked_recipe.name
            food_object = ingredient.linked_recipe

        quantity = ingredient.amount_grams
        portion_description = "g"

        if food_object:
            available_portions = get_available_portions(food_object)
            available_portions.sort(key=lambda p: p.gram_weight, reverse=True)

            for p in available_portions:
                if p.gram_weight > 0.1:
                    if (
                        abs(ingredient.amount_grams % p.gram_weight) < 0.01
                        or abs(
                            p.gram_weight - (ingredient.amount_grams % p.gram_weight)
                        )
                        < 0.01
                    ):
                        quantity = round(ingredient.amount_grams / p.gram_weight, 2)
                        portion_description = remove_leading_one(p.full_description_str)
                        break

        ingredient_details.append(
            {
                "description": description,
                "quantity": quantity,
                "portion_description": portion_description,
                "amount_grams": ingredient.amount_grams,
            }
        )

    form = AddToLogForm()
    return render_template(
        "recipes/view_recipe.html",
        recipe=recipe,
        ingredients=ingredient_details,
        totals=total_nutrition,
        form=form,
    )


@recipes_bp.route("/<int:recipe_id>/delete", methods=["POST"])
@login_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash("You are not authorized to delete this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))

    recipe.user_id = None
    db.session.commit()
    flash("Recipe deleted.", "success")
    return redirect(url_for("recipes.recipes"))


@recipes_bp.route("/recipe/portion/auto_add/<int:recipe_id>", methods=["POST"])
@login_required
def auto_add_recipe_portion(recipe_id):
    recipe = Recipe.query.options(selectinload(Recipe.ingredients)).get_or_404(
        recipe_id
    )
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    servings_from_form = request.form.get("servings", type=float)
    if servings_from_form is None or servings_from_form <= 0:
        flash("Invalid servings value provided.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

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
        gram_weight=gram_weight_per_serving,
    )
    db.session.add(new_portion)
    db.session.commit()
    name_from_form = request.form.get("name", type=str)
    instructions_from_form = request.form.get("instructions", type=str)

    # ... (existing code)

    return redirect(
        url_for(
            "recipes.edit_recipe",
            recipe_id=recipe.id,
            servings_param=servings_from_form,
            name_param=name_from_form,
            instructions_param=instructions_from_form,
        )
    )


@recipes_bp.route("/recipe/portion/add/<int:recipe_id>", methods=["POST"])
@login_required
def add_recipe_portion(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))

    form = PortionForm()
    if form.validate_on_submit():
        # Calculate the next seq_num
        max_seq_num = (
            db.session.query(func.max(UnifiedPortion.seq_num))
            .filter(UnifiedPortion.recipe_id == recipe_id)
            .scalar()
        )
        next_seq_num = (max_seq_num or 0) + 1
        new_portion = UnifiedPortion(
            recipe_id=recipe.id,
            my_food_id=None,
            fdc_id=None,
            portion_description=form.portion_description.data,
            amount=form.amount.data,
            measure_unit_description=form.measure_unit_description.data,
            modifier=form.modifier.data,
            gram_weight=form.gram_weight.data,
            seq_num=next_seq_num,
        )
        db.session.add(new_portion)
        db.session.commit()
        flash("Recipe portion added.", "success")
    else:
        # Collect and flash form errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", "danger")

    return redirect(url_for("recipes.edit_recipe", recipe_id=recipe.id))


@recipes_bp.route("/recipe/portion/update/<int:portion_id>", methods=["POST"])
@login_required
def update_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or portion.recipe.user_id != current_user.id:
        flash("Portion not found or you do not have permission to edit it.", "danger")
        return redirect(url_for("recipes.recipes"))

    form = PortionForm(request.form, obj=portion)
    if form.validate_on_submit():
        form.populate_obj(portion)
        db.session.commit()
        flash("Portion updated successfully!", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", "danger")
    return redirect(
        url_for("recipes.edit_recipe", recipe_id=portion.recipe_id) + "#portions-table"
    )


@recipes_bp.route("/recipe/portion/delete/<int:portion_id>", methods=["POST"])
@login_required
def delete_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if portion and portion.recipe and portion.recipe.user_id == current_user.id:
        recipe_id = portion.recipe_id
        db.session.delete(portion)
        db.session.commit()
        flash("Recipe portion deleted.", "success")
        return redirect(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    else:
        flash("Portion not found or you do not have permission to delete it.", "danger")
        return redirect(url_for("recipes.recipes"))


@recipes_bp.route("/<int:recipe_id>/generate_label_pdf")
@login_required
def generate_label_pdf(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if not recipe.is_public and recipe.user_id != current_user.id:
        flash("You are not authorized to view this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))
    return generate_recipe_label_pdf(recipe_id, label_only=True)


@recipes_bp.route("/<int:recipe_id>/generate_pdf_details")
@login_required
def generate_pdf_details(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if not recipe.is_public and recipe.user_id != current_user.id:
        flash("You are not authorized to view this recipe.", "danger")
        return redirect(url_for("recipes.recipes"))
    return generate_recipe_label_pdf(recipe_id, label_only=False)


@recipes_bp.route("/<int:recipe_id>/copy", methods=["POST"])
@login_required
def copy_recipe(recipe_id):
    original_recipe = Recipe.query.options(
        selectinload(Recipe.ingredients), selectinload(Recipe.portions)
    ).get_or_404(recipe_id)

    # Verify user is friends with the owner
    friend_ids = [friend.id for friend in current_user.friends]
    if original_recipe.user_id not in friend_ids:
        # Allow copying public recipes even if not friends
        if not original_recipe.is_public:
            flash(
                "You can only copy recipes from your friends or public recipes.",
                "danger",
            )
            return redirect(request.referrer or url_for("recipes.recipes"))

    # Create a new recipe for the current user
    new_recipe = Recipe(
        user_id=current_user.id,
        name=original_recipe.name,
        instructions=original_recipe.instructions,
        servings=original_recipe.servings,
        is_public=False,  # Copied recipes are private by default
    )
    db.session.add(new_recipe)
    db.session.flush()  # Flush to get the new_recipe.id for ingredients

    # Copy ingredients
    for orig_ing in original_recipe.ingredients:
        new_ing = RecipeIngredient(
            recipe_id=new_recipe.id,
            fdc_id=orig_ing.fdc_id,
            my_food_id=orig_ing.my_food_id,
            recipe_id_link=orig_ing.recipe_id_link,
            amount_grams=orig_ing.amount_grams,
        )
        db.session.add(new_ing)

    # Copy portions
    for orig_portion in original_recipe.portions:
        new_portion = UnifiedPortion(
            recipe_id=new_recipe.id,
            amount=orig_portion.amount,
            measure_unit_description=orig_portion.measure_unit_description,
            portion_description=orig_portion.portion_description,
            modifier=orig_portion.modifier,
            gram_weight=orig_portion.gram_weight,
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(f"Successfully copied '{original_recipe.name}' to your recipes.", "success")
    return redirect(url_for("recipes.edit_recipe", recipe_id=new_recipe.id))


@recipes_bp.route("/portion/<int:portion_id>/move_up", methods=["POST"])
@login_required
def move_recipe_portion_up(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.recipe.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for("recipes.recipes"))

    if portion_to_move.seq_num is None:
        # Assign sequence numbers to all portions of this food if any are missing
        portions = (
            UnifiedPortion.query.filter_by(recipe_id=portion_to_move.recipe_id)
            .order_by(UnifiedPortion.gram_weight)
            .all()
        )
        for i, p in enumerate(portions):
            p.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all portions. Please try again.", "info")
        return redirect(
            url_for("recipes.edit_recipe", recipe_id=portion_to_move.recipe_id)
        )

    # Find the portion with the next lower seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.recipe_id == portion_to_move.recipe_id,
            UnifiedPortion.seq_num < portion_to_move.seq_num,
        )
        .order_by(UnifiedPortion.seq_num.desc())
        .first()
    )

    if portion_to_swap_with:
        # Swap seq_num values
        portion_to_move.seq_num, portion_to_swap_with.seq_num = (
            portion_to_swap_with.seq_num,
            portion_to_move.seq_num,
        )
        db.session.commit()
        flash("Portion moved up.", "success")
    else:
        flash("Portion is already at the top.", "info")

    return redirect(
        url_for("recipes.edit_recipe", recipe_id=portion_to_move.recipe_id)
        + "#portions-table"
    )


@recipes_bp.route("/portion/<int:portion_id>/move_down", methods=["POST"])
@login_required
def move_recipe_portion_down(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.recipe.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for("recipes.recipes"))

    # Find the portion with the next higher seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.recipe_id == portion_to_move.recipe_id,
            UnifiedPortion.seq_num > portion_to_move.seq_num,
        )
        .order_by(UnifiedPortion.seq_num.asc())
        .first()
    )

    if portion_to_swap_with:
        # Swap seq_num values
        portion_to_move.seq_num, portion_to_swap_with.seq_num = (
            portion_to_swap_with.seq_num,
            portion_to_move.seq_num,
        )
        db.session.commit()
        flash("Portion moved down.", "success")
    else:
        flash("Portion is already at the bottom.", "info")

    return redirect(
        url_for("recipes.edit_recipe", recipe_id=portion_to_move.recipe_id)
        + "#portions-table"
    )
