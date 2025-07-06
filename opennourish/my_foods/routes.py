from flask import render_template, request, redirect, url_for, flash, Blueprint, current_app
from flask_login import login_required, current_user
from models import db, MyFood, Food, Nutrient, FoodNutrient, UnifiedPortion
from opennourish.my_foods.forms import MyFoodForm, PortionForm
from sqlalchemy.orm import joinedload

my_foods_bp = Blueprint('my_foods', __name__, template_folder='templates')

@my_foods_bp.route('/')
@login_required
def my_foods():
    user_my_foods = MyFood.query.filter_by(user_id=current_user.id).all()
    return render_template('my_foods/my_foods.html', my_foods=user_my_foods)

@my_foods_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_my_food():
    form = MyFoodForm()
    if form.validate_on_submit():
        my_food = MyFood(
            user_id=current_user.id,
            description=form.description.data,
            ingredients=form.ingredients.data,
            calories_per_100g=form.calories_per_100g.data,
            protein_per_100g=form.protein_per_100g.data,
            carbs_per_100g=form.carbs_per_100g.data,
            fat_per_100g=form.fat_per_100g.data,
            saturated_fat_per_100g=form.saturated_fat_per_100g.data,
            trans_fat_per_100g=form.trans_fat_per_100g.data,
            cholesterol_mg_per_100g=form.cholesterol_mg_per_100g.data,
            sodium_mg_per_100g=form.sodium_mg_per_100g.data,
            fiber_per_100g=form.fiber_per_100g.data,
            sugars_per_100g=form.sugars_per_100g.data,
            vitamin_d_mcg_per_100g=form.vitamin_d_mcg_per_100g.data,
            calcium_mg_per_100g=form.calcium_mg_per_100g.data,
            iron_mg_per_100g=form.iron_mg_per_100g.data,
            potassium_mg_per_100g=form.potassium_mg_per_100g.data
        )
        db.session.add(my_food)
        db.session.commit()
        flash('Custom food added successfully!', 'success')
        return redirect(url_for('my_foods.my_foods'))
    return render_template('my_foods/new_my_food.html', form=form)

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
        new_portion.full_description = new_portion.full_description_str
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
        portion.full_description = portion.full_description_str
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



