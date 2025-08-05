from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    Blueprint,
    current_app,
)
from flask_login import login_required, current_user
from models import (
    db,
    MyFood,
    Food,
    FoodNutrient,
    UnifiedPortion,
    FoodCategory,
)
from opennourish.my_foods.forms import MyFoodForm, PortionForm
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from opennourish.utils import (
    generate_myfood_label_pdf,
    ensure_portion_sequence,
    get_nutrients_for_display,
    convert_display_nutrients_to_100g,
)

my_foods_bp = Blueprint("my_foods", __name__)


@my_foods_bp.route("/")
@login_required
def my_foods():
    page = request.args.get("page", 1, type=int)
    view_mode = request.args.get("view", "user")  # 'user' or 'friends'
    per_page = 10

    query = MyFood.query
    if view_mode == "friends":
        friend_ids = [friend.id for friend in current_user.friends]
        # Eager load the 'user' relationship to get usernames efficiently
        query = query.options(joinedload(MyFood.user))
        if not friend_ids:
            # No friends, so return an empty query
            query = query.filter(db.false())
        else:
            query = query.filter(MyFood.user_id.in_(friend_ids))
    else:  # Default to user's foods
        query = query.filter_by(user_id=current_user.id)

    my_foods_pagination = query.order_by(MyFood.description).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "my_foods/my_foods.html", my_foods=my_foods_pagination, view_mode=view_mode
    )


@my_foods_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_my_food():
    form = MyFoodForm()
    form.food_category.choices = [("", "-- Select a Category --")] + [
        (c.id, c.description) for c in FoodCategory.query.order_by(FoodCategory.code)
    ]
    portion_form = PortionForm(prefix="portion_form")

    # Change form labels for the 'new' page context
    nutrient_fields = [
        "calories_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "fat_per_100g",
        "saturated_fat_per_100g",
        "trans_fat_per_100g",
        "cholesterol_mg_per_100g",
        "sodium_mg_per_100g",
        "fiber_per_100g",
        "sugars_per_100g",
        "added_sugars_per_100g",
        "vitamin_d_mcg_per_100g",
        "calcium_mg_per_100g",
        "iron_mg_per_100g",
        "potassium_mg_per_100g",
    ]
    for field_name in nutrient_fields:
        field = getattr(form, field_name)
        field.label.text = field.label.text.replace(" per 100g", "")

    if form.validate_on_submit() and portion_form.validate_on_submit():
        gram_weight = portion_form.gram_weight.data
        if not gram_weight or gram_weight <= 0:
            flash("Gram weight of the portion must be greater than zero.", "danger")
            return render_template(
                "my_foods/new_my_food.html", form=form, portion_form=portion_form
            )

        factor = 100.0 / gram_weight

        my_food = MyFood(
            user_id=current_user.id,
            description=form.description.data,
            ingredients=form.ingredients.data,
            food_category_id=form.food_category.data
            if form.food_category.data
            else None,
        )

        nutrient_fields = [
            "calories_per_100g",
            "protein_per_100g",
            "carbs_per_100g",
            "fat_per_100g",
            "saturated_fat_per_100g",
            "trans_fat_per_100g",
            "cholesterol_mg_per_100g",
            "sodium_mg_per_100g",
            "fiber_per_100g",
            "sugars_per_100g",
            "added_sugars_per_100g",
            "vitamin_d_mcg_per_100g",
            "calcium_mg_per_100g",
            "iron_mg_per_100g",
            "potassium_mg_per_100g",
        ]
        for field_name in nutrient_fields:
            field = getattr(form, field_name)
            if field.data is not None:
                setattr(my_food, field_name, field.data * factor)

        db.session.add(my_food)
        db.session.flush()  # Get the ID for the new food item

        # Create the user-defined portion
        new_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=portion_form.amount.data,
            measure_unit_description=portion_form.measure_unit_description.data,
            portion_description=portion_form.portion_description.data,
            modifier=portion_form.modifier.data,
            gram_weight=portion_form.gram_weight.data,
        )
        db.session.add(new_portion)

        # Also create the default 1-gram portion for easy scaling
        gram_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=1.0,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0,
        )
        db.session.add(gram_portion)

        db.session.commit()
        flash(
            "Custom food added successfully! Nutritional values have been scaled to 100g.",
            "success",
        )
        return redirect(url_for("my_foods.edit_my_food", food_id=my_food.id))

    return render_template(
        "my_foods/new_my_food.html", form=form, portion_form=portion_form
    )


@my_foods_bp.route("/<int:food_id>/edit", methods=["GET", "POST"])
@login_required
def edit_my_food(food_id):
    my_food = MyFood.query.options(selectinload(MyFood.portions)).get_or_404(food_id)
    if my_food.user_id != current_user.id:
        flash("You are not authorized to edit this food.", "danger")
        return redirect(url_for("my_foods.my_foods"))

    ensure_portion_sequence([my_food])
    portions = sorted(
        my_food.portions,
        key=lambda p: p.seq_num if p.seq_num is not None else float("inf"),
    )

    form = MyFoodForm(obj=my_food)
    form.food_category.choices = [("", "-- Select a Category --")] + [
        (c.id, c.description) for c in FoodCategory.query.order_by(FoodCategory.code)
    ]
    portion_form = PortionForm(prefix="portion_form")

    if form.validate_on_submit():
        submitted_portion_id = request.form.get("selected_portion_id", type=int)
        submitted_portion = db.session.get(UnifiedPortion, submitted_portion_id)

        if not submitted_portion or submitted_portion.my_food_id != my_food.id:
            flash("Invalid portion selected for nutrient input.", "danger")
            return redirect(url_for("my_foods.edit_my_food", food_id=my_food.id))

        submitted_nutrients = {
            "calories": form.calories_per_100g.data,
            "protein": form.protein_per_100g.data,
            "carbs": form.carbs_per_100g.data,
            "fat": form.fat_per_100g.data,
            "saturated_fat": form.saturated_fat_per_100g.data,
            "trans_fat": form.trans_fat_per_100g.data,
            "cholesterol": form.cholesterol_mg_per_100g.data,
            "sodium": form.sodium_mg_per_100g.data,
            "fiber": form.fiber_per_100g.data,
            "sugars": form.sugars_per_100g.data,
            "added_sugars": form.added_sugars_per_100g.data,
            "vitamin_d": form.vitamin_d_mcg_per_100g.data,
            "calcium": form.calcium_mg_per_100g.data,
            "iron": form.iron_mg_per_100g.data,
            "potassium": form.potassium_mg_per_100g.data,
        }
        nutrients_100g = convert_display_nutrients_to_100g(
            submitted_nutrients, submitted_portion
        )

        my_food.description = form.description.data
        my_food.ingredients = form.ingredients.data
        my_food.fdc_id = form.fdc_id.data
        my_food.upc = form.upc.data
        my_food.food_category_id = form.food_category.data or None

        for key, value in nutrients_100g.items():
            field_name = key + "_per_100g"
            if key in ["cholesterol", "sodium", "calcium", "iron", "potassium"]:
                field_name = key + "_mg_per_100g"
            elif key == "vitamin_d":
                field_name = key + "_mcg_per_100g"
            setattr(my_food, field_name, value)

        db.session.commit()
        flash("Custom food updated successfully.", "success")
        return redirect(
            url_for(
                "my_foods.edit_my_food",
                food_id=my_food.id,
                portion_id=submitted_portion.id,
            )
        )

    # GET Request Logic
    selected_portion_id = request.args.get("portion_id", type=int)
    selected_portion = (
        db.session.get(UnifiedPortion, selected_portion_id)
        if selected_portion_id
        else None
    )
    if not selected_portion or selected_portion.my_food_id != my_food.id:
        selected_portion = next(
            (p for p in portions if p.seq_num == 1), portions[0] if portions else None
        )

    scaled_nutrients = get_nutrients_for_display(my_food, selected_portion)

    return render_template(
        "my_foods/edit_my_food.html",
        form=form,
        my_food=my_food,
        portion_form=portion_form,
        portions=portions,
        selected_portion=selected_portion,
        scaled_nutrients=scaled_nutrients,
    )


@my_foods_bp.route("/<int:food_id>/delete", methods=["POST"])
@login_required
def delete_my_food(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    my_food.user_id = None
    db.session.commit()
    flash("Food deleted successfully!", "success")
    return redirect(url_for("my_foods.my_foods"))


@my_foods_bp.route("/<int:food_id>/add_portion", methods=["POST"])
@login_required
def add_my_food_portion(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    form = PortionForm()
    if form.validate_on_submit():
        # Calculate the next seq_num
        max_seq_num = (
            db.session.query(func.max(UnifiedPortion.seq_num))
            .filter(UnifiedPortion.my_food_id == food_id)
            .scalar()
        )
        next_seq_num = (max_seq_num or 0) + 1

        new_portion = UnifiedPortion(
            my_food_id=my_food.id,
            recipe_id=None,
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
        flash("Portion added successfully!", "success")
    else:
        flash("Error adding portion.", "danger")
    return redirect(
        url_for("my_foods.edit_my_food", food_id=my_food.id) + "#portions-table"
    )


@my_foods_bp.route("/portion/<int:portion_id>/update", methods=["POST"])
@login_required
def update_my_food_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or portion.my_food.user_id != current_user.id:
        flash("Portion not found or you do not have permission to edit it.", "danger")
        return redirect(url_for("my_foods.my_foods"))

    form = PortionForm(request.form, obj=portion)
    if form.validate_on_submit():
        form.populate_obj(portion)
        db.session.commit()
        flash("Portion updated successfully!", "success")
    else:
        current_app.logger.debug(f"PortionForm errors: {form.errors}")
        flash("Error updating portion.", "danger")
    return redirect(
        url_for("my_foods.edit_my_food", food_id=portion.my_food_id) + "#portions-table"
    )


@my_foods_bp.route("/portion/<int:portion_id>/delete", methods=["POST"])
@login_required
def delete_my_food_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if portion and portion.my_food and portion.my_food.user_id == current_user.id:
        food_id = portion.my_food_id
        db.session.delete(portion)
        db.session.commit()
        flash("Portion deleted.", "success")
        return redirect(
            url_for("my_foods.edit_my_food", food_id=food_id) + "#portions-table"
        )
    else:
        flash("Portion not found or you do not have permission to delete it.", "danger")
        return redirect(url_for("my_foods.my_foods"))


@my_foods_bp.route("/copy_usda", methods=["POST"])
@login_required
def copy_usda_food():
    fdc_id = request.form.get("fdc_id")
    if not fdc_id:
        flash("No USDA Food ID provided for copying.", "danger")
        return redirect(request.referrer or url_for("my_foods.my_foods"))

    usda_food = (
        Food.query.options(joinedload(Food.nutrients).joinedload(FoodNutrient.nutrient))
        .filter_by(fdc_id=fdc_id)
        .first_or_404()
    )

    # Create the new MyFood object
    new_food = MyFood(
        user_id=current_user.id,
        description=usda_food.description,
        food_category_id=usda_food.food_category_id,
        ingredients=usda_food.ingredients,
        fdc_id=usda_food.fdc_id,
        upc=usda_food.upc,
    )

    # Nutrient mapping dictionary (Nutrient Name from USDA -> MyFood attribute)
    nutrient_map = {
        "Energy": "calories_per_100g",
        "Protein": "protein_per_100g",
        "Carbohydrate, by difference": "carbs_per_100g",
        "Total lipid (fat)": "fat_per_100g",
        "Fatty acids, total saturated": "saturated_fat_per_100g",
        "Fatty acids, total trans": "trans_fat_per_100g",
        "Cholesterol": "cholesterol_mg_per_100g",
        "Sodium, Na": "sodium_mg_per_100g",
        "Fiber, total dietary": "fiber_per_100g",
        "Sugars, total including NLEA": "sugars_per_100g",
        "Sugars, added": "added_sugars_per_100g",
        "Vitamin D (D2 + D3)": "vitamin_d_mcg_per_100g",
        "Calcium, Ca": "calcium_mg_per_100g",
        "Iron, Fe": "iron_mg_per_100g",
        "Potassium, K": "potassium_mg_per_100g",
    }

    # Populate nutrients from the USDA food using the map
    for nutrient_link in usda_food.nutrients:
        nutrient_name = nutrient_link.nutrient.name
        my_food_attr = nutrient_map.get(nutrient_name)
        if my_food_attr:
            # For 'Energy', only copy it if the unit is KCAL.
            if nutrient_name == "Energy":
                if nutrient_link.nutrient.unit_name.lower() == "kcal":
                    setattr(new_food, my_food_attr, nutrient_link.amount)
            # For all other mapped nutrients, copy them directly.
            else:
                setattr(new_food, my_food_attr, nutrient_link.amount)

    db.session.add(new_food)
    db.session.flush()  # Flush to get the new_food.id

    # Deep copy portions from the original USDA food, preserving seq_num
    original_portions = (
        UnifiedPortion.query.filter_by(fdc_id=usda_food.fdc_id)
        .order_by(UnifiedPortion.seq_num)
        .all()
    )
    for orig_portion in original_portions:
        new_portion = UnifiedPortion(
            my_food_id=new_food.id,
            amount=orig_portion.amount,
            measure_unit_description=orig_portion.measure_unit_description,
            portion_description=orig_portion.portion_description,
            modifier=orig_portion.modifier,
            gram_weight=orig_portion.gram_weight,
            seq_num=orig_portion.seq_num,  # Copy the sequence number
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(f"Successfully created '{new_food.description}' from USDA data.", "success")
    return redirect(url_for("my_foods.edit_my_food", food_id=new_food.id))


@my_foods_bp.route("/<int:food_id>/copy", methods=["POST"])
@login_required
def copy_my_food(food_id):
    # This route now exclusively handles copying an existing MyFood
    original_food = MyFood.query.options(joinedload(MyFood.portions)).get_or_404(
        food_id
    )
    friend_ids = [friend.id for friend in current_user.friends]
    if (
        original_food.user_id not in friend_ids
        and original_food.user_id != current_user.id
    ):
        flash("You can only copy foods from your friends or your own foods.", "danger")
        return redirect(request.referrer or url_for("my_foods.my_foods"))

    new_food = MyFood(
        user_id=current_user.id,
        description=f"{original_food.description} (Copy)",
        ingredients=original_food.ingredients,
        calories_per_100g=original_food.calories_per_100g,
        protein_per_100g=original_food.protein_per_100g,
        carbs_per_100g=original_food.carbs_per_100g,
        fat_per_100g=original_food.fat_per_100g,
        saturated_fat_per_100g=original_food.saturated_fat_per_100g,
        trans_fat_per_100g=original_food.trans_fat_per_100g,
        cholesterol_mg_per_100g=original_food.cholesterol_mg_per_100g,
        sodium_mg_per_100g=original_food.sodium_mg_per_100g,
        fiber_per_100g=original_food.fiber_per_100g,
        sugars_per_100g=original_food.sugars_per_100g,
        added_sugars_per_100g=original_food.added_sugars_per_100g,
        vitamin_d_mcg_per_100g=original_food.vitamin_d_mcg_per_100g,
        calcium_mg_per_100g=original_food.calcium_mg_per_100g,
        iron_mg_per_100g=original_food.iron_mg_per_100g,
        potassium_mg_per_100g=original_food.potassium_mg_per_100g,
    )
    db.session.add(new_food)
    db.session.flush()

    for orig_portion in original_food.portions:
        new_portion = UnifiedPortion(
            my_food_id=new_food.id,
            amount=orig_portion.amount,
            measure_unit_description=orig_portion.measure_unit_description,
            portion_description=orig_portion.portion_description,
            modifier=orig_portion.modifier,
            gram_weight=orig_portion.gram_weight,
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(
        f"Successfully copied '{original_food.description}' to your foods.", "success"
    )
    return redirect(url_for("my_foods.my_foods"))


@my_foods_bp.route("/<int:food_id>/generate_pdf_label", methods=["GET"])
@login_required
def generate_pdf_label(food_id):
    # Verify the user owns the food item
    MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    return generate_myfood_label_pdf(food_id, label_only=True)


@my_foods_bp.route("/<int:food_id>/generate_pdf_details", methods=["GET"])
@login_required
def generate_pdf_details(food_id):
    # Verify the user owns the food item
    MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    return generate_myfood_label_pdf(food_id, label_only=False)


@my_foods_bp.route("/portion/<int:portion_id>/move_up", methods=["POST"])
@login_required
def move_my_food_portion_up(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.my_food.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for("my_foods.my_foods"))

    # Find the portion with the next lower seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.my_food_id == portion_to_move.my_food_id,
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
        url_for("my_foods.edit_my_food", food_id=portion_to_move.my_food_id)
        + "#portions-table"
    )


@my_foods_bp.route("/portion/<int:portion_id>/move_down", methods=["POST"])
@login_required
def move_my_food_portion_down(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or portion_to_move.my_food.user_id != current_user.id:
        flash("Portion not found or unauthorized.", "danger")
        return redirect(url_for("my_foods.my_foods"))

    # Find the portion with the next higher seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.my_food_id == portion_to_move.my_food_id,
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
        url_for("my_foods.edit_my_food", food_id=portion_to_move.my_food_id)
        + "#portions-table"
    )
