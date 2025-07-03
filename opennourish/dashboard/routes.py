from flask import render_template
from flask_login import login_required, current_user
from . import dashboard_bp
from models import db, DailyLog, Food, MyFood, UserGoal, FoodNutrient, CheckIn
from datetime import date

@dashboard_bp.route('/')
@login_required
def index():
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    if not user_goal:
        # Create a temporary default goal if none exists
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(user_id=current_user.id, log_date=date.today()).all()
    
    totals = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0}
    
    # Nutrient IDs for USDA data
    NUTRIENT_IDS = {
        'calories': 1008, # Energy (kcal)
        'protein': 1003,  # Protein
        'carbs': 1005,    # Carbohydrate, by difference
        'fat': 1004       # Total lipid (fat)
    }

    for log in daily_logs:
        scaling_factor = log.amount_grams / 100.0
        if log.fdc_id:
            # USDA food
            for name, nid in NUTRIENT_IDS.items():
                nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=log.fdc_id, nutrient_id=nid).first()
                if nutrient:
                    totals[name] += nutrient.amount * scaling_factor
        elif log.my_food_id:
            # Custom food
            my_food = db.session.get(MyFood, log.my_food_id)
            if my_food:
                totals['calories'] += my_food.calories_per_100g * scaling_factor
                totals['protein'] += my_food.protein_per_100g * scaling_factor
                totals['carbs'] += my_food.carbs_per_100g * scaling_factor
                totals['fat'] += my_food.fat_per_100g * scaling_factor

    remaining = {
        'calories': user_goal.calories - totals['calories'],
        'protein': user_goal.protein - totals['protein'],
        'carbs': user_goal.carbs - totals['carbs'],
        'fat': user_goal.fat - totals['fat']
    }

    food_names = {}
    for log in daily_logs:
        if log.fdc_id:
            food = db.session.get(Food, log.fdc_id)
            if food:
                food_names[log.id] = food.description
        elif log.my_food_id:
            my_food = db.session.get(MyFood, log.my_food_id)
            if my_food:
                food_names[log.id] = my_food.description

    check_ins = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.asc()).limit(30).all()
    chart_labels = [check_in.checkin_date.strftime('%Y-%m-%d') for check_in in check_ins]
    weight_data = [check_in.weight_kg for check_in in check_ins]
    body_fat_data = [check_in.body_fat_percentage for check_in in check_ins]
    waist_data = [check_in.waist_cm for check_in in check_ins]

    return render_template('dashboard.html', daily_logs=daily_logs, food_names=food_names, goals=user_goal, totals=totals, remaining=remaining, chart_labels=chart_labels, weight_data=weight_data, body_fat_data=body_fat_data, waist_data=waist_data)