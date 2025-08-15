from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from . import profile_bp
from models import (
    db,
    User,
    Friendship,
    DailyLog,
    Food,
    MyFood,
    UserGoal,
    CheckIn,
    ExerciseLog,
    Recipe,
    UnifiedPortion,
)
from datetime import date, timedelta
from opennourish.time_utils import get_user_today
from opennourish.utils import (
    calculate_nutrition_for_items,
    get_standard_meal_names_for_user,
)
from constants import ALL_MEAL_TYPES


def _get_friend_user_or_404(username):
    friend_user = User.query.filter_by(username=username).first_or_404()

    if friend_user.id == current_user.id:
        # Allow viewing own profile, but not as a "friend"
        return friend_user

    # Check if current_user is friends with friend_user
    is_friend = Friendship.query.filter(
        (
            (Friendship.requester_id == current_user.id)
            & (Friendship.receiver_id == friend_user.id)
            & (Friendship.status == "accepted")
        )
        | (
            (Friendship.requester_id == friend_user.id)
            & (Friendship.receiver_id == current_user.id)
            & (Friendship.status == "accepted")
        )
    ).first()

    if not is_friend:
        flash(f"You are not friends with {username}.", "danger")
        return None

    return friend_user


@profile_bp.route("/<username>/dashboard")
@profile_bp.route("/<username>/dashboard/<string:log_date_str>")
@login_required
def dashboard(username, log_date_str=None):
    friend_user = _get_friend_user_or_404(username)
    if friend_user is None:
        return redirect(url_for("friends.friends_page"))

    time_range = request.args.get("time_range", "3_month")  # Default to 3 months

    if log_date_str:
        date_obj = date.fromisoformat(log_date_str)
    else:
        date_obj = get_user_today(current_user.timezone)

    prev_date = date_obj - timedelta(days=1)
    next_date = date_obj + timedelta(days=1)

    user_goal = UserGoal.query.filter_by(user_id=friend_user.id).first()
    if not user_goal:
        # Create a temporary default goal if none exists
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(
        user_id=friend_user.id, log_date=date_obj
    ).all()

    totals = calculate_nutrition_for_items(daily_logs)

    exercise_logs = ExerciseLog.query.filter_by(
        user_id=friend_user.id, log_date=date_obj
    ).all()
    calories_burned = sum(log.calories_burned for log in exercise_logs)

    remaining = {
        "calories": user_goal.calories - totals["calories"] + calories_burned,
        "protein": user_goal.protein - totals["protein"],
        "carbs": user_goal.carbs - totals["carbs"],
        "fat": user_goal.fat - totals["fat"],
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
    check_ins_query = CheckIn.query.filter_by(user_id=friend_user.id)

    if time_range == "1_month":
        start_date = get_user_today(current_user.timezone) - timedelta(days=30)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == "3_month":
        start_date = get_user_today(current_user.timezone) - timedelta(days=90)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == "6_month":
        start_date = get_user_today(current_user.timezone) - timedelta(days=180)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    elif time_range == "1_year":
        start_date = get_user_today(current_user.timezone) - timedelta(days=365)
        check_ins_query = check_ins_query.filter(CheckIn.checkin_date >= start_date)
    # 'all_time' doesn't need a filter

    check_ins = check_ins_query.order_by(CheckIn.checkin_date.asc()).all()

    chart_labels = [
        check_in.checkin_date.strftime("%Y-%m-%d") for check_in in check_ins
    ]
    weight_data = [check_in.weight_kg for check_in in check_ins]
    body_fat_data = [check_in.body_fat_percentage for check_in in check_ins]
    waist_data = [check_in.waist_cm for check_in in check_ins]

    # --- Weekly Goal Progress ---
    # Calculate start and end of the week based on the currently viewed date (date_obj)
    start_of_week = date_obj - timedelta(days=date_obj.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    days_elapsed_in_week = date_obj.weekday() + 1

    weekly_logs = ExerciseLog.query.filter(
        ExerciseLog.user_id == friend_user.id,
        ExerciseLog.log_date >= start_of_week,
        ExerciseLog.log_date <= end_of_week,
    ).all()

    weekly_progress = {
        "calories_burned": sum(log.calories_burned for log in weekly_logs),
        "exercises": len(weekly_logs),
        "minutes": sum(log.duration_minutes for log in weekly_logs),
    }

    weekly_diet_logs = DailyLog.query.filter(
        DailyLog.user_id == friend_user.id,
        DailyLog.log_date >= start_of_week,
        DailyLog.log_date <= end_of_week,
    ).all()

    weekly_totals = calculate_nutrition_for_items(weekly_diet_logs)
    weekly_goals = {
        "calories": user_goal.calories * 7,
        "protein": user_goal.protein * 7,
        "carbs": user_goal.carbs * 7,
        "fat": user_goal.fat * 7,
    }

    return render_template(
        "dashboard.html",
        date=date_obj,
        prev_date=prev_date,
        next_date=next_date,
        daily_logs=daily_logs,
        food_names=food_names,
        goals=user_goal,
        totals=totals,
        remaining=remaining,
        calories_burned=calories_burned,
        chart_labels=chart_labels,
        weight_data=weight_data,
        body_fat_data=body_fat_data,
        waist_data=waist_data,
        time_range=time_range,
        weekly_progress=weekly_progress,
        exercise_logs=exercise_logs,
        start_of_week=start_of_week,
        end_of_week=end_of_week,
        is_read_only=True,
        username=username,
        weekly_totals=weekly_totals,
        weekly_goals=weekly_goals,
        days_elapsed_in_week=days_elapsed_in_week,
        current_user_measurement_system=getattr(current_user, "measurement_system", ""),
    )


@profile_bp.route("/<username>/diary")
@profile_bp.route("/<username>/diary/<string:log_date_str>")
@login_required
def diary(username, log_date_str=None):
    friend_user = _get_friend_user_or_404(username)
    if friend_user is None:
        return redirect(url_for("friends.friends_page"))

    if log_date_str:
        log_date = date.fromisoformat(log_date_str)
    else:
        log_date = get_user_today(current_user.timezone)

    user_goal = db.session.get(UserGoal, friend_user.id)
    if not user_goal:
        user_goal = UserGoal(calories=2000, protein=150, carbs=250, fat=60)

    daily_logs = DailyLog.query.filter_by(
        user_id=friend_user.id, log_date=log_date
    ).all()

    exercise_logs = ExerciseLog.query.filter_by(
        user_id=friend_user.id, log_date=log_date
    ).all()
    calories_burned = sum(log.calories_burned for log in exercise_logs)

    meals = {
        "Breakfast": [],
        "Snack (morning)": [],
        "Lunch": [],
        "Snack (afternoon)": [],
        "Dinner": [],
        "Snack (evening)": [],
        "Unspecified": [],
    }

    meal_totals = {
        meal_name: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}
        for meal_name in meals
    }

    totals = calculate_nutrition_for_items(daily_logs)

    for log in daily_logs:
        food_item = None
        description_to_display = "Unknown Food"
        display_amount = log.amount_grams  # Initialize with default
        selected_portion_id = None  # Initialize with default
        nutrition = calculate_nutrition_for_items([log])  # Initialize with default
        available_portions = []  # Initialize with default

        if log.fdc_id:
            food_item = db.session.get(Food, log.fdc_id)
        elif log.my_food_id:
            food_item = db.session.get(MyFood, log.my_food_id)
        elif log.recipe_id:
            food_item = db.session.get(Recipe, log.recipe_id)

        if food_item:
            # available_portions = [] # No portions in read-only mode

            display_amount = log.amount_grams
            selected_portion_id = "g"  # Default to grams

            if log.portion_id_fk:
                selected_portion = db.session.get(UnifiedPortion, log.portion_id_fk)
                if selected_portion and selected_portion.gram_weight > 0:
                    display_amount = log.amount_grams / selected_portion.gram_weight
                    selected_portion_id = selected_portion.id

            nutrition = calculate_nutrition_for_items([log])
            description_to_display = (
                food_item.description
                if hasattr(food_item, "description")
                else food_item.name
            )

        # Assign to the correct meal category, defaulting to 'Unspecified'
        meal_key = log.meal_name or "Unspecified"
        if meal_key not in meals:
            meals[meal_key] = []
        if meal_key not in meal_totals:
            meal_totals[meal_key] = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

        # Add nutrition to the meal's total
        meal_totals[meal_key]["calories"] += nutrition["calories"]
        meal_totals[meal_key]["protein"] += nutrition["protein"]
        meal_totals[meal_key]["carbs"] += nutrition["carbs"]
        meal_totals[meal_key]["fat"] += nutrition["fat"]
        meal_totals[meal_key]["fiber"] += nutrition["fiber"]

        meals[meal_key].append(
            {
                "log_id": log.id,
                "description": description_to_display,
                "amount": display_amount,
                "nutrition": nutrition,
                "portions": available_portions,
                "serving_type": log.serving_type,
                "selected_portion_id": selected_portion_id,
            }
        )

    # current_app.logger.debug(f"Friend's meals dictionary: {meals}")

    prev_date = log_date - timedelta(days=1)
    next_date = log_date + timedelta(days=1)

    # Determine the base meal names to always display based on user settings
    base_meals_to_show = get_standard_meal_names_for_user(friend_user)

    # Collect all meal names that actually have items logged for the day
    logged_meal_names = {meal_name for meal_name, items in meals.items() if items}

    # Combine base meals with any other meals that have logged items
    meal_names_to_render = sorted(
        list(set(base_meals_to_show) | logged_meal_names), key=ALL_MEAL_TYPES.index
    )

    # Calculate total water intake in grams
    water_total_grams = sum(
        log.amount_grams for log in daily_logs if log.meal_name == "Water"
    )

    return render_template(
        "diary/diary.html",
        date=log_date,
        meals=meals,
        totals=totals,
        prev_date=prev_date,
        next_date=next_date,
        goals=user_goal,
        calories_burned=calories_burned,
        is_read_only=True,
        username=username,
        meal_names_to_render=meal_names_to_render,
        user=friend_user,
        meal_totals=meal_totals,
        water_total_grams=water_total_grams,
    )
