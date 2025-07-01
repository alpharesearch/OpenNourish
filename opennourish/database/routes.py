from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy import case
from . import database_bp
from models import db, Food, MyFood, FoodNutrient, Nutrient

from sqlalchemy import case

@database_bp.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    search_term = request.form.get('search_term') or request.args.get('search_term')
    page = request.args.get('page', 1, type=int)
    foods = None

    if search_term and search_term.strip():
        term = search_term.strip()
        search_query = f"%{term}%"
        
        # Prioritize results where the description starts with the search term
        order_logic = case(
            (Food.description.ilike(f"{term},%"), 0),
            else_=1
        )

        foods = db.session.query(Food).filter(
            Food.description.ilike(search_query)
        ).order_by(order_logic, Food.description).paginate(page=page, per_page=20)

    return render_template('database/search.html', foods=foods, search_term=search_term)

@database_bp.route('/my_foods', methods=['GET', 'POST'])
@login_required
def my_foods():
    if request.method == 'POST':
        description = request.form.get('description')
        calories = request.form.get('calories', type=float)
        protein = request.form.get('protein', type=float)
        carbs = request.form.get('carbs', type=float)
        fat = request.form.get('fat', type=float)

        if description and calories and protein and carbs and fat:
            new_food = MyFood(
                user_id=current_user.id,
                description=description,
                calories_per_100g=calories,
                protein_per_100g=protein,
                carbs_per_100g=carbs,
                fat_per_100g=fat
            )
            db.session.add(new_food)
            db.session.commit()
            flash('Custom food added successfully!', 'success')
        else:
            flash('Please fill out all fields.', 'danger')
        
        return redirect(url_for('database.my_foods'))

    my_foods = MyFood.query.filter_by(user_id=current_user.id).all()
    return render_template('database/my_foods.html', my_foods=my_foods)

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
