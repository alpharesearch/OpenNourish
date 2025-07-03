from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy import case, func
from . import database_bp
from models import db, Food, MyFood, FoodNutrient, Nutrient, Portion
from .forms import MyFoodForm

@database_bp.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    q = request.args.get('q')
    page = request.args.get('page', 1, type=int)
    foods = None

    if q and q.strip():
        term = q.strip()
        
        foods = db.session.query(Food).filter(
            Food.description.ilike(f'%{term}%')
        ).outerjoin(Portion).outerjoin(FoodNutrient).group_by(Food.fdc_id).order_by(
            db.func.count(Portion.id).desc(),
            db.func.count(FoodNutrient.nutrient_id).desc(),
            case(
                (Food.description.ilike(term), 0),
                (Food.description.ilike(f'{term}%'), 1),
                else_=2
            )
        ).paginate(page=page, per_page=20)

    return render_template('database/search.html', foods=foods, search_term=q)

@database_bp.route('/my_foods', methods=['GET', 'POST'])
@login_required
def my_foods():
    form = MyFoodForm()
    if form.validate_on_submit():
        new_food = MyFood(
            user_id=current_user.id,
            description=form.description.data,
            calories_per_100g=form.calories.data,
            protein_per_100g=form.protein.data,
            carbs_per_100g=form.carbs.data,
            fat_per_100g=form.fat.data
        )
        db.session.add(new_food)
        db.session.commit()
        flash('Custom food added successfully!', 'success')
        return redirect(url_for('database.my_foods'))

    my_foods = MyFood.query.filter_by(user_id=current_user.id).all()
    return render_template('database/my_foods.html', my_foods=my_foods, form=form)

@database_bp.route('/copy_food/<int:fdc_id>')
@login_required
def copy_food(fdc_id):
    food_to_copy = db.session.get(Food, fdc_id)

    if food_to_copy:
        # Nutrient IDs for Calories, Protein, Fat, Carbohydrates
        nutrient_ids = {'calories': 1008, 'protein': 1003, 'carbs': 1005, 'fat': 1004}
        nutrients = {}

        for name, nid in nutrient_ids.items():
            nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=fdc_id, nutrient_id=nid).first()
            nutrients[name] = nutrient.amount if nutrient else 0

        new_my_food = MyFood(
            user_id=current_user.id,
            description=food_to_copy.description,
            calories_per_100g=nutrients.get('calories'),
            protein_per_100g=nutrients.get('protein'),
            carbs_per_100g=nutrients.get('carbs'),
            fat_per_100g=nutrients.get('fat')
        )
        db.session.add(new_my_food)
        db.session.commit()
        flash(f'{food_to_copy.description} has been added to your foods.', 'success')
    else:
        flash('Food not found.', 'danger')

    return redirect(url_for('database.my_foods'))

@database_bp.route('/my_foods/edit/<int:food_id>', methods=['GET', 'POST'])
@login_required
def edit_my_food(food_id):
    food = db.session.get(MyFood, food_id)
    if not food or food.user_id != current_user.id:
        flash('Food not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('database.my_foods'))

    form = MyFoodForm(obj=food)
    if form.validate_on_submit():
        form.populate_obj(food)
        db.session.commit()
        flash('Food updated successfully!', 'success')
        return redirect(url_for('database.my_foods'))

    return render_template('database/edit_my_food.html', food=food, form=form)

@database_bp.route('/my_foods/delete/<int:food_id>', methods=['POST'])
@login_required
def delete_my_food(food_id):
    food = db.session.get(MyFood, food_id)
    if not food or food.user_id != current_user.id:
        flash('Food not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('database.my_foods'))

    db.session.delete(food)
    db.session.commit()
    flash('Food deleted successfully!', 'success')
    return redirect(url_for('database.my_foods'))
