from flask import render_template, request
from flask_login import login_required, current_user
from . import dashboard_bp
from models import db, DailyLog, Food, MyFood, UserGoal, CheckIn, ExerciseLog, FastingSession
from datetime import date, timedelta, datetime
from opennourish.utils import calculate_nutrition_for_items, calculate_weekly_nutrition_summary, calculate_weight_projection
from opennourish.time_utils import get_user_today, get_start_of_week
from sqlalchemy import func
from opennourish.decorators import onboarding_required

@dashboard_bp.route('/')
@dashboard_bp.route('/<string:log_date_str>')
@login_required
@onboarding_required
def index(log_date_str=None):
    time_range = request.args.get('time_range', '3_month') # Default to 3 months

    if log_date_str:
        date_obj = date.fromisoformat(log_date_str)
    else:
        date_obj = get_user_today()

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
        'calories': (user_goal.calories or 0) - totals['calories'] + calories_burned,
        'protein': (user_goal.protein or 0) - totals['protein'],
        'carbs': (user_goal.carbs or 0) - totals['carbs'],
        'fat': (user_goal.fat or 0) - totals['fat']
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
        start_date = date_obj - timedelta(days=30)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '3_month':
        start_date = date_obj - timedelta(days=90)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '6_month':
        start_date = date_obj - timedelta(days=180)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == '1_year':
        start_date = date_obj - timedelta(days=365)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    # 'all_time' doesn't need a filter

    check_ins = check_ins_query.order_by(CheckIn.checkin_date.asc()).all()

    chart_labels = [check_in.checkin_date.strftime('%Y-%m-%d') for check_in in check_ins]
    weight_data = [check_in.weight_kg for check_in in check_ins]
    body_fat_data = [check_in.body_fat_percentage for check_in in check_ins]
    waist_data = [check_in.waist_cm for check_in in check_ins]

    # --- Weekly Goal Progress ---
    # Calculate start and end of the week based on the currently viewed date (date_obj)
    start_of_week = get_start_of_week(date_obj, current_user.week_start_day)
    end_of_week = start_of_week + timedelta(days=6)
    days_elapsed_in_week = (date_obj - start_of_week).days + 1

    weekly_exercise_logs = ExerciseLog.query.filter(
        ExerciseLog.user_id == current_user.id,
        ExerciseLog.log_date >= start_of_week,
        ExerciseLog.log_date <= end_of_week
    ).all()

    weekly_progress = {
        'calories_burned': sum(log.calories_burned for log in weekly_exercise_logs),
        'exercises': len(weekly_exercise_logs),
        'minutes': sum(log.duration_minutes for log in weekly_exercise_logs)
    }

    weekly_diet_logs = DailyLog.query.filter(
        DailyLog.user_id == current_user.id,
        DailyLog.log_date >= start_of_week,
        DailyLog.log_date <= end_of_week
    ).all()

    weekly_totals = calculate_nutrition_for_items(weekly_diet_logs)
    weekly_goals = {
        'calories': (user_goal.calories or 0) * 7,
        'protein': (user_goal.protein or 0) * 7,
        'carbs': (user_goal.carbs or 0) * 7,
        'fat': (user_goal.fat or 0) * 7
    }

    # --- Weight Goal Projection ---
    projected_dates, projected_weights, trending_away, at_goal_and_maintaining = calculate_weight_projection(current_user)
    days_to_goal = None
    goal_date_str = None
    if projected_dates and not trending_away and not at_goal_and_maintaining:
        days_to_goal = len(projected_dates) - 1
        goal_date = date.fromisoformat(projected_dates[-1])
        goal_date_str = goal_date.strftime('%B %d, %Y')
    
    # --- Fasting Status ---
    active_fast = FastingSession.query.filter_by(user_id=current_user.id, status='active').first()
    last_completed_fast = FastingSession.query.filter_by(user_id=current_user.id, status='completed').order_by(FastingSession.end_time.desc()).first()

    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()


    return render_template('dashboard.html', date=date_obj, prev_date=prev_date, next_date=next_date, 
                           daily_logs=daily_logs, food_names=food_names, goals=user_goal, totals=totals, 
                           remaining=remaining, calories_burned=calories_burned, chart_labels=chart_labels, 
                           weight_data=weight_data, body_fat_data=body_fat_data, waist_data=waist_data, 
                           time_range=time_range, weekly_progress=weekly_progress, exercise_logs=exercise_logs, 
                           start_of_week=start_of_week, end_of_week=end_of_week, 
                           pending_received=current_user.pending_requests_received, 
                           current_user_measurement_system=current_user.measurement_system, 
                           weekly_totals=weekly_totals, weekly_goals=weekly_goals, 
                           days_elapsed_in_week=days_elapsed_in_week,
                           projected_dates=projected_dates, projected_weights=projected_weights,
                           trending_away=trending_away, days_to_goal=days_to_goal, goal_date_str=goal_date_str,
                           at_goal_and_maintaining=at_goal_and_maintaining,
                           active_fast=active_fast, last_completed_fast=last_completed_fast, now=datetime.utcnow(), latest_checkin=latest_checkin)