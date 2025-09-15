from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    Response,
)
from datetime import datetime, timezone
import yaml
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
from sqlalchemy.orm import joinedload, selectinload, subqueryload
from opennourish.utils import (
    calculate_nutrition_for_items,
    calculate_recipe_nutrition_per_100g,
    ensure_portion_sequence,
    get_available_portions,
    update_recipe_nutrition,
    prepare_undo_and_delete,
)
from opennourish.typst_utils import (
    generate_recipe_label_pdf,
    generate_recipe_label_svg,
)

recipes_bp = Blueprint("recipes", __name__, template_folder="templates")


INGREDIENTS_SECTION_FRAGMENT = "#ingredients-section"
RECIPES_LIST_ROUTE = "recipes.recipes"
EDIT_RECIPE_ROUTE = "recipes.edit_recipe"
PORTION_TABLE_FRAGMENT = "#portions-table"
IMPORT_RECIPES_ROUTE = "recipes.import_recipes"


def _get_or_create_food_category(category_name, user_id, food_description):
    if not category_name or category_name.lower() == food_description.lower():
        return None
    category_name = category_name.strip()
    # Try to find user-specific category first
    category = FoodCategory.query.filter(
        func.lower(FoodCategory.description) == func.lower(category_name),
        FoodCategory.user_id == user_id,
    ).first()
    if category:
        return category
    # Try to find global category
    category = FoodCategory.query.filter(
        func.lower(FoodCategory.description) == func.lower(category_name),
        FoodCategory.user_id.is_(None),
    ).first()
    if category:
        return category
    # Create new user-specific category
    new_category = FoodCategory(description=category_name, user_id=user_id)
    db.session.add(new_category)
    db.session.flush()
    return new_category


def _process_recipe_yaml_import(yaml_stream):
    try:
        data = yaml.safe_load(yaml_stream)
        if not data:
            flash("No data found in the YAML content.", "info")
            return redirect(url_for(IMPORT_RECIPES_ROUTE))

        # Mode detection
        is_simple_import = "ingredients" in data and isinstance(
            data["ingredients"], list
        )
        is_complex_import = "dependent_my_foods" in data or "recipes" in data

        if is_simple_import and not is_complex_import:
            # --- Simple Import Workflow ---
            name = data.get("name")
            if not name:
                flash("Simple import requires a 'name' for the recipe.", "danger")
                return redirect(url_for(IMPORT_RECIPES_ROUTE))

            new_recipe = Recipe(
                user_id=current_user.id,
                name=name,
                servings=data.get("servings", 1),
                instructions=data.get("instructions", ""),
                is_public=False,
            )
            db.session.add(new_recipe)
            db.session.flush()

            for ingredient_text in data["ingredients"]:
                placeholder_food = MyFood(
                    user_id=current_user.id,
                    description=ingredient_text,
                    is_placeholder=True,
                )
                db.session.add(placeholder_food)
                db.session.flush()

                ingredient = RecipeIngredient(
                    recipe_id=new_recipe.id,
                    my_food_id=placeholder_food.id,
                    amount_grams=100,  # Default amount
                )
                db.session.add(ingredient)

            db.session.commit()
            flash(
                "Recipe imported! Please match the ingredients to real foods.",
                "success",
            )
            return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=new_recipe.id))

        elif is_complex_import:
            # --- Complex Import Workflow ---
            dependent_foods = data.get("dependent_my_foods", [])
            recipes_to_import = data.get("recipes", [])

            if not isinstance(dependent_foods, list) or not isinstance(
                recipes_to_import, list
            ):
                flash(
                    "Complex import must contain 'dependent_my_foods' and 'recipes' as lists.",
                    "danger",
                )
                return redirect(url_for(IMPORT_RECIPES_ROUTE))

            # ... (rest of the complex import logic remains the same)
            # --- Pass 1: Process Dependent MyFoods ---
            existing_food_descriptions = {
                f.description.lower()
                for f in MyFood.query.filter_by(user_id=current_user.id).all()
            }
            my_foods_map = {f.lower(): f for f in existing_food_descriptions}
            new_foods_count = 0

            for food_item in dependent_foods:
                description = food_item.get("description")
                if not description or description.lower() in existing_food_descriptions:
                    continue  # Skip if no description or already exists

                # Create new MyFood
                category = _get_or_create_food_category(
                    food_item.get("category"), current_user.id, description
                )
                nutrition_facts = food_item.get("nutrition_facts", {})
                first_portion = (
                    food_item["portions"][0] if "portions" in food_item else {}
                )
                gram_weight = first_portion.get("gram_weight", 0)
                factor = 100.0 / gram_weight if gram_weight > 0 else 0

                new_food = MyFood(
                    user_id=current_user.id,
                    description=description,
                    food_category=category,
                    ingredients=food_item.get("ingredients"),
                    upc=food_item.get("upc"),
                    calories_per_100g=nutrition_facts.get("calories", 0) * factor,
                    protein_per_100g=nutrition_facts.get("protein_grams", 0) * factor,
                    carbs_per_100g=nutrition_facts.get("carbohydrates_grams", 0)
                    * factor,
                    fat_per_100g=nutrition_facts.get("fat_grams", 0) * factor,
                )
                db.session.add(new_food)
                db.session.flush()

                for p_data in food_item.get("portions", []):
                    portion = UnifiedPortion(
                        my_food_id=new_food.id,
                        amount=p_data.get("amount", 1),
                        measure_unit_description=p_data.get("measure_unit_description"),
                        gram_weight=p_data.get("gram_weight"),
                    )
                    db.session.add(portion)

                existing_food_descriptions.add(description.lower())
                my_foods_map[description.lower()] = new_food
                new_foods_count += 1

            # --- Pass 2: Process Recipes ---
            existing_recipe_names = {
                r.name.lower()
                for r in Recipe.query.filter_by(user_id=current_user.id).all()
            }
            recipes_map = {}
            new_recipes_count = 0

            for recipe_data in recipes_to_import:
                name = recipe_data.get("name")
                if not name or name.lower() in existing_recipe_names:
                    continue

                category = _get_or_create_food_category(
                    recipe_data.get("category"), current_user.id, name
                )

                new_recipe = Recipe(
                    user_id=current_user.id,
                    name=name,
                    servings=recipe_data.get("servings", 1),
                    instructions=recipe_data.get("instructions"),
                    is_public=False,  # Always import as private
                    food_category=category,
                )
                db.session.add(new_recipe)
                db.session.flush()

                for portion_data in recipe_data.get("portions", []):
                    portion = UnifiedPortion(
                        recipe_id=new_recipe.id,
                        amount=portion_data.get("amount"),
                        measure_unit_description=portion_data.get(
                            "measure_unit_description"
                        ),
                        gram_weight=portion_data.get("gram_weight"),
                    )
                    db.session.add(portion)

                recipes_map[name.lower()] = new_recipe
                existing_recipe_names.add(name.lower())
                new_recipes_count += 1

            # --- Pass 3: Link Ingredients ---
            for recipe_data in recipes_to_import:
                recipe_name = recipe_data.get("name")
                if not recipe_name or recipe_name.lower() not in recipes_map:
                    continue

                recipe_obj = recipes_map[recipe_name.lower()]
                for ing_data in recipe_data.get("ingredients", []):
                    ing_type = ing_data.get("type")
                    identifier = ing_data.get("identifier")
                    amount_grams = ing_data.get("amount_grams")

                    ingredient = RecipeIngredient(
                        recipe_id=recipe_obj.id, amount_grams=amount_grams
                    )

                    if ing_type == "usda":
                        ingredient.fdc_id = identifier
                    elif ing_type == "my_food":
                        food_obj = MyFood.query.filter(
                            func.lower(MyFood.description) == identifier.lower(),
                            MyFood.user_id == current_user.id,
                        ).first()
                        if food_obj:
                            ingredient.my_food_id = food_obj.id
                    elif ing_type == "recipe":
                        # Check both existing and newly imported recipes
                        nested_recipe_obj = Recipe.query.filter(
                            func.lower(Recipe.name) == identifier.lower(),
                            Recipe.user_id == current_user.id,
                        ).first()
                        if nested_recipe_obj:
                            ingredient.recipe_id_link = nested_recipe_obj.id

                    db.session.add(ingredient)

                update_recipe_nutrition(recipe_obj)

            db.session.commit()
            flash(
                f"Import successful! Added {new_recipes_count} new recipes and {new_foods_count} new foods.",
                "success",
            )
            return redirect(url_for(RECIPES_LIST_ROUTE))
        else:
            flash("Invalid YAML format. Could not determine import type.", "danger")
            return redirect(url_for(IMPORT_RECIPES_ROUTE))

    except yaml.YAMLError as e:
        flash(f"Error parsing YAML file: {e}", "danger")
        return redirect(url_for(IMPORT_RECIPES_ROUTE))
    except Exception as e:
        db.session.rollback()
        flash(f"An unexpected error occurred during import: {e}", "danger")
        current_app.logger.error(f"Recipe import failed: {e}")
        return redirect(url_for(IMPORT_RECIPES_ROUTE))


@recipes_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_recipes():
    if request.method == "POST":
        if "file" in request.files and request.files["file"].filename != "":
            file = request.files["file"]
            if file and (
                file.filename.endswith(".yaml") or file.filename.endswith(".yml")
            ):
                return _process_recipe_yaml_import(file.stream)
            else:
                flash("Invalid file type. Please upload a .yaml file.", "danger")
        elif "yaml_text" in request.form and request.form["yaml_text"].strip():
            return _process_recipe_yaml_import(request.form["yaml_text"])
        else:
            flash("No file or text provided.", "info")
        return redirect(url_for(IMPORT_RECIPES_ROUTE))

    return render_template("recipes/import_recipes.html")


@recipes_bp.route("/export", methods=["GET"])
@login_required
def export_recipes():
    user_recipes = (
        Recipe.query.options(
            subqueryload(Recipe.ingredients).subqueryload(RecipeIngredient.my_food),
            subqueryload(Recipe.ingredients).subqueryload(
                RecipeIngredient.linked_recipe
            ),
            subqueryload(Recipe.portions),
            subqueryload(Recipe.food_category),
        )
        .filter_by(user_id=current_user.id)
        .all()
    )

    dependent_my_foods = {}
    recipes_to_export_data = []

    # Use a set to keep track of recipes to include, ensuring no duplicates
    recipes_to_process = set(user_recipes)
    processed_recipe_ids = set()

    while recipes_to_process:
        recipe = recipes_to_process.pop()
        if recipe.id in processed_recipe_ids:
            continue
        processed_recipe_ids.add(recipe.id)

        ingredients_data = []
        for ing in recipe.ingredients:
            ing_info = {
                "amount_grams": ing.amount_grams,
            }
            portion = db.session.get(UnifiedPortion, ing.portion_id_fk)
            if portion:
                ing_info["portion"] = {
                    "amount": portion.amount,
                    "measure_unit_description": portion.measure_unit_description,
                }

            if ing.fdc_id:
                ing_info["type"] = "usda"
                ing_info["identifier"] = ing.fdc_id
            elif ing.my_food_id:
                ing_info["type"] = "my_food"
                ing_info["identifier"] = ing.my_food.description
                if ing.my_food.id not in dependent_my_foods:
                    dependent_my_foods[ing.my_food.id] = ing.my_food
            elif ing.recipe_id_link:
                ing_info["type"] = "recipe"
                ing_info["identifier"] = ing.linked_recipe.name
                # If the linked recipe is also a user recipe, ensure it's processed
                if (
                    ing.linked_recipe.user_id == current_user.id
                    and ing.linked_recipe.id not in processed_recipe_ids
                ):
                    recipes_to_process.add(ing.linked_recipe)

            ingredients_data.append(ing_info)

        portions_data = [
            {
                "amount": p.amount,
                "measure_unit_description": p.measure_unit_description,
                "gram_weight": p.gram_weight,
            }
            for p in recipe.portions
        ]

        recipe_data = {
            "name": recipe.name,
            "servings": recipe.servings,
            "instructions": recipe.instructions,
            "category": recipe.food_category.description
            if recipe.food_category
            else "",
            "is_public": recipe.is_public,
            "portions": portions_data,
            "ingredients": ingredients_data,
        }
        recipes_to_export_data.append(recipe_data)

    # Format dependent MyFoods for export
    my_foods_export_data = []
    for food in dependent_my_foods.values():
        food_portions_data = [
            {
                "amount": p.amount,
                "measure_unit_description": p.measure_unit_description or "",
                "gram_weight": p.gram_weight,
            }
            for p in food.portions
        ]
        first_portion = food.portions[0] if food.portions else None
        nutrition_facts = {}
        if first_portion and first_portion.gram_weight > 0:
            scaling_factor = first_portion.gram_weight / 100.0
            nutrition_facts = {
                "calories": (food.calories_per_100g or 0) * scaling_factor,
                "protein_grams": (food.protein_per_100g or 0) * scaling_factor,
                "carbohydrates_grams": (food.carbs_per_100g or 0) * scaling_factor,
                "fat_grams": (food.fat_per_100g or 0) * scaling_factor,
            }

        my_foods_export_data.append(
            {
                "description": food.description,
                "category": food.food_category.description
                if food.food_category
                else "",
                "ingredients": food.ingredients or "",
                "upc": food.upc or "",
                "portions": food_portions_data,
                "nutrition_facts": nutrition_facts,
            }
        )

    # Final YAML structure
    export_payload = {
        "format_version": 1.0,
        "exported_on": datetime.now(timezone.utc).isoformat(),
        "dependent_my_foods": my_foods_export_data,
        "recipes": recipes_to_export_data,
    }

    yaml_content = yaml.dump(
        export_payload, default_flow_style=False, sort_keys=False, indent=2
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recipes_export_{timestamp}.yaml"

    return Response(
        yaml_content,
        mimetype="application/x-yaml",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _process_ingredient_for_display(ingredient, usda_foods_map):
    description = "Unknown Food"
    if hasattr(ingredient, "usda_food") and ingredient.usda_food:
        description = ingredient.usda_food.description
    elif ingredient.my_food:
        description = ingredient.my_food.description
    elif ingredient.linked_recipe:
        description = ingredient.linked_recipe.name

    quantity = ingredient.amount_grams
    portion_description = "g"
    selected_portion = None

    if ingredient.portion_id_fk:
        selected_portion = db.session.get(UnifiedPortion, ingredient.portion_id_fk)

    if selected_portion and selected_portion.gram_weight > 0:
        quantity = ingredient.amount_grams / selected_portion.gram_weight
        portion_description = selected_portion.full_description_str
    # No else needed, defaults are already set

    return {
        "description": description,
        "quantity": quantity,
        "portion_description": portion_description,
        "amount_grams": ingredient.amount_grams,
        "fdc_id": ingredient.fdc_id,
        "my_food_id": ingredient.my_food_id,
        "recipe_id_link": ingredient.recipe_id_link,
        "selected_portion": selected_portion,
    }


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
            final_weight_grams=form.final_weight_grams.data,
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
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=new_recipe.id))
    return render_template(
        "recipes/edit_recipe.html",
        form=form,
        recipe=None,
        portion_form=PortionForm(),
        ingredients_for_display=[],
        total_ingredient_weight=0,
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

    # Ensure all ingredients have a seq_num
    if any(ing.seq_num is None for ing in recipe.ingredients):
        ingredients_to_update = sorted(
            recipe.ingredients, key=lambda ing: ing.id
        )  # Sort by ID for initial assignment
        for i, ing in enumerate(ingredients_to_update):
            ing.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all ingredients.", "info")

    # Manually fetch USDA food data
    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    usda_foods_map = {}
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}

    ingredients_for_display = []
    for ing in recipe.ingredients:
        if ing.fdc_id:
            ing.usda_food = usda_foods_map.get(ing.fdc_id)

        # Calculate nutrition for each individual ingredient
        ingredient_nutrition = calculate_nutrition_for_items([ing])

        # Calculate quantity and portion description for display
        food_object = None
        if hasattr(ing, "usda_food") and ing.usda_food:
            food_object = ing.usda_food
        elif ing.my_food:
            food_object = ing.my_food
        elif ing.linked_recipe:
            food_object = ing.linked_recipe

        display_quantity = ing.amount_grams
        display_portion_description = "g"
        available_portions = []
        selected_portion = None

        if ing.portion_id_fk:
            selected_portion = db.session.get(UnifiedPortion, ing.portion_id_fk)

        if food_object:
            ensure_portion_sequence([food_object])
            available_portions = get_available_portions(food_object)

        if selected_portion and selected_portion.gram_weight > 0:
            display_quantity = ing.amount_grams / selected_portion.gram_weight
            display_portion_description = selected_portion.full_description_str
        # No else needed, defaults are already set

        ingredients_for_display.append(
            {
                "id": ing.id,
                "fdc_id": ing.fdc_id,
                "my_food_id": ing.my_food_id,
                "recipe_id_link": ing.recipe_id_link,
                "amount_grams": ing.amount_grams,
                "serving_type": ing.serving_type,
                "portion_id_fk": ing.portion_id_fk,
                "seq_num": ing.seq_num,
                "food": ing.food,  # This will be the USDA Food object if fdc_id is present
                "my_food": ing.my_food,
                "linked_recipe": ing.linked_recipe,
                "calories": ingredient_nutrition["calories"],
                "protein": ingredient_nutrition["protein"],
                "carbs": ingredient_nutrition["carbs"],
                "fat": ingredient_nutrition["fat"],
                "quantity": display_quantity,
                "portion_description": display_portion_description,
                "available_portions": available_portions,
                "selected_portion": selected_portion,
                "total_gram_weight": ing.amount_grams,
            }
        )

    if recipe.user_id != current_user.id:
        flash("You are not authorized to edit this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

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
    final_weight_grams_param = request.args.get("final_weight_grams_param", type=str)

    if servings_param is not None:
        form.servings.data = servings_param
    if name_param is not None:
        form.name.data = name_param
    if instructions_param is not None:
        form.instructions.data = instructions_param
    if final_weight_grams_param is not None:
        try:
            form.final_weight_grams.data = float(final_weight_grams_param)
        except (ValueError, TypeError):
            form.final_weight_grams.data = None

    portion_form = PortionForm()

    if form.validate_on_submit():
        # Manually handle populating the object to avoid the relationship error
        recipe.name = form.name.data
        recipe.instructions = form.instructions.data
        recipe.servings = form.servings.data
        recipe.upc = form.upc.data
        recipe.final_weight_grams = form.final_weight_grams.data

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
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

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
        if final_weight_grams_param is not None:
            try:
                form.final_weight_grams.data = float(final_weight_grams_param)
            except (ValueError, TypeError):
                form.final_weight_grams.data = None

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

    total_ingredient_weight = sum(
        ing.amount_grams for ing in recipe.ingredients if ing.amount_grams
    )

    return render_template(
        "recipes/edit_recipe.html",
        form=form,
        recipe=recipe,
        portion_form=portion_form,
        get_available_portions=get_available_portions,
        search_term=query,
        ingredients_for_display=ingredients_for_display,
        timestamp=datetime.now(timezone.utc).timestamp(),
        total_ingredient_weight=total_ingredient_weight,
    )


@recipes_bp.route("/ingredients/<int:ingredient_id>/delete", methods=["POST"])
@login_required
def delete_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

    redirect_info = {
        "endpoint": EDIT_RECIPE_ROUTE,
        "params": {"recipe_id": recipe.id},
        "fragment": "ingredients-section",
    }
    # This is a hard delete
    prepare_undo_and_delete(
        ingredient,
        "recipe_ingredient",
        redirect_info,
        success_message="Ingredient deleted.",
    )
    update_recipe_nutrition(recipe)
    db.session.commit()

    return redirect(
        url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id) + INGREDIENTS_SECTION_FRAGMENT
    )


@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/update", methods=["POST"])
@login_required
def update_ingredient(ingredient_id):
    ingredient = RecipeIngredient.query.get_or_404(ingredient_id)
    recipe = ingredient.recipe
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

    amount = request.form.get("amount", type=float)
    portion_id = request.form.get("portion_id", type=int)

    if amount is None or amount <= 0:
        flash("Amount must be a positive number.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

    if portion_id is None:
        flash("Portion is required.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

    portion_obj = db.session.get(UnifiedPortion, portion_id)
    if not portion_obj:
        flash("Selected portion not found.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

    ingredient.amount_grams = amount * portion_obj.gram_weight
    ingredient.serving_type = portion_obj.full_description_str
    ingredient.portion_id_fk = portion_obj.id
    update_recipe_nutrition(recipe)
    db.session.commit()
    flash("Ingredient updated successfully.", "success")
    return redirect(
        url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id) + INGREDIENTS_SECTION_FRAGMENT
    )


@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/move_up", methods=["POST"])
@login_required
def move_recipe_ingredient_up(ingredient_id):
    ingredient_to_move = db.session.get(RecipeIngredient, ingredient_id)
    if not ingredient_to_move or ingredient_to_move.recipe.user_id != current_user.id:
        flash("Ingredient not found or unauthorized.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

    if ingredient_to_move.seq_num is None:
        # Assign sequence numbers to all ingredients of this recipe if any are missing
        ingredients = (
            RecipeIngredient.query.filter_by(recipe_id=ingredient_to_move.recipe_id)
            .order_by(
                RecipeIngredient.id
            )  # Use ID for initial assignment if seq_num is missing
            .all()
        )
        for i, ing in enumerate(ingredients):
            ing.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all ingredients. Please try again.", "info")
        return redirect(
            url_for(EDIT_RECIPE_ROUTE, recipe_id=ingredient_to_move.recipe_id)
        )

    # Find the ingredient with the next lower seq_num
    ingredient_to_swap_with = (
        RecipeIngredient.query.filter(
            RecipeIngredient.recipe_id == ingredient_to_move.recipe_id,
            RecipeIngredient.seq_num < ingredient_to_move.seq_num,
        )
        .order_by(RecipeIngredient.seq_num.desc())
        .first()
    )

    if ingredient_to_swap_with:
        # Swap seq_num values
        ingredient_to_move.seq_num, ingredient_to_swap_with.seq_num = (
            ingredient_to_swap_with.seq_num,
            ingredient_to_move.seq_num,
        )
        db.session.commit()
        flash("Ingredient moved up.", "success")
    else:
        flash("Ingredient is already at the top.", "info")

    return redirect(
        url_for(EDIT_RECIPE_ROUTE, recipe_id=ingredient_to_move.recipe_id)
        + INGREDIENTS_SECTION_FRAGMENT
    )


@recipes_bp.route("/recipe/ingredient/<int:ingredient_id>/move_down", methods=["POST"])
@login_required
def move_recipe_ingredient_down(ingredient_id):
    ingredient_to_move = db.session.get(RecipeIngredient, ingredient_id)
    if not ingredient_to_move or ingredient_to_move.recipe.user_id != current_user.id:
        flash("Ingredient not found or unauthorized.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

    if ingredient_to_move.seq_num is None:
        # Assign sequence numbers to all ingredients of this recipe if any are missing
        ingredients = (
            RecipeIngredient.query.filter_by(recipe_id=ingredient_to_move.recipe_id)
            .order_by(
                RecipeIngredient.id
            )  # Use ID for initial assignment if seq_num is missing
            .all()
        )
        for i, ing in enumerate(ingredients):
            ing.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all ingredients. Please try again.", "info")
        return redirect(
            url_for(EDIT_RECIPE_ROUTE, recipe_id=ingredient_to_move.recipe_id)
        )

    # Find the ingredient with the next higher seq_num
    ingredient_to_swap_with = (
        RecipeIngredient.query.filter(
            RecipeIngredient.recipe_id == ingredient_to_move.recipe_id,
            RecipeIngredient.seq_num > ingredient_to_move.seq_num,
        )
        .order_by(RecipeIngredient.seq_num.asc())
        .first()
    )

    if ingredient_to_swap_with:
        # Swap seq_num values
        ingredient_to_move.seq_num, ingredient_to_swap_with.seq_num = (
            ingredient_to_swap_with.seq_num,
            ingredient_to_move.seq_num,
        )
        db.session.commit()
        flash("Ingredient moved down.", "success")
    else:
        flash("Ingredient is already at the bottom.", "info")

    return redirect(
        url_for(EDIT_RECIPE_ROUTE, recipe_id=ingredient_to_move.recipe_id)
        + INGREDIENTS_SECTION_FRAGMENT
    )


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
        return redirect(url_for(RECIPES_LIST_ROUTE))

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

    ingredient_details = [
        _process_ingredient_for_display(ingredient, usda_foods_map)
        for ingredient in recipe.ingredients
    ]

    form = AddToLogForm()
    return render_template(
        "recipes/view_recipe.html",
        recipe=recipe,
        ingredients=ingredient_details,
        totals=total_nutrition,
        form=form,
        timestamp=datetime.now(timezone.utc).timestamp(),
    )


@recipes_bp.route("/<int:recipe_id>/delete", methods=["POST"])
@login_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash("You are not authorized to delete this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

    redirect_info = {"endpoint": RECIPES_LIST_ROUTE}
    prepare_undo_and_delete(
        recipe,
        "recipe",
        redirect_info,
        delete_method="anonymize",
        success_message="Recipe deleted.",
    )

    return redirect(url_for(RECIPES_LIST_ROUTE))


@recipes_bp.route("/recipe/portion/auto_add/<int:recipe_id>", methods=["POST"])
@login_required
def auto_add_recipe_portion(recipe_id):
    recipe = Recipe.query.options(selectinload(Recipe.ingredients)).get_or_404(
        recipe_id
    )
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

    servings_from_form = request.form.get("servings", type=float)
    if servings_from_form is None or servings_from_form <= 0:
        flash("Invalid servings value provided.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

    # Use final_weight_grams from the form if available
    final_weight_from_form = request.form.get("final_weight_grams", type=float)
    if final_weight_from_form and final_weight_from_form > 0:
        total_gram_weight = final_weight_from_form
        flash("Portion created based on the final cooked weight of the recipe.", "info")
    else:
        total_gram_weight = sum(
            ing.amount_grams
            for ing in recipe.ingredients
            if ing.amount_grams is not None
        )
        flash(
            "Portion created based on the sum of ingredient weights. For better accuracy, you can provide a final cooked weight.",
            "info",
        )

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
    final_weight_grams_from_form = request.form.get("final_weight_grams", type=str)

    return redirect(
        url_for(
            EDIT_RECIPE_ROUTE,
            recipe_id=recipe.id,
            servings_param=servings_from_form,
            name_param=name_from_form,
            instructions_param=instructions_from_form,
            final_weight_grams_param=final_weight_grams_from_form,
        )
    )


@recipes_bp.route("/recipe/portion/add/<int:recipe_id>", methods=["POST"])
@login_required
def add_recipe_portion(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.user_id != current_user.id:
        flash("You are not authorized to modify this recipe.", "danger")
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))

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

    return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe.id))


@recipes_bp.route("/recipe/portion/update/<int:portion_id>", methods=["POST"])
@login_required
def update_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or portion.recipe.user_id != current_user.id:
        flash("Portion not found or you do not have permission to edit it.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

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
        url_for(EDIT_RECIPE_ROUTE, recipe_id=portion.recipe_id) + PORTION_TABLE_FRAGMENT
    )


@recipes_bp.route("/recipe/portion/delete/<int:portion_id>", methods=["POST"])
@login_required
def delete_recipe_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if portion and portion.recipe and portion.recipe.user_id == current_user.id:
        recipe_id = portion.recipe_id
        redirect_info = {
            "endpoint": EDIT_RECIPE_ROUTE,
            "params": {"recipe_id": recipe_id},
            "fragment": "portions-table",
        }
        prepare_undo_and_delete(
            portion, "portion", redirect_info, success_message="Portion deleted."
        )
        return redirect(
            url_for(EDIT_RECIPE_ROUTE, recipe_id=recipe_id) + PORTION_TABLE_FRAGMENT
        )
    else:
        flash("Portion not found or you do not have permission to delete it.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))


@recipes_bp.route("/<int:recipe_id>/generate_label_pdf")
@login_required
def generate_label_pdf(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if not recipe.is_public and recipe.user_id != current_user.id:
        flash("You are not authorized to view this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))
    return generate_recipe_label_pdf(recipe_id, label_only=True)


@recipes_bp.route("/<int:recipe_id>/nutrition-label.svg")
@login_required
def nutrition_label_svg(recipe_id):
    return generate_recipe_label_svg(recipe_id)


@recipes_bp.route("/<int:recipe_id>/generate_pdf_details")
@login_required
def generate_pdf_details(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if not recipe.is_public and recipe.user_id != current_user.id:
        flash("You are not authorized to view this recipe.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))
    return generate_recipe_label_pdf(recipe_id, label_only=False)


@recipes_bp.route("/<int:recipe_id>/copy", methods=["POST"])
@login_required
def copy_recipe(recipe_id):
    original_recipe = Recipe.query.options(
        selectinload(Recipe.ingredients), selectinload(Recipe.portions)
    ).get_or_404(recipe_id)

    # Allow cloning own recipe, or copying from a friend/public recipe
    if original_recipe.user_id != current_user.id:
        friend_ids = [friend.id for friend in current_user.friends]
        if not original_recipe.is_public and original_recipe.user_id not in friend_ids:
            flash(
                "You can only copy recipes from your friends or public recipes.",
                "danger",
            )
            return redirect(request.referrer or url_for(RECIPES_LIST_ROUTE))

    # Create a new recipe for the current user
    new_recipe = Recipe(
        user_id=current_user.id,
        name=f"{original_recipe.name} (Copy)",
        instructions=original_recipe.instructions,
        servings=original_recipe.servings,
        final_weight_grams=original_recipe.final_weight_grams,
        is_public=False,  # Copied recipes are private by default
    )
    db.session.add(new_recipe)
    db.session.flush()  # Flush to get the new_recipe.id for ingredients

    # Copy ingredients
    for i, orig_ing in enumerate(original_recipe.ingredients):
        new_ing = RecipeIngredient(
            recipe_id=new_recipe.id,
            fdc_id=orig_ing.fdc_id,
            my_food_id=orig_ing.my_food_id,
            recipe_id_link=orig_ing.recipe_id_link,
            amount_grams=orig_ing.amount_grams,
            serving_type=orig_ing.serving_type,
            portion_id_fk=orig_ing.portion_id_fk,
            seq_num=i + 1,
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
            seq_num=orig_portion.seq_num,
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(f"Successfully copied '{original_recipe.name}' to your recipes.", "success")
    return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=new_recipe.id))


@recipes_bp.route("/portion/<int:portion_id>/move_up", methods=["POST"])
@login_required
def move_recipe_portion_up(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.recipe.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

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
        return redirect(url_for(EDIT_RECIPE_ROUTE, recipe_id=portion_to_move.recipe_id))

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
        url_for(EDIT_RECIPE_ROUTE, recipe_id=portion_to_move.recipe_id)
        + PORTION_TABLE_FRAGMENT
    )


@recipes_bp.route("/portion/<int:portion_id>/move_down", methods=["POST"])
@login_required
def move_recipe_portion_down(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.recipe.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for(RECIPES_LIST_ROUTE))

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
        url_for(EDIT_RECIPE_ROUTE, recipe_id=portion_to_move.recipe_id)
        + PORTION_TABLE_FRAGMENT
    )
