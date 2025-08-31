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
    calculate_nutrient_density,
    get_meal_based_nutrition,
    calculate_intake_vs_goal_deviation,
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

    # --- Enhanced Analytics (for friend's view) ---
    nutrient_density = calculate_nutrient_density(daily_logs)
    meal_nutrition = get_meal_based_nutrition(daily_logs)
    deviation_metrics = calculate_intake_vs_goal_deviation(user_goal, daily_logs)
    latest_checkin = (
        CheckIn.query.filter_by(user_id=friend_user.id)
        .order_by(CheckIn.checkin_date.desc())
        .first()
    )

    # --- Scaled Daily Values ---
    fda_standard_dvs = {
        "saturated_fat": 20,  # g
        "cholesterol": 300,  # mg
        "sodium": 2300,  # mg
        "fiber": 28,  # g
        "sugars": 90,  # g
        "added_sugars": 50,  # g
        "vitamin_d": 20,  # mcg
        "calcium": 1300,  # mg
        "iron": 18,  # mg
        "potassium": 4700,  # mg
    }
    scaling_factor = (user_goal.calories or 2000) / 2000
    scaled_daily_values = {
        key: value * scaling_factor for key, value in fda_standard_dvs.items()
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
        # Pass empty analytics data for now to prevent crashes
        nutrient_density=nutrient_density,
        meal_nutrition=meal_nutrition,
        deviation_metrics=deviation_metrics,
        latest_checkin=latest_checkin,
        scaled_daily_values=scaled_daily_values,
        # Friends cannot see each other's projections or fasting
        projected_dates=[],
        projected_weights=[],
        trending_away=False,
        days_to_goal=None,
        goal_date_str=None,
        at_goal_and_maintaining=False,
        active_fast=None,
        last_completed_fast=None,
        now=None,
        pending_received=current_user.pending_requests_received,
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
        display_amount = log.amount_grams
        selected_portion = None
        nutrition = calculate_nutrition_for_items([log])
        available_portions = []
        total_gram_weight = log.amount_grams

        if log.fdc_id:
            food_item = db.session.get(Food, log.fdc_id)
        elif log.my_food_id:
            food_item = db.session.get(MyFood, log.my_food_id)
        elif log.recipe_id:
            food_item = db.session.get(Recipe, log.recipe_id)

        if food_item:
            if log.portion_id_fk:
                portion = db.session.get(UnifiedPortion, log.portion_id_fk)
                if portion and portion.gram_weight > 0:
                    display_amount = log.amount_grams / portion.gram_weight
                    selected_portion = portion

            nutrition = calculate_nutrition_for_items([log])
            description_to_display = (
                food_item.description
                if hasattr(food_item, "description")
                else food_item.name
            )

        meal_key = log.meal_name or "Unspecified"
        if meal_key not in meals:
            meals[meal_key] = []
        if meal_key not in meal_totals:
            meal_totals[meal_key] = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

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
                "selected_portion": selected_portion,
                "total_gram_weight": total_gram_weight,
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


@profile_bp.route("/<username>/copy_log", methods=["POST"])
@login_required
def copy_log_from_friend(username):
    friend_user = _get_friend_user_or_404(username)
    if friend_user is None:
        flash(
            "Friend not found or you do not have permission to view their diary.",
            "danger",
        )
        return redirect(url_for("friends.friends_page"))

    log_id = request.form.get("log_id")
    target_date_str = request.form.get("target_date")
    target_meal_name = request.form.get("target_meal_name")

    log_entry_to_copy = db.session.get(DailyLog, log_id)

    if not log_entry_to_copy or log_entry_to_copy.user_id != friend_user.id:
        flash(
            "Diary entry not found or it does not belong to the specified user.",
            "danger",
        )
        return redirect(url_for("profile.diary", username=username))

    try:
        target_date = date.fromisoformat(target_date_str)

        new_log_entry = DailyLog(
            user_id=current_user.id,
            log_date=target_date,
            meal_name=target_meal_name,
            fdc_id=log_entry_to_copy.fdc_id,
            my_food_id=log_entry_to_copy.my_food_id,
            recipe_id=log_entry_to_copy.recipe_id,
            amount_grams=log_entry_to_copy.amount_grams,
            serving_type=log_entry_to_copy.serving_type,
            portion_id_fk=log_entry_to_copy.portion_id_fk,
        )
        db.session.add(new_log_entry)
        db.session.commit()
        flash(f"Successfully copied item from {username}'s diary.", "success")
        anchor = f"meal-{target_meal_name.lower().replace(' ', '-')}"
        return redirect(
            url_for("diary.diary", log_date_str=target_date_str, _anchor=anchor)
        )
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while copying the entry: {e}", "danger")
        return redirect(
            url_for(
                "profile.diary",
                username=username,
                log_date_str=log_entry_to_copy.log_date.isoformat(),
            )
        )
