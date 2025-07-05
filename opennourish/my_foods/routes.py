from flask import render_template, request, redirect, url_for, flash, Blueprint
from flask_login import login_required, current_user
from models import db, MyFood, Food, Nutrient, FoodNutrient, Portion, MyPortion
from opennourish.my_foods.forms import MyFoodForm, MyPortionForm
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
    else:
        flash('Please correct the errors below.', 'danger')
    return render_template('my_foods/new_my_food.html', form=form)

@my_foods_bp.route('/edit/<int:food_id>', methods=['GET', 'POST'])
@login_required
def edit_my_food(food_id):
    my_food = MyFood.query.filter_by(id=food_id, user_id=current_user.id).first_or_404()
    form = MyFoodForm(obj=my_food)
    portion_form = MyPortionForm()

    if form.validate_on_submit():
        form.populate_obj(my_food)
        db.session.commit()
        flash('Food updated successfully!', 'success')
        return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))
    
    return render_template('my_foods/edit_my_food.html', form=form, my_food=my_food, portion_form=portion_form)

@my_foods_bp.route('/delete/<int:food_id>', methods=['POST'])
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
    form = MyPortionForm()
    if form.validate_on_submit():
        new_portion = MyPortion(
            my_food_id=my_food.id,
            description=form.description.data,
            gram_weight=form.gram_weight.data
        )
        db.session.add(new_portion)
        db.session.commit()
        flash('Portion added successfully!', 'success')
    else:
        flash('Error adding portion.', 'danger')
    return redirect(url_for('my_foods.edit_my_food', food_id=my_food.id))

@my_foods_bp.route('/delete_portion/<int:portion_id>', methods=['POST'])
@login_required
def delete_my_food_portion(portion_id):
    portion = MyPortion.query.get_or_404(portion_id)
    if portion.my_food.user_id != current_user.id:
        flash('You are not authorized to delete this portion.', 'danger')
        return redirect(url_for('my_foods.my_foods'))
    
    food_id = portion.my_food_id
    db.session.delete(portion)
    db.session.commit()
    flash('Portion deleted.', 'success')
    return redirect(url_for('my_foods.edit_my_food', food_id=food_id))

@my_foods_bp.route('/copy_food/<int:fdc_id>')
@login_required
def copy_food(fdc_id):
    food_to_copy = db.session.get(Food, fdc_id)

    if food_to_copy:
        nutrient_ids = {
            'calories': 1008, 'protein': 1003, 'carbs': 1005, 'fat': 1004,
            'saturated_fat': 1258, 'trans_fat': 1257, 'cholesterol': 1253,
            'sodium': 1093, 'fiber': 1079, 'sugars': 2000, 'vitamin_d': 1110,
            'calcium': 1087, 'iron': 1089, 'potassium': 1092
        }
        nutrients = {}

        for name, nid in nutrient_ids.items():
            nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=fdc_id, nutrient_id=nid).first()
            nutrients[name] = nutrient.amount if nutrient else 0

        new_my_food = MyFood(
            user_id=current_user.id,
            description=food_to_copy.description,
            ingredients=food_to_copy.ingredients,
            calories_per_100g=nutrients.get('calories'),
            protein_per_100g=nutrients.get('protein'),
            carbs_per_100g=nutrients.get('carbs'),
            fat_per_100g=nutrients.get('fat'),
            saturated_fat_per_100g=nutrients.get('saturated_fat'),
            trans_fat_per_100g=nutrients.get('trans_fat'),
            cholesterol_mg_per_100g=nutrients.get('cholesterol'),
            sodium_mg_per_100g=nutrients.get('sodium'),
            fiber_per_100g=nutrients.get('fiber'),
            sugars_per_100g=nutrients.get('sugars'),
            vitamin_d_mcg_per_100g=nutrients.get('vitamin_d'),
            calcium_mg_per_100g=nutrients.get('calcium'),
            iron_mg_per_100g=nutrients.get('iron'),
            potassium_mg_per_100g=nutrients.get('potassium')
        )
        db.session.add(new_my_food)
        db.session.commit()

        for portion in food_to_copy.portions:
            new_portion = MyPortion(
                my_food_id=new_my_food.id,
                description=portion.portion_description,
                gram_weight=portion.gram_weight
            )
            db.session.add(new_portion)
        db.session.commit()

        flash(f'{food_to_copy.description} has been added to your foods.', 'success')
    else:
        flash('Food not found.', 'danger')

    return redirect(url_for('my_foods.my_foods'))

