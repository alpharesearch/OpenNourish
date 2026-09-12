"""
Advanced analytics module for OpenNourish.
Provides functions to calculate and format data for various analytics visualizations.
"""

from datetime import date, timedelta
from collections import defaultdict
from models import (
    db,
    DailyLog,
    ExerciseLog,
    CheckIn,
    UserGoal,
    MyFood,
)
from opennourish.utils import (
    calculate_nutrition_for_items,
    get_meal_based_nutrition,
    calculate_intake_vs_goal_deviation,
    calculate_weekly_nutrition_summary,
)


def get_daily_nutrition_data(user_id, days=30):
    """
    Get daily nutrition data for the specified number of days.
    Returns a list of dictionaries with date and nutrition values.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    logs = (
        DailyLog.query.filter(
            DailyLog.user_id == user_id,
            DailyLog.log_date >= start_date,
            DailyLog.log_date <= end_date,
        )
        .order_by(DailyLog.log_date.asc())
        .all()
    )

    # Group by date
    daily_data = defaultdict(
        lambda: {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "date": None}
    )

    for log in logs:
        if log.log_date not in daily_data:
            daily_data[log.log_date] = {
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
                "date": log.log_date,
            }

    # Calculate nutrition for each day's logs
    logs_by_date = defaultdict(list)
    for log in logs:
        logs_by_date[log.log_date].append(log)

    for date_key, logs_list in logs_by_date.items():
        if logs_list:
            totals = calculate_nutrition_for_items(logs_list)
            daily_data[date_key]["calories"] = round(totals["calories"], 1)
            daily_data[date_key]["protein"] = round(totals["protein"], 1)
            daily_data[date_key]["carbs"] = round(totals["carbs"], 1)
            daily_data[date_key]["fat"] = round(totals["fat"], 1)

    # Convert to sorted list
    result = sorted(daily_data.values(), key=lambda x: x["date"])
    return result


def get_macro_distribution_by_meal(user_id, days=7):
    """
    Get macro distribution data grouped by meal type.
    Returns data for pie charts showing macro composition per meal.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    logs = DailyLog.query.filter(
        DailyLog.user_id == user_id,
        DailyLog.log_date >= start_date,
        DailyLog.log_date <= end_date,
    ).all()

    meal_nutrition = get_meal_based_nutrition(logs)

    # Calculate percentages for each macro by meal
    result = {}
    for meal_name, nutrition in meal_nutrition.items():
        total_calories = nutrition["calories"]
        if total_calories > 0:
            protein_pct = (nutrition["protein"] * 4) / total_calories * 100
            carbs_pct = (nutrition["carbs"] * 4) / total_calories * 100
            fat_pct = (nutrition["fat"] * 9) / total_calories * 100

            result[meal_name] = {
                "protein": round(protein_pct, 1),
                "carbs": round(carbs_pct, 1),
                "fat": round(fat_pct, 1),
                "total_calories": nutrition["calories"],
            }

    return result


def get_weekly_trends(user_id):
    """
    Get weekly trends for macros and calories.
    Returns data suitable for line charts showing progress over weeks.
    """
    today = date.today()
    one_year_ago = today - timedelta(days=365)

    logs = (
        DailyLog.query.filter(
            DailyLog.user_id == user_id, DailyLog.log_date >= one_year_ago
        )
        .order_by(DailyLog.log_date.asc())
        .all()
    )

    # Group by week (starting Monday)
    weekly_data = defaultdict(
        lambda: {
            "calories": [],
            "protein": [],
            "carbs": [],
            "fat": [],
            "week_start": None,
            "week_end": None,
        }
    )

    for log in logs:
        # Calculate week start (Monday)
        year, week, _ = log.log_date.isocalendar()
        week_start = date.fromisocalendar(year, week, 1)

        if week_start not in weekly_data:
            week_end = week_start + timedelta(days=6)
            weekly_data[week_start] = {
                "calories": [],
                "protein": [],
                "carbs": [],
                "fat": [],
                "week_start": week_start,
                "week_end": week_end,
            }

    # Group logs by week and calculate averages
    logs_by_week = defaultdict(list)
    for log in logs:
        year, week, _ = log.log_date.isocalendar()
        week_start = date.fromisocalendar(year, week, 1)
        logs_by_week[week_start].append(log)

    for week_start, logs_list in sorted(logs_by_week.items()):
        if logs_list:
            summary = calculate_weekly_nutrition_summary(logs_list)
            weekly_data[week_start]["calories"] = round(summary.avg_calories, 1)
            weekly_data[week_start]["protein"] = round(summary.avg_protein, 1)
            weekly_data[week_start]["carbs"] = round(summary.avg_carbs, 1)
            weekly_data[week_start]["fat"] = round(summary.avg_fat, 1)

    # Convert to sorted list
    result = sorted(weekly_data.values(), key=lambda x: x["week_start"])
    return result


def get_food_category_breakdown(user_id, days=30):
    """
    Analyze food consumption by category.
    Returns data showing what percentage of calories come from each food category.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    logs = DailyLog.query.filter(
        DailyLog.user_id == user_id,
        DailyLog.log_date >= start_date,
        DailyLog.log_date <= end_date,
    ).all()

    category_totals = defaultdict(lambda: {"calories": 0, "grams": 0})

    for log in logs:
        if log.my_food_id:
            my_food = db.session.get(MyFood, log.my_food_id)
            if my_food and my_food.food_category:
                category_name = my_food.food_category.description
                scaling_factor = log.amount_grams / 100.0

                calories = (my_food.calories_per_100g or 0) * scaling_factor
                grams = log.amount_grams or 0

                category_totals[category_name]["calories"] += calories
                category_totals[category_name]["grams"] += grams

        elif log.recipe_id:
            # For recipes, we need to get the category from the recipe itself
            from models import Recipe

            recipe = db.session.get(Recipe, log.recipe_id)
            if recipe and recipe.food_category:
                category_name = recipe.food_category.description
                scaling_factor = log.amount_grams / 100.0

                calories = (recipe.calories_per_100g or 0) * scaling_factor
                grams = log.amount_grams or 0

                category_totals[category_name]["calories"] += calories
                category_totals[category_name]["grams"] += grams

    # Calculate percentages
    total_calories = sum(data["calories"] for data in category_totals.values())
    result = []

    if total_calories > 0:
        for category, data in sorted(category_totals.items()):
            pct = (data["calories"] / total_calories) * 100
            result.append(
                {
                    "category": category,
                    "calories": round(data["calories"], 1),
                    "percentage": round(pct, 1),
                }
            )

    return result


def get_exercise_vs_diet_balance(user_id, days=30):
    """
    Calculate balance between calories consumed and calories burned.
    Returns data for visualization showing net calorie balance.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    diet_logs = DailyLog.query.filter(
        DailyLog.user_id == user_id,
        DailyLog.log_date >= start_date,
        DailyLog.log_date <= end_date,
    ).all()

    exercise_logs = ExerciseLog.query.filter(
        ExerciseLog.user_id == user_id,
        ExerciseLog.log_date >= start_date,
        ExerciseLog.log_date <= end_date,
    ).all()

    # Group by date
    daily_balance = defaultdict(
        lambda: {"date": None, "calories_in": 0, "calories_out": 0, "net": 0}
    )

    for log in diet_logs:
        if log.log_date not in daily_balance:
            daily_balance[log.log_date] = {
                "date": log.log_date,
                "calories_in": 0,
                "calories_out": 0,
                "net": 0,
            }
        daily_balance[log.log_date]["calories_in"] += calculate_nutrition_for_items(
            [log]
        )["calories"]

    for log in exercise_logs:
        if log.log_date not in daily_balance:
            daily_balance[log.log_date] = {
                "date": log.log_date,
                "calories_in": 0,
                "calories_out": 0,
                "net": 0,
            }
        daily_balance[log.log_date]["calories_out"] += log.calories_burned

    # Calculate net balance
    for date_key, data in daily_balance.items():
        data["net"] = round(data["calories_in"] - data["calories_out"], 1)

    # Convert to sorted list
    result = sorted(daily_balance.values(), key=lambda x: x["date"])
    return result


def get_nutrient_intake_vs_goals(user_id):
    """
    Calculate how user's intake compares to their goals for each macro.
    Returns data showing progress toward daily targets.
    """
    today = date.today()
    logs = DailyLog.query.filter(
        DailyLog.user_id == user_id, DailyLog.log_date == today
    ).all()

    user_goal = UserGoal.query.filter_by(user_id=user_id).first()

    if not user_goal:
        return None

    totals = calculate_nutrition_for_items(logs)
    deviations = calculate_intake_vs_goal_deviation(user_goal, logs)

    return {
        "calories": {
            "intake": round(totals["calories"], 1),
            "goal": user_goal.calories,
            "deviation": deviations["calories"],
        },
        "protein": {
            "intake": round(totals["protein"], 1),
            "goal": user_goal.protein,
            "deviation": deviations["protein"],
        },
        "carbs": {
            "intake": round(totals["carbs"], 1),
            "goal": user_goal.carbs,
            "deviation": deviations["carbs"],
        },
        "fat": {
            "intake": round(totals["fat"], 1),
            "goal": user_goal.fat,
            "deviation": deviations["fat"],
        },
    }


def get_body_composition_trends(user_id):
    """
    Get body composition data (weight, waist, body fat) over time.
    Returns data for multi-line chart showing trends.
    """
    checkins = (
        CheckIn.query.filter_by(user_id=user_id)
        .order_by(CheckIn.checkin_date.asc())
        .all()
    )

    result = []
    for ci in checkins:
        result.append(
            {
                "date": ci.checkin_date.strftime("%Y-%m-%d"),
                "weight_kg": ci.weight_kg,
                "waist_cm": ci.waist_cm,
                "body_fat_pct": ci.body_fat_percentage,
            }
        )

    return result
