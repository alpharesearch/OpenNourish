from flask import render_template
from flask_login import login_required, current_user
from . import dashboard_bp
from models import db, DailyLog, Food, MyFood, UserGoal, CheckIn, ExerciseLog
from datetime import date, timedelta
from flask import render_template, request
from flask_login import login_required, current_user
from . import dashboard_bp
from models import db, DailyLog, Food, MyFood, UserGoal, CheckIn, ExerciseLog
from opennourish.utils import calculate_nutrition_for_items

@dashboard_bp.route('/')
@dashboard_bp.route('/<string:log_date_str>')
@login_required
def index(log_date_str=None):
    time_range = request.args.get('time_range', '3_month') # Default to 3 months

    if log_date_str:
        date_obj = date.fromisoformat(log_date_str)
    else:
        date_obj = date.today()

    prev_date = date_obj - timedelta(days=1)
    next_date = date_obj + timedelta(days=1)

    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    if not user_goal:
        # Create a temporary default goal if none exists
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(user_id=current_user.id, log_date=date_obj).all()
    
    totals = calculate_nutrition_for_items(daily_logs)

    exercise_logs = ExerciseLog.query.filter_by(user_id=current_user.id, log_date=date_obj).all()
    calories_burned = sum(log.calories_burned for log in exercise_logs)

    remaining = {
        'calories': user_goal.calories - totals['calories'] + calories_burned,
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

    # Filter check-ins based on time_range
    check_ins_query = CheckIn.query.filter_by(user_id=current_user.id)

    if time_range == '1_month':
        start_date = date.today() - timedelta(days=30)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '3_month':
        start_date = date.today() - timedelta(days=90)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '6_month':
        start_date = date.today() - timedelta(days=180)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '1_year':
        start_date = date.today() - timedelta(days=365)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    # 'all_time' doesn't need a filter

    check_ins = check_ins_query.order_by(CheckIn.checkin_date.asc()).all()

    chart_labels = [check_in.checkin_date.strftime('%Y-%m-%d') for check_in in check_ins]
    weight_data = [check_in.weight_kg for check_in in check_ins]
    body_fat_data = [check_in.body_fat_percentage for check_in in check_ins]
    waist_data = [check_in.waist_cm for check_in in check_ins]

    # --- Weekly Exercise Goal Progress ---
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    weekly_logs = ExerciseLog.query.filter(
        ExerciseLog.user_id == current_user.id,
        ExerciseLog.log_date >= start_of_week,
        ExerciseLog.log_date <= end_of_week
    ).all()

    weekly_progress = {
        'calories_burned': sum(log.calories_burned for log in weekly_logs),
        'exercises': len(weekly_logs),
        'minutes': sum(log.duration_minutes for log in weekly_logs)
    }

    return render_template('dashboard.html', date=date_obj, prev_date=prev_date, next_date=next_date, daily_logs=daily_logs, food_names=food_names, goals=user_goal, totals=totals, remaining=remaining, calories_burned=calories_burned, chart_labels=chart_labels, weight_data=weight_data, body_fat_data=body_fat_data, waist_data=waist_data, time_range=time_range, weekly_progress=weekly_progress, exercise_logs=exercise_logs)