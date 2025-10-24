import asyncio
from constants import DIET_PRESETS, CORE_NUTRIENT_IDS, MEAL_CONFIG, DEFAULT_MEAL_NAMES
from flask import (
    current_app,
    render_template,
    session,
    flash,
    url_for,
)
from markupsafe import Markup
from types import SimpleNamespace
from cryptography.fernet import Fernet
from flask_mailing import Message
from opennourish import mail
from datetime import datetime, timedelta
from opennourish.time_utils import get_user_today
from models import (
    db,
    UserGoal,
    CheckIn,
    DailyLog,
    ExerciseLog,
    MyFood,
    FoodNutrient,
)
from sqlalchemy.inspection import inspect
from datetime import date
from decimal import Decimal


def _serialize_model_for_session(model_instance):
    """
    Serializes a SQLAlchemy model instance into a JSON-serializable dictionary.
    """
    mapper = inspect(model_instance.__class__)
    serialized_data = {}
    for column in mapper.columns:
        value = getattr(model_instance, column.key)
        if isinstance(value, (datetime, date)):
            serialized_data[column.key] = value.isoformat()
        elif isinstance(value, Decimal):
            serialized_data[column.key] = float(value)
        else:
            serialized_data[column.key] = value
    return serialized_data


def encrypt_value(value, key):
    f = Fernet(key)
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value, key):
    f = Fernet(key)
    return f.decrypt(encrypted_value.encode()).decode()


def send_password_reset_email(user, token):
    msg = Message(
        subject="Password Reset Request",
        recipients=[user.email],
        html=render_template("email/reset_password.html", user=user, token=token),
    )
    current_app.logger.debug(
        f"Attempting to send email. MAIL_SUPPRESS_SEND: {current_app.config.get('MAIL_SUPPRESS_SEND')}"
    )
    try:
        asyncio.run(mail.send_message(msg))
        current_app.logger.info(f"Password reset email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(
            f"Failed to send password reset email to {user.email}: {e}"
        )


def send_verification_email(user, token):
    msg = Message(
        subject="Verify Your Email Address",
        recipients=[user.email],
        html=render_template("email/verify_email.html", user=user, token=token),
    )
    current_app.logger.debug(
        f"Attempting to send verification email. MAIL_SUPPRESS_SEND: {current_app.config.get('MAIL_SUPPRESS_SEND')}"
    )
    try:
        asyncio.run(mail.send_message(msg))
        current_app.logger.info(f"Verification email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(
            f"Failed to send verification email to {user.email}: {e}"
        )


def calculate_weekly_nutrition_summary(weekly_logs):
    """
    Calculates the average daily nutritional summary for a given list of weekly DailyLog items.
    """
    if not weekly_logs:
        return SimpleNamespace(avg_calories=0, avg_protein=0, avg_carbs=0, avg_fat=0)

    total_nutrition = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    # Group logs by date
    logs_by_date = {}
    for log in weekly_logs:
        if log.log_date not in logs_by_date:
            logs_by_date[log.log_date] = []
        logs_by_date[log.log_date].append(log)

    # Calculate total nutrition for the week
    for date1, logs in logs_by_date.items():
        daily_totals = calculate_nutrition_for_items(logs)
        total_nutrition["calories"] += daily_totals["calories"]
        total_nutrition["protein"] += daily_totals["protein"]
        total_nutrition["carbs"] += daily_totals["carbs"]
        total_nutrition["fat"] += daily_totals["fat"]

    # Calculate the average over the number of days that have logs
    num_days_with_logs = len(logs_by_date)
    if num_days_with_logs > 0:
        avg_calories = total_nutrition["calories"] / num_days_with_logs
        avg_protein = total_nutrition["protein"] / num_days_with_logs
        avg_carbs = total_nutrition["carbs"] / num_days_with_logs
        avg_fat = total_nutrition["fat"] / num_days_with_logs
    else:
        avg_calories = avg_protein = avg_carbs = avg_fat = 0

    return SimpleNamespace(
        avg_calories=avg_calories,
        avg_protein=avg_protein,
        avg_carbs=avg_carbs,
        avg_fat=avg_fat,
    )


def calculate_nutrient_density(daily_logs):
    """
    Calculates nutrient density (calories per gram) for a given set of daily logs.
    Returns both overall and macro-specific densities.
    """
    if not daily_logs:
        return {"overall": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    # Calculate total nutrition and grams for all foods in the logs
    totals = calculate_nutrition_for_items(daily_logs)

    # Calculate total weight (in grams) of consumed foods
    total_weight_grams = sum(
        log.amount_grams for log in daily_logs if log.amount_grams is not None
    )

    if total_weight_grams == 0:
        return {"overall": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    # Calculate overall calorie density (calories per gram)
    overall_density = totals["calories"] / total_weight_grams

    # Calculate macro-specific densities
    protein_density = (
        (totals["protein"] * 4) / total_weight_grams if totals["protein"] > 0 else 0.0
    )
    carbs_density = (
        (totals["carbs"] * 4) / total_weight_grams if totals["carbs"] > 0 else 0.0
    )
    fat_density = (totals["fat"] * 9) / total_weight_grams if totals["fat"] > 0 else 0.0

    return {
        "overall": round(overall_density, 2),
        "protein": round(protein_density, 2),
        "carbs": round(carbs_density, 2),
        "fat": round(fat_density, 2),
    }


def get_meal_based_nutrition(daily_logs):
    """
    Groups logs by meal type and calculates nutrition totals for each.
    Assumes the logs have a meal_type attribute or can be grouped in another way.
    Returns data suitable for visualization of macronutrient distribution across meals.
    """
    # Group logs by meal type
    meal_groups = {}

    for log in daily_logs:
        # For now, we'll group by index - this would normally use a proper meal_type field
        # If there's no meal_type or it's not set, default to 'other'
        if hasattr(log, "meal_name") and log.meal_name:
            meal_name = log.meal_name
        else:
            meal_name = "Other"

        if meal_name not in meal_groups:
            meal_groups[meal_name] = []
        meal_groups[meal_name].append(log)

    # Calculate nutrition for each meal group
    meal_nutrition = {}
    for meal_name, logs in meal_groups.items():
        totals = calculate_nutrition_for_items(logs)
        meal_nutrition[meal_name] = {
            "calories": round(totals["calories"], 2),
            "protein": round(totals["protein"], 2),
            "carbs": round(totals["carbs"], 2),
            "fat": round(totals["fat"], 2),
            "saturated_fat": round(totals["saturated_fat"], 2),
            "trans_fat": round(totals["trans_fat"], 2),
            "cholesterol": round(totals["cholesterol"], 2),
            "sodium": round(totals["sodium"], 2),
            "fiber": round(totals["fiber"], 2),
            "sugars": round(totals["sugars"], 2),
            "vitamin_d": round(totals["vitamin_d"], 2),
            "calcium": round(totals["calcium"], 2),
            "iron": round(totals["iron"], 2),
            "potassium": round(totals["potassium"], 2),
            "net_carbs": round(totals["net_carbs"], 2),
            "grams": sum(
                log.amount_grams for log in logs if log.amount_grams is not None
            ),
        }

        # Ensure added_sugars key exists, defaulting to 0.0 if missing
        if "added_sugars" in totals:
            meal_nutrition[meal_name]["added_sugars"] = round(totals["added_sugars"], 2)
        else:
            meal_nutrition[meal_name]["added_sugars"] = 0.0

    return meal_nutrition


def calculate_intake_vs_goal_deviation(user_goals, daily_logs):
    """
    Calculate deviation from user goals (in percentage) for each macro.
    Returns a dict with deviations per macro.
    """
    if not user_goals or not daily_logs:
        return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    totals = calculate_nutrition_for_items(daily_logs)

    # Calculate percentage deviation from goal for each macro
    deviations = {}
    try:
        if user_goals.calories and user_goals.calories > 0:
            calories_deviation = (
                (totals["calories"] - user_goals.calories) / user_goals.calories
            ) * 100
            deviations["calories"] = round(calories_deviation, 2)
        else:
            deviations["calories"] = 0.0

        if user_goals.protein and user_goals.protein > 0:
            protein_deviation = (
                (totals["protein"] - user_goals.protein) / user_goals.protein
            ) * 100
            deviations["protein"] = round(protein_deviation, 2)
        else:
            deviations["protein"] = 0.0

        if user_goals.carbs and user_goals.carbs > 0:
            carbs_deviation = (
                (totals["carbs"] - user_goals.carbs) / user_goals.carbs
            ) * 100
            deviations["carbs"] = round(carbs_deviation, 2)
        else:
            deviations["carbs"] = 0.0

        if user_goals.fat and user_goals.fat > 0:
            fat_deviation = ((totals["fat"] - user_goals.fat) / user_goals.fat) * 100
            deviations["fat"] = round(fat_deviation, 2)
        else:
            deviations["fat"] = 0.0

    except Exception as e:
        current_app.logger.error(f"Error calculating intake vs goal deviation: {e}")
        # Return zeros on error to avoid crashing the dashboard
        return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    return deviations


# --- Unit Conversion Utilities ---


# Height
def cm_to_ft_in(cm):
    if cm is None:
        return None, None
    if cm == 0:
        return 0, 0
    inches_total = cm / 2.54
    feet = int(inches_total // 12)
    inches = round(inches_total % 12, 1)
    return feet, inches


def ft_in_to_cm(feet, inches):
    if feet is None or inches is None:
        return None
    return (feet * 12 + inches) * 2.54


# Weight
def kg_to_lbs(kg):
    if kg is None:
        return None
    return round(kg * 2.20462, 2)


def lbs_to_kg(lbs):
    if lbs is None:
        return None
    return lbs / 2.20462


# Waist
def cm_to_in(cm):
    if cm is None:
        return None
    return round(cm / 2.54, 1)


def in_to_cm(inches):
    if inches is None:
        return None
    return inches * 2.54


def get_display_weight(weight_kg, system):
    if system == "us":
        return kg_to_lbs(weight_kg)
    return weight_kg


def get_display_waist(waist_cm, system):
    if system == "us":
        return cm_to_in(waist_cm)
    return waist_cm


def get_display_height(height_cm, system):
    if system == "us":
        return cm_to_ft_in(height_cm)
    return height_cm


# --- BMR and Goal Calculation ---


def calculate_bmr(weight_kg, height_cm, age, gender, body_fat_percentage=None):
    """
    Calculates Basal Metabolic Rate (BMR).
    Uses Katch-McArdle formula if body_fat_percentage is provided, otherwise Mifflin-St Jeor.
    Returns a tuple of (bmr, formula_name).
    """
    if body_fat_percentage is not None and body_fat_percentage > 0:
        lean_body_mass = weight_kg * (1 - (body_fat_percentage / 100))
        bmr = 370 + (21.6 * lean_body_mass)
        formula_name = "Katch-McArdle"
    else:
        formula_name = "Mifflin-St Jeor"
        if gender == "Male":
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
        elif gender == "Female":
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
        else:
            return None, None  # Or raise an error for invalid gender
    return bmr, formula_name


def calculate_goals_from_preset(bmr, preset_name):
    """
    Calculates nutritional goals based on a BMR and a diet preset.
    """
    preset = DIET_PRESETS.get(preset_name)
    if not preset:
        return None

    # For simplicity, we'll use BMR as the calorie target.
    # In a real app, you might add an activity multiplier.
    calories = bmr
    protein_grams = (calories * preset["protein"]) / 4
    carbs_grams = (calories * preset["carbs"]) / 4
    fat_grams = (calories * preset["fat"]) / 9

    return {
        "calories": round(calories),
        "protein": round(protein_grams),
        "carbs": round(carbs_grams),
        "fat": round(fat_grams),
    }


def remove_leading_one(input_string):
    """
    If a string starts with '1', returns the rest of the string.
    Otherwise, returns the original string.
    """
    if input_string.startswith("1 "):
        return input_string[1:]
    else:
        return input_string


def get_allow_registration_status():
    """
    Checks the system setting in the database to see if user registration is currently allowed.
    Returns True if allowed, False otherwise.
    """
    from models import SystemSetting  # Import here to avoid circular dependency issues

    # Query the database for the setting
    allow_registration_setting = SystemSetting.query.filter_by(
        key="allow_registration"
    ).first()

    # If the setting exists and its value is 'False', registration is disabled
    if (
        allow_registration_setting
        and allow_registration_setting.value.lower() == "false"
    ):
        current_app.logger.debug(
            "get_allow_registration_status: Setting found and is 'False'. Registration disabled."
        )
        return False

    # In all other cases (setting doesn't exist, or value is not 'False'), registration is allowed
    current_app.logger.debug(
        "get_allow_registration_status: Setting not found or not 'False'. Registration enabled."
    )
    return True


def calculate_nutrition_for_items(items, processed_recipes=None):
    """
    Calculates total nutrition for a list of items (DailyLog or RecipeIngredient).
    `processed_recipes` is a set used to prevent infinite recursion for nested recipes.
    """
    if processed_recipes is None:
        processed_recipes = set()

    totals = {
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fat": 0,
        "saturated_fat": 0,
        "trans_fat": 0,
        "cholesterol": 0,
        "sodium": 0,
        "fiber": 0,
        "sugars": 0,
        "vitamin_d": 0,
        "calcium": 0,
        "iron": 0,
        "potassium": 0,
        "net_carbs": 0,
    }

    # Get nutrient IDs for common nutrients to avoid repeated lookups
    nutrient_ids = CORE_NUTRIENT_IDS

    usda_fdc_ids = set()
    for item in items:
        if item.fdc_id:
            usda_fdc_ids.add(item.fdc_id)

    nutrients_map = {}
    if usda_fdc_ids:
        # Fetch all relevant FoodNutrient objects in one query
        # Use .all() to execute the query and fetch results
        food_nutrients = (
            db.session.query(FoodNutrient)
            .filter(FoodNutrient.fdc_id.in_(usda_fdc_ids))
            .all()
        )
        for fn in food_nutrients:
            if fn.fdc_id not in nutrients_map:
                nutrients_map[fn.fdc_id] = {}
            nutrients_map[fn.fdc_id][fn.nutrient_id] = fn.amount

    for item in items:
        # Initialize scaling_factor for the current item
        scaling_factor = item.amount_grams / 100.0

        if item.fdc_id:
            if item.fdc_id in nutrients_map:
                for name, nid in nutrient_ids.items():
                    if nid in nutrients_map[item.fdc_id]:
                        totals[name] += nutrients_map[item.fdc_id][nid] * scaling_factor

        elif item.my_food_id:
            my_food = db.session.get(MyFood, item.my_food_id)
            if my_food:
                totals["calories"] += (my_food.calories_per_100g or 0) * scaling_factor
                totals["protein"] += (my_food.protein_per_100g or 0) * scaling_factor
                totals["carbs"] += (my_food.carbs_per_100g or 0) * scaling_factor
                totals["fat"] += (my_food.fat_per_100g or 0) * scaling_factor
                totals["saturated_fat"] += (
                    my_food.saturated_fat_per_100g or 0
                ) * scaling_factor
                totals["trans_fat"] += (
                    my_food.trans_fat_per_100g or 0
                ) * scaling_factor
                totals["cholesterol"] += (
                    my_food.cholesterol_mg_per_100g or 0
                ) * scaling_factor
                totals["sodium"] += (my_food.sodium_mg_per_100g or 0) * scaling_factor
                totals["fiber"] += (my_food.fiber_per_100g or 0) * scaling_factor
                totals["sugars"] += (my_food.sugars_per_100g or 0) * scaling_factor
                totals["vitamin_d"] += (
                    my_food.vitamin_d_mcg_per_100g or 0
                ) * scaling_factor
                totals["calcium"] += (my_food.calcium_mg_per_100g or 0) * scaling_factor
                totals["iron"] += (my_food.iron_mg_per_100g or 0) * scaling_factor
                totals["potassium"] += (
                    my_food.potassium_mg_per_100g or 0
                ) * scaling_factor

        elif item.recipe_id:
            # Handle nested recipes recursively
            from models import Recipe  # Import here to avoid circular dependency

            nested_recipe = db.session.get(Recipe, item.recipe_id)
            if nested_recipe:
                # Prevent infinite recursion for circular recipe dependencies
                if nested_recipe.id in processed_recipes:
                    current_app.logger.warning(
                        f"Circular recipe dependency detected for recipe ID {nested_recipe.id}. Skipping nutrition calculation for this instance."
                    )
                    continue

                processed_recipes.add(nested_recipe.id)
                nested_nutrition = calculate_nutrition_for_items(
                    nested_recipe.ingredients, processed_recipes
                )
                processed_recipes.remove(nested_recipe.id)

                # Determine the scaling factor for the nested recipe
                total_nested_recipe_grams = (
                    nested_recipe.final_weight_grams
                    if nested_recipe.final_weight_grams
                    and nested_recipe.final_weight_grams > 0
                    else sum(ing.amount_grams for ing in nested_recipe.ingredients)
                )

                if total_nested_recipe_grams > 0:
                    scaling_factor = item.amount_grams / total_nested_recipe_grams
                else:
                    scaling_factor = 0

                for key, value in nested_nutrition.items():
                    totals[key] += value * scaling_factor

    totals["net_carbs"] = max(0, totals.get("carbs", 0) - totals.get("fiber", 0))

    return totals


def get_available_portions(food_item):
    """
    Returns a list of all available portions for a given food item from the database.
    """
    if not food_item:
        return []

    # The 1-gram portion is now guaranteed to be in the database for all
    # food types (USDA, MyFood, Recipe), so we can simply query for all portions.
    if hasattr(food_item, "portions"):
        return food_item.portions

    return []


def calculate_recipe_nutrition_per_100g(recipe):
    """
    Calculates the nutritional values per 100g for a given recipe.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = (
        recipe.final_weight_grams
        if recipe.final_weight_grams and recipe.final_weight_grams > 0
        else sum(
            ing.amount_grams
            for ing in recipe.ingredients
            if ing.amount_grams is not None
        )
    )

    nutrition_per_100g = {
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fat": 0,
        "fiber": 0,
        "net_carbs": 0,
    }

    if total_grams > 0:
        scaling_factor = 100.0 / total_grams
        nutrition_per_100g["calories"] = (
            total_nutrition.get("calories", 0) * scaling_factor
        )
        nutrition_per_100g["protein"] = (
            total_nutrition.get("protein", 0) * scaling_factor
        )
        nutrition_per_100g["carbs"] = total_nutrition.get("carbs", 0) * scaling_factor
        nutrition_per_100g["fat"] = total_nutrition.get("fat", 0) * scaling_factor
        nutrition_per_100g["fiber"] = total_nutrition.get("fiber", 0) * scaling_factor
        nutrition_per_100g["net_carbs"] = max(
            0, nutrition_per_100g["carbs"] - nutrition_per_100g["fiber"]
        )

    return nutrition_per_100g


def update_recipe_nutrition(recipe):
    """
    Calculates and updates the nutritional data for a recipe based on its ingredients.
    The session is not committed here.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = (
        recipe.final_weight_grams
        if recipe.final_weight_grams and recipe.final_weight_grams > 0
        else sum(
            ing.amount_grams
            for ing in recipe.ingredients
            if ing.amount_grams is not None
        )
    )

    if total_grams > 0:
        scaling_factor = 100.0 / total_grams
        recipe.calories_per_100g = total_nutrition.get("calories", 0) * scaling_factor
        recipe.protein_per_100g = total_nutrition.get("protein", 0) * scaling_factor
        recipe.carbs_per_100g = total_nutrition.get("carbs", 0) * scaling_factor
        recipe.fat_per_100g = total_nutrition.get("fat", 0) * scaling_factor
        recipe.saturated_fat_per_100g = (
            total_nutrition.get("saturated_fat", 0) * scaling_factor
        )
        recipe.trans_fat_per_100g = total_nutrition.get("trans_fat", 0) * scaling_factor
        recipe.cholesterol_mg_per_100g = (
            total_nutrition.get("cholesterol", 0) * scaling_factor
        )
        recipe.sodium_mg_per_100g = total_nutrition.get("sodium", 0) * scaling_factor
        recipe.fiber_per_100g = total_nutrition.get("fiber", 0) * scaling_factor
        recipe.sugars_per_100g = total_nutrition.get("sugars", 0) * scaling_factor
        recipe.vitamin_d_mcg_per_100g = (
            total_nutrition.get("vitamin_d", 0) * scaling_factor
        )
        recipe.calcium_mg_per_100g = total_nutrition.get("calcium", 0) * scaling_factor
        recipe.iron_mg_per_100g = total_nutrition.get("iron", 0) * scaling_factor
        recipe.potassium_mg_per_100g = (
            total_nutrition.get("potassium", 0) * scaling_factor
        )
    else:
        # If there are no ingredients with weight, zero out the nutritional info
        recipe.calories_per_100g = 0.0
        recipe.protein_per_100g = 0.0
        recipe.carbs_per_100g = 0.0
        recipe.fat_per_100g = 0.0
        recipe.saturated_fat_per_100g = 0.0
        recipe.trans_fat_per_100g = 0.0
        recipe.cholesterol_mg_per_100g = 0.0
        recipe.sodium_mg_per_100g = 0.0
        recipe.fiber_per_100g = 0.0
        recipe.sugars_per_100g = 0.0
        recipe.vitamin_d_mcg_per_100g = 0.0
        recipe.calcium_mg_per_100g = 0.0
        recipe.iron_mg_per_100g = 0.0
        recipe.potassium_mg_per_100g = 0.0


def get_standard_meal_names_for_user(user):
    """
    Returns a list of standard meal names based on the user's preference.
    """
    if not user or not hasattr(user, "meals_per_day"):
        return DEFAULT_MEAL_NAMES

    return MEAL_CONFIG.get(user.meals_per_day, DEFAULT_MEAL_NAMES)


def calculate_weight_projection(user):
    """
    Projects a user's weight over time based on recent activity and goals.
    """
    today = get_user_today(user.timezone)

    # 1. Fetch latest check-in and goal
    latest_checkin = (
        CheckIn.query.filter_by(user_id=user.id)
        .order_by(CheckIn.checkin_date.desc())
        .first()
    )
    user_goal = UserGoal.query.filter_by(user_id=user.id).first()

    if not latest_checkin or not user_goal or not user_goal.weight_goal_kg:
        return (
            [],
            [],
            False,
            False,
        )  # Return empty lists if essential data is missing, and at_goal_and_maintaining is False

    # 2. Calculate BMR
    bmr, _ = calculate_bmr(
        weight_kg=latest_checkin.weight_kg,
        height_cm=user.height_cm,
        age=user.age,
        gender=user.gender,
        body_fat_percentage=latest_checkin.body_fat_percentage,
    )
    if not bmr:
        return [], [], False, False
    bmr = round(bmr)

    current_weight = latest_checkin.weight_kg
    goal_weight = user_goal.weight_goal_kg

    # 3. Calculate average daily calorie surplus/deficit
    two_weeks_ago = today - timedelta(days=14)

    recent_diet_logs = DailyLog.query.filter(
        DailyLog.user_id == user.id, DailyLog.log_date >= two_weeks_ago
    ).all()

    recent_exercise_logs = ExerciseLog.query.filter(
        ExerciseLog.user_id == user.id, ExerciseLog.log_date >= two_weeks_ago
    ).all()

    # Determine average daily calorie intake and expenditure over the last 14 days
    # If there's no recent activity, use the user's calorie goal as the intake baseline.

    logged_days = set(log.log_date for log in recent_diet_logs) | set(
        log.log_date for log in recent_exercise_logs
    )
    num_logged_days = (
        len(logged_days) if logged_days else 1
    )  # Ensure at least 1 to avoid division by zero

    total_calories_consumed = calculate_nutrition_for_items(recent_diet_logs)[
        "calories"
    ]
    total_calories_burned = sum(log.calories_burned for log in recent_exercise_logs)

    # Calculate average daily intake based on logs, or fall back to user goal if no logs
    if recent_diet_logs:
        avg_daily_calories_in = total_calories_consumed / num_logged_days
    elif user_goal and user_goal.calories is not None:
        avg_daily_calories_in = user_goal.calories
    else:
        return [], [], False  # Cannot make a projection without intake data

    # Calculate average daily burned calories based on logs, or fall back to weekly goal if no logs
    if recent_exercise_logs:
        avg_daily_calories_out = total_calories_burned / num_logged_days
    elif user_goal and user_goal.calories_burned_goal_weekly is not None:
        avg_daily_calories_out = (
            user_goal.calories_burned_goal_weekly / 7
        )  # Convert weekly goal to daily
    else:
        avg_daily_calories_out = 0  # Assume no exercise if no logs and no weekly goal

    avg_daily_surplus_deficit = avg_daily_calories_in - (bmr + avg_daily_calories_out)
    # current_app.logger.debug(f"BMR: {bmr}, Avg Daily Calories In: {avg_daily_calories_in}, Avg Daily Calories Out: {avg_daily_calories_out}, Avg Daily Surplus/Deficit: {avg_daily_surplus_deficit}")

    # Determine if the user is at their goal and maintaining
    at_goal_and_maintaining = False
    if (
        abs(avg_daily_surplus_deficit) < 1 and abs(current_weight - goal_weight) < 0.5
    ):  # Within 1 calorie and 0.5 kg of goal
        at_goal_and_maintaining = True

    # 4. Project weight
    projected_dates = []
    projected_weights = []

    current_weight = latest_checkin.weight_kg
    current_date = today
    goal_weight = user_goal.weight_goal_kg

    # Determine if the user is trending towards or away from the goal
    is_losing = avg_daily_surplus_deficit < 0
    is_gaining = avg_daily_surplus_deficit > 0

    wants_to_lose = goal_weight < current_weight
    wants_to_gain = goal_weight > current_weight

    trending_away = (wants_to_lose and is_gaining) or (wants_to_gain and is_losing)

    # Constants
    CALORIES_PER_KG_FAT = 7700
    PROJECTION_LIMIT_DAYS = 1095  # 3 years
    AWAY_TREND_LIMIT_DAYS = 1095

    day_count = 0

    while True:
        # If at goal and maintaining, only project for today
        if at_goal_and_maintaining and day_count == 1:
            break

        # Safety break for infinite loops
        if day_count > PROJECTION_LIMIT_DAYS:
            break

        # Safety break if trending away
        if trending_away and day_count > AWAY_TREND_LIMIT_DAYS:
            break

        # Add current state to projection
        projected_dates.append(current_date.strftime("%Y-%m-%d"))
        projected_weights.append(current_weight)

        # Check for goal completion
        if (wants_to_lose and current_weight <= goal_weight) or (
            wants_to_gain and current_weight >= goal_weight
        ):
            break  # Goal reached

        # Project next day's weight
        weight_change_kg = avg_daily_surplus_deficit / CALORIES_PER_KG_FAT
        current_weight += weight_change_kg
        current_date += timedelta(days=1)
        day_count += 1

    return projected_dates, projected_weights, trending_away, at_goal_and_maintaining


def ensure_portion_sequence(items):
    """
    Iterates through a list of items (MyFood, Recipe, Food) and ensures
    all their portions have a sequence number.
    """
    needs_commit = False
    for item in items:
        if hasattr(item, "portions") and item.portions:
            # Check if any portion is missing a seq_num
            if any(p.seq_num is None for p in item.portions):
                # Sort portions by gram_weight to create a stable order
                # Handle potential None in gram_weight just in case
                portions_to_update = sorted(
                    item.portions, key=lambda p: p.gram_weight or 0
                )
                for i, p in enumerate(portions_to_update):
                    p.seq_num = i + 1
                needs_commit = True
    if needs_commit:
        db.session.commit()


def get_nutrients_for_display(my_food, portion):
    """
    Calculates and returns the nutrient values scaled to the given portion's gram_weight.
    If the portion's gram_weight is 1.0, it returns values per 100g, as this is considered the base 'per gram' unit.
    """
    # If portion is None, or has 0 or 1.0 gram_weight, we want to show the base 100g values.
    if not portion or not portion.gram_weight or abs(portion.gram_weight - 1.0) < 1e-9:
        scaling_factor = 1.0
    # Otherwise, scale from per-100g to the portion's weight.
    else:
        scaling_factor = portion.gram_weight / 100.0

    # Create a dictionary of all nutrient attributes from the my_food object
    base_nutrients = {
        "calories": my_food.calories_per_100g,
        "protein": my_food.protein_per_100g,
        "carbs": my_food.carbs_per_100g,
        "fat": my_food.fat_per_100g,
        "saturated_fat": my_food.saturated_fat_per_100g,
        "trans_fat": my_food.trans_fat_per_100g,
        "cholesterol": my_food.cholesterol_mg_per_100g,
        "sodium": my_food.sodium_mg_per_100g,
        "fiber": my_food.fiber_per_100g,
        "sugars": my_food.sugars_per_100g,
        "added_sugars": my_food.added_sugars_per_100g,
        "vitamin_d": my_food.vitamin_d_mcg_per_100g,
        "calcium": my_food.calcium_mg_per_100g,
        "iron": my_food.iron_mg_per_100g,
        "potassium": my_food.potassium_mg_per_100g,
    }

    # Scale all nutrients
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in base_nutrients.items()
    }

    return scaled_nutrients


def convert_display_nutrients_to_100g(display_nutrients, portion):
    """
    Converts nutrient values from a given portion's scale back to per 100g.
    If the portion's gram_weight is 1.0, it assumes the display values are already per 100g.
    """
    # If portion is None, or has 0 or 1.0 gram_weight, assume display values are per 100g.
    if not portion or not portion.gram_weight or abs(portion.gram_weight - 1.0) < 1e-9:
        scaling_factor = 1.0
    # Otherwise, scale from the portion's weight up to 100g.
    else:
        scaling_factor = 100.0 / portion.gram_weight

    nutrients_100g = {}
    for key, value in display_nutrients.items():
        # Ensure value is a number before multiplication
        try:
            numeric_value = float(value) if value is not None else 0.0
        except (ValueError, TypeError):
            numeric_value = 0.0
        nutrients_100g[key] = numeric_value * scaling_factor
    return nutrients_100g


def prepare_undo_and_delete(
    item_to_delete,
    item_type_str,
    redirect_info,
    delete_method="hard",
    success_message="Item deleted.",
):
    """
    Handles deleting an item in a way that can be undone, using either a 'hard' delete or 'anonymize' method.
    """
    session_data = {
        "type": item_type_str,
        "redirect_info": redirect_info,
    }

    if delete_method == "hard":
        session_data["undo_method"] = "reinsert"
        # Serialize the full object
        data = _serialize_model_for_session(item_to_delete)
        session_data["data"] = data

        # Perform the hard delete
        db.session.delete(item_to_delete)

    elif delete_method == "anonymize":
        session_data["undo_method"] = "reassign_owner"
        session_data["data"] = {
            "item_id": item_to_delete.id,
            "original_user_id": item_to_delete.user_id,
        }

        # Perform the anonymization
        item_to_delete.user_id = None

    else:
        raise ValueError(f"Unknown delete_method: {delete_method}")

    # Store in session, commit, and flash
    session["last_deleted"] = session_data
    db.session.commit()

    undo_url = url_for("undo.undo_last_action")
    flash(
        Markup(f"{success_message} <a href='{undo_url}' class='alert-link'>Undo</a>"),
        "success",
    )


def calculate_bmi(weight_kg, height_cm):
    """
    Calculates Body Mass Index (BMI).
    Formula: weight (kg) / (height (m))^2
    """
    if not weight_kg or not height_cm or height_cm == 0:
        return None
    height_m = height_cm / 100
    bmi = weight_kg / (height_m**2)
    return bmi
