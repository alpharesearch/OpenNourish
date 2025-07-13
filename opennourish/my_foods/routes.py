from flask import render_template, request, redirect, url_for, flash, Blueprint, current_app
from flask_login import login_required, current_user
from models import db, MyFood, Food, Nutrient, FoodNutrient, UnifiedPortion, User
from opennourish.my_foods.forms import MyFoodForm, PortionForm
from sqlalchemy.orm import joinedload

my_foods_bp = Blueprint('my_foods', __name__)

@my_foods_bp.route('/')
@login_required
def my_foods():
    page = request.args.get('page', 1, type=int)
    view_mode = request.args.get('view', 'user') # 'user' or 'friends'
    per_page = 10

    query = MyFood.query
    if view_mode == 'friends':
        friend_ids = [friend.id for friend in current_user.friends]
        # Eager load the 'user' relationship to get usernames efficiently
        query = query.options(joinedload(MyFood.user))
        if not friend_ids:
            # No friends, so return an empty query
            query = query.filter(db.false())
        else:
            query = query.filter(MyFood.user_id.in_(friend_ids))
    else: # Default to user's foods
        query = query.filter_by(user_id=current_user.id)

    my_foods_pagination = query.order_by(MyFood.description).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('my_foods/my_foods.html', my_foods=my_foods_pagination, view_mode=view_mode)

@my_foods_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_my_food():
    form = MyFoodForm()
    portion_form = PortionForm()

    # Change form labels for the 'new' page context
    nutrient_fields = [
        'calories_per_100g', 'protein_per_100g', 'carbs_per_100g', 'fat_per_100g',
        'saturated_fat_per_100g', 'trans_fat_per_100g', 'cholesterol_mg_per_100g',
        'sodium_mg_per_100g', 'fiber_per_100g', 'sugars_per_100g',
        'vitamin_d_mcg_per_100g', 'calcium_mg_per_100g', 'iron_mg_per_100g',
        'potassium_mg_per_100g'
    ]
    for field_name in nutrient_fields:
        field = getattr(form, field_name)
        field.label.text = field.label.text.replace(' per 100g', '')

    if form.validate_on_submit() and portion_form.validate_on_submit():
        gram_weight = portion_form.gram_weight.data
        if not gram_weight or gram_weight <= 0:
            flash('Gram weight of the portion must be greater than zero.', 'danger')
            return render_template('my_foods/new_my_food.html', form=form, portion_form=portion_form)

        factor = 100.0 / gram_weight

        my_food_data = {
            'user_id': current_user.id,
            'description': form.description.data,
            'ingredients': form.ingredients.data,
        }

        for field_name in nutrient_fields:
            field = getattr(form, field_name)
            if field.data is not None:
                # The form field name is `calories_per_100g`, so we use it directly
                my_food_data[field_name] = field.data * factor
        
        my_food = MyFood(**my_food_data)
        db.session.add(my_food)
        db.session.flush()  # Get the ID for the new food item

        # Create the user-defined portion
        new_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=portion_form.amount.data,
            measure_unit_description=portion_form.measure_unit_description.data,
            portion_description=portion_form.portion_description.data,
            modifier=portion_form.modifier.data,
            gram_weight=portion_form.gram_weight.data
        )
        db.session.add(new_portion)

        # Also create the default 1-gram portion for easy scaling
        gram_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=1.0,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0
        )
        db.session.add(gram_portion)

        db.session.commit()
        flash('Custom food added successfully! Nutritional values have been scaled to 100g.', 'success')
        return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))

    return render_template('my_foods/new_my_food.html', form=form, portion_form=portion_form)

@my_foods_bp.route('/<int:food_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_my_food(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    form = MyFoodForm(obj=my_food)
    portion_form = PortionForm()

    if form.validate_on_submit():
        form.populate_obj(my_food)
        db.session.commit()
        flash('Food updated successfully!', 'success')
        return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))
    
    return render_template('my_foods/edit_my_food.html', form=form, my_food=my_food, portion_form=portion_form)

@my_foods_bp.route('/<int:food_id>/delete', methods=['POST'])
@login_required
def delete_my_food(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    db.session.delete(my_food)
    db.session.commit()
    flash('Food deleted successfully!', 'success')
    return redirect(url_for('my_foods.my_foods'))



@my_foods_bp.route('/<int:food_id>/add_portion', methods=['POST'])
@login_required
def add_my_food_portion(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    form = PortionForm()
    if form.validate_on_submit():
        new_portion = UnifiedPortion(
            my_food_id=my_food.id,
            recipe_id=None,
            fdc_id=None,
            portion_description=form.portion_description.data,
            amount=form.amount.data,
            measure_unit_description=form.measure_unit_description.data,
            modifier=form.modifier.data,
            gram_weight=form.gram_weight.data,
        )
        db.session.add(new_portion)
        db.session.commit()
        flash('Portion added successfully!', 'success')
    else:
        flash('Error adding portion.', 'danger')
    return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))

@my_foods_bp.route('/portion/<int:portion_id>/update', methods=['POST'])
@login_required
def update_my_food_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or portion.my_food.user_id != current_user.id:
        flash('Portion not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('my_foods.my_foods'))

    form = PortionForm(request.form, obj=portion)
    if form.validate_on_submit():
        form.populate_obj(portion)
        db.session.commit()
        flash('Portion updated successfully!', 'success')
    else:
        current_app.logger.debug(f"PortionForm errors: {form.errors}")
        flash('Error updating portion.', 'danger')
    return redirect(url_for('my_foods.edit_my_food', food_id=portion.my_food_id))

@my_foods_bp.route('/portion/<int:portion_id>/delete', methods=['POST'])
@login_required
def delete_my_food_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if portion and portion.my_food and portion.my_food.user_id == current_user.id:
        food_id = portion.my_food_id
        db.session.delete(portion)
        db.session.commit()
        flash('Portion deleted.', 'success')
        return redirect(url_for('my_foods.edit_my_food', food_id=food_id))
    else:
        flash('Portion not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('my_foods.my_foods'))


@my_foods_bp.route('/copy_usda', methods=['POST'])
@login_required
def copy_usda_food():
    fdc_id = request.form.get('fdc_id')
    if not fdc_id:
        flash('No USDA Food ID provided for copying.', 'danger')
        return redirect(request.referrer or url_for('my_foods.my_foods'))

    usda_food = Food.query.options(
        joinedload(Food.nutrients).joinedload(FoodNutrient.nutrient)
    ).filter_by(fdc_id=fdc_id).first_or_404()

    new_food = MyFood(user_id=current_user.id, description=usda_food.description)
    # Populate nutrients from the USDA food
    for nutrient_link in usda_food.nutrients:
        nutrient_name = nutrient_link.nutrient.name.lower()
        # This is a simplified mapping. You might need a more robust one.
        if 'protein' in nutrient_name:
            new_food.protein_per_100g = nutrient_link.amount
        elif 'total lipid (fat)' in nutrient_name:
            new_food.fat_per_100g = nutrient_link.amount
        elif 'carbohydrate' in nutrient_name:
            new_food.carbs_per_100g = nutrient_link.amount
        elif 'energy' in nutrient_name and 'kcal' in nutrient_link.nutrient.unit_name.lower():
            new_food.calories_per_100g = nutrient_link.amount
    
    db.session.add(new_food)
    db.session.flush() # Flush to get the new_food.id

    # Deep copy portions from the original USDA food
    original_portions = UnifiedPortion.query.filter_by(fdc_id=usda_food.fdc_id).all()
    for orig_portion in original_portions:
        new_portion = UnifiedPortion(
            my_food_id=new_food.id,
            amount=orig_portion.amount,
            measure_unit_description=orig_portion.measure_unit_description,
            portion_description=orig_portion.portion_description,
            modifier=orig_portion.modifier,
            gram_weight=orig_portion.gram_weight
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(f"Successfully created '{new_food.description}' from USDA data.", "success")
    return redirect(url_for('my_foods.edit_my_food', food_id=new_food.id))


@my_foods_bp.route('/<int:food_id>/copy', methods=['POST'])
@login_required
def copy_my_food(food_id):
    # This route now exclusively handles copying an existing MyFood
    original_food = MyFood.query.options(joinedload(MyFood.portions)).get_or_404(food_id)
    friend_ids = [friend.id for friend in current_user.friends]
    if original_food.user_id not in friend_ids and original_food.user_id != current_user.id:
        flash("You can only copy foods from your friends or your own foods.", "danger")
        return redirect(request.referrer or url_for('my_foods.my_foods'))

    new_food = MyFood(
        user_id=current_user.id,
        description=original_food.description,
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
        vitamin_d_mcg_per_100g=original_food.vitamin_d_mcg_per_100g,
        calcium_mg_per_100g=original_food.calcium_mg_per_100g,
        iron_mg_per_100g=original_food.iron_mg_per_100g,
        potassium_mg_per_100g=original_food.potassium_mg_per_100g
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
            gram_weight=orig_portion.gram_weight
        )
        db.session.add(new_portion)

    db.session.commit()
    flash(f"Successfully copied '{original_food.description}' to your foods.", "success")
    return redirect(url_for('my_foods.my_foods'))



