import os
import asyncio
import subprocess
import tempfile
from constants import DIET_PRESETS, CORE_NUTRIENT_IDS
from flask import send_file, current_app, render_template
from types import SimpleNamespace
from cryptography.fernet import Fernet
from flask_mailing import Message
from opennourish import mail
from datetime import timedelta
from opennourish.time_utils import get_user_today
from models import (
    db,
    UserGoal,
    CheckIn,
    DailyLog,
    ExerciseLog,
    Food,
    MyFood,
    Recipe,
    UnifiedPortion,
    FoodNutrient,
)


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
    for date, logs in logs_by_date.items():
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
                total_nested_recipe_grams = sum(
                    ing.amount_grams for ing in nested_recipe.ingredients
                )

                if total_nested_recipe_grams > 0:
                    scaling_factor = item.amount_grams / total_nested_recipe_grams
                else:
                    scaling_factor = 0

                for key, value in nested_nutrition.items():
                    totals[key] += value * scaling_factor

    return totals


def _get_nutrition_label_data(fdc_id):
    food = db.session.get(Food, fdc_id)
    if not food:
        return None, None, None

    # Map common nutrition label fields to USDA nutrient names and their units
    nutrient_info = {
        "Energy": {
            "names": [
                "Energy",
                "Energy (Atwater General Factors)",
                "Energy (Atwater Specific Factors)",
            ],
            "unit": "kcal",
            "format": ".0f",
        },
        "Total lipid (fat)": {
            "names": ["Total lipid (fat)", "Lipids"],
            "unit": "g",
            "format": ".1f",
        },
        "Fatty acids, total saturated": {
            "names": ["Fatty acids, total saturated"],
            "unit": "g",
            "format": ".1f",
        },
        "Fatty acids, total trans": {
            "names": ["Fatty acids, total trans"],
            "unit": "g",
            "format": ".1f",
        },
        "Cholesterol": {"names": ["Cholesterol"], "unit": "mg", "format": ".0f"},
        "Sodium": {"names": ["Sodium", "Sodium, Na"], "unit": "mg", "format": ".0f"},
        "Carbohydrate, by difference": {
            "names": ["Carbohydrate, by difference", "Carbohydrates"],
            "unit": "g",
            "format": ".1f",
        },
        "Fiber, total dietary": {
            "names": ["Fiber, total dietary", "Total dietary fiber (AOAC 2011.25)"],
            "unit": "g",
            "format": ".1f",
        },
        "Sugars, total including NLEA": {
            "names": ["Sugars, total including NLEA", "Sugars, total", "Total Sugars"],
            "unit": "g",
            "format": ".1f",
        },
        "Sugars, added": {"names": ["Sugars, added"], "unit": "g", "format": ".1f"},
        "Protein": {
            "names": ["Protein", "Adjusted Protein"],
            "unit": "g",
            "format": ".1f",
        },
        "Vitamin D": {
            "names": ["Vitamin D (D2 + D3)"],
            "unit": "mcg",
            "format": ".0f",
            "key": "vitamin_d",
        },
        "Calcium": {
            "names": ["Calcium", "Calcium, Ca", "Calcium, added", "Calcium, intrinsic"],
            "unit": "mg",
            "format": ".0f",
            "key": "calcium",
        },
        "Iron": {
            "names": [
                "Iron",
                "Iron, Fe",
                "Iron, heme",
                "Iron, non-heme",
                "Iron, added",
                "Iron, intrinsic",
            ],
            "unit": "mg",
            "format": ".1f",
            "key": "iron",
        },
        "Potassium": {
            "names": ["Potassium", "Potassium, K"],
            "unit": "mg",
            "format": ".0f",
            "key": "potassium",
        },
    }

    # Extract nutrient values
    nutrients_for_label = {}
    for label_field, info in nutrient_info.items():
        found_value = None  # Initialize to None to distinguish from 0.0
        for usda_name in info["names"]:
            # Iterate through the eager-loaded food.nutrients
            for fn in food.nutrients:
                if fn.nutrient.name == usda_name:
                    found_value = fn.amount
                    break  # Break as soon as a match is found
            # If a value was found for the current usda_name, stop searching other names for this label_field
            if found_value is not None:
                break
        nutrients_for_label[label_field] = (
            found_value if found_value is not None else 0.0
        )  # Assign 0.0 if not found
    return food, nutrient_info, nutrients_for_label


# this is for USDA foods
def _generate_typst_content(
    food, nutrient_info, nutrients_for_label, include_extra_info=False
):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping the '*' character."""
        if not isinstance(text, str):
            return text
        return text.replace("*", r"\*")

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.fdc_id == food.fdc_id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        serving_size_str = _sanitize_for_typst(default_portion.full_description_str_1)
        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    ingredients_str = food.ingredients if food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()
    if food_portions:
        portions_list = [
            f"{p.full_description_str_1} ({p.gram_weight}g)" for p in food_portions
        ]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"
    portions_str = _sanitize_for_typst(portions_str)

    # Sanitize food description
    sanitized_food_description = _sanitize_for_typst(food.description)

    # Prepare UPC for EAN-13. A 12-digit UPC-A needs a leading 0.
    # The ean13 function takes the first 12 digits and calculates the 13th.
    upc_str = "0"
    if food.upc and len(food.upc) == 12:
        upc_str = f"0{food.upc}"[:12]
    elif food.upc and len(food.upc) == 13:
        upc_str = food.upc[:12]
    elif food.upc:
        # Pad or truncate to 12 digits if it's some other length
        upc_str = food.upc.ljust(12, "0")[:12]

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:{nutrient_info['Energy']['format']}}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:{nutrient_info['Total lipid (fat)']['format']}}, unit: "{nutrient_info['Total lipid (fat)']['unit']}"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:{nutrient_info['Fatty acids, total saturated']['format']}}, unit: "{nutrient_info['Fatty acids, total saturated'] ['unit']}"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:{nutrient_info['Fatty acids, total trans']['format']}}, unit: "{nutrient_info['Fatty acids, total trans']['unit']}"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:{nutrient_info['Cholesterol']['format']}}, unit: "{nutrient_info['Cholesterol']['unit']}"),
  sodium: (value: {scaled_nutrients['Sodium']:{nutrient_info['Sodium']['format']}}, unit: "{nutrient_info['Sodium']['unit']}"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:{nutrient_info['Carbohydrate, by difference']['format']}}, unit: "{nutrient_info['Carbohydrate, by difference']['unit']}"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:{nutrient_info['Fiber, total dietary']['format']}}, unit: "{nutrient_info['Fiber, total dietary']['unit']}"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:{nutrient_info['Sugars, total including NLEA']['format']}}, unit: "{nutrient_info['Sugars, total including NLEA']['unit']}"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:{nutrient_info['Sugars, added']['format']}}, unit: "{nutrient_info['Sugars, added']['unit']}"),
  protein: (value: {scaled_nutrients['Protein']:{nutrient_info['Protein']['format']}}, unit: "{nutrient_info['Protein']['unit']}"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:{nutrient_info['Vitamin D']['format']}}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:{nutrient_info['Calcium']['format']}}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:{nutrient_info['Iron']['format']}}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:{nutrient_info['Potassium']['format']}}, unit: "mg"),
  ),
)
"""

    if include_extra_info:
        typst_content = (
            typst_content_data
            + f"""
#set page(paper: "a4", header: align(right + horizon)[OpenNourish Food fact sheet], columns: 2)
#set text(font: "Liberation Sans")
#place(
  top + center,
  float: true,
  scope: "parent",
  clearance: 2em,
)[
= {sanitized_food_description}
]
== UPC:
#ean13(scale:(1.8, .5), "{upc_str}")

== Ingredients: 
{ingredients_str}

== Portion Sizes: 
{portions_str}

#colbreak()
#show: nutrition-label-nam(data)

"""
        )
    else:
        typst_content = (
            typst_content_data
            + """
#set page(width: 12cm, height: 18cm)
#show: nutrition-label-nam(data)
"""
        )

    return typst_content


def generate_nutrition_label_pdf(fdc_id):
    food, nutrient_info, nutrients_for_label = _get_nutrition_label_data(fdc_id)
    if not food:
        return "Food not found", 404

    typst_content = _generate_typst_content(
        food, nutrient_info, nutrients_for_label, include_extra_info=True
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        pdf_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=f"nutrition_label_{fdc_id}.pdf",
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return (
                "Typst executable not found. Please ensure Typst is installed and in your system's PATH.",
                500,
            )


def generate_nutrition_label_svg(fdc_id):
    food, nutrient_info, nutrients_for_label = _get_nutrition_label_data(fdc_id)
    if not food:
        return "Food not found", 404

    typst_content = _generate_typst_content(food, nutrient_info, nutrients_for_label)

    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        svg_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.svg")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    "--format",
                    "svg",
                    os.path.basename(typ_file_path),
                    os.path.basename(svg_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            response = send_file(
                svg_file_path,
                as_attachment=False,
                download_name=f"nutrition_label_{fdc_id}.svg",
                mimetype="image/svg+xml",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return (
                "Typst executable not found. Please ensure Typst is installed and in your system's PATH.",
                500,
            )


def calculate_recipe_nutrition_per_100g(recipe):
    """
    Calculates the nutritional values per 100g for a given recipe.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = sum(ing.amount_grams for ing in recipe.ingredients)

    nutrition_per_100g = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    if total_grams > 0:
        scaling_factor = 100.0 / total_grams
        nutrition_per_100g["calories"] = total_nutrition["calories"] * scaling_factor
        nutrition_per_100g["protein"] = total_nutrition["protein"] * scaling_factor
        nutrition_per_100g["carbs"] = total_nutrition["carbs"] * scaling_factor
        nutrition_per_100g["fat"] = total_nutrition["fat"] * scaling_factor

    return nutrition_per_100g


def update_recipe_nutrition(recipe):
    """
    Calculates and updates the nutritional data for a recipe based on its ingredients.
    The session is not committed here.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = sum(
        ing.amount_grams for ing in recipe.ingredients if ing.amount_grams is not None
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


def _get_nutrition_label_data_myfood(my_food_id):
    """
    Fetches a MyFood item and its nutritional data, formatted for the Typst label generator.
    """
    my_food = db.session.get(MyFood, my_food_id)
    if not my_food:
        return None, None

    # The Typst template expects specific keys. We map the MyFood attributes to these keys.
    # All values are per 100g.
    nutrients_for_label = {
        "Energy": my_food.calories_per_100g or 0,
        "Total lipid (fat)": my_food.fat_per_100g or 0,
        "Fatty acids, total saturated": my_food.saturated_fat_per_100g or 0,
        "Fatty acids, total trans": my_food.trans_fat_per_100g or 0,
        "Cholesterol": my_food.cholesterol_mg_per_100g or 0,
        "Sodium": my_food.sodium_mg_per_100g or 0,
        "Carbohydrate, by difference": my_food.carbs_per_100g or 0,
        "Fiber, total dietary": my_food.fiber_per_100g or 0,
        "Sugars, total including NLEA": my_food.sugars_per_100g or 0,
        "Sugars, added": my_food.added_sugars_per_100g or 0,
        "Protein": my_food.protein_per_100g or 0,
        "Vitamin D": my_food.vitamin_d_mcg_per_100g or 0,
        "Calcium": my_food.calcium_mg_per_100g or 0,
        "Iron": my_food.iron_mg_per_100g or 0,
        "Potassium": my_food.potassium_mg_per_100g or 0,
    }
    return my_food, nutrients_for_label


def _generate_typst_content_myfood(my_food, nutrients_for_label, label_only=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace("\\", r"\\").replace('"', r"\"").replace("*", r"\*")

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.my_food_id == my_food.id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        serving_size_str = _sanitize_for_typst(default_portion.full_description_str_1)
        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    # Sanitize all user-provided strings
    sanitized_food_name = _sanitize_for_typst(my_food.description)

    ingredients_str = my_food.ingredients if my_food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)

    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"my_food.upc from DB: {my_food.upc}")
    upc_str = "0"  # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if my_food.upc and len(my_food.upc) == 13 and my_food.upc.startswith("200"):
        upc_str = my_food.upc[:12]  # Slice off the checksum for the label generator
        current_app.logger.debug(
            f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}"
        )

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif my_food.upc and len(my_food.upc) == 12:
        upc_str = f"0{my_food.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif my_food.upc and len(my_food.upc) == 13:
        upc_str = my_food.upc[:12]
        current_app.logger.debug(
            f"Full EAN-13 detected. Using first 12 digits: {upc_str}"
        )

    # Fallback for other lengths
    elif my_food.upc:
        upc_str = my_food.upc.ljust(12, "0")[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(my_food_id=my_food.id).all()
    if food_portions:
        portions_list = [
            f"{_sanitize_for_typst(p.full_description_str_1)} ({p.gram_weight}g)"
            for p in food_portions
        ]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:.0f}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {scaled_nutrients['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {scaled_nutrients['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if label_only:
        typst_content = (
            typst_content_data
            + f"""
#set page(width: 2in, height: 1in)
#set page(margin: (x: 0.1cm, y: 0.1cm))
#set text(font: "Liberation Sans", size: 8pt)
#ean13(scale:(1.6, .5), "{upc_str}")
{sanitized_food_name}
"""
        )
    else:
        typst_content = (
            typst_content_data
            + f"""
#set page(width: 6in, height: 4in, columns: 2)
#set page(margin: (x: 0.2in, y: 0.05in))
#set text(font: "Liberation Sans", size: 8pt)
#ean13(scale:(2.0, .5), "{upc_str}")

#box(width: 3.25in, height: 3in, clip: true, 
[== My Food: 
{sanitized_food_name}
== Ingredients: 
{ingredients_str}
== Portion Sizes: 
{portions_str}])
#colbreak()
#set align(right)
#show: nutrition-label-nam(data, scale-percent: 75%, show-footnote: false,)
"""
        )

    return typst_content


def generate_myfood_label_pdf(my_food_id, label_only=False):
    """
    Generates a PDF nutrition label for a MyFood item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    my_food, nutrients_for_label = _get_nutrition_label_data_myfood(my_food_id)
    if not my_food:
        return "Food not found", 404

    typst_content = _generate_typst_content_myfood(
        my_food, nutrients_for_label, label_only=label_only
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(
            tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.typ"
        )
        pdf_file_path = os.path.join(
            tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.pdf"
        )

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    "--pages",
                    "1",
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            download_name = f"{my_food.description}_{file_suffix}.pdf"
            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=download_name,
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            current_app.logger.error(
                f"Typst compilation failed for my_food_id {my_food_id}: {e.stderr}"
            )
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error("Typst executable not found.")
            return (
                "Typst executable not found. Please ensure Typst is installed and in your system's PATH.",
                500,
            )


def _generate_typst_content_recipe(recipe, nutrients_for_label, label_only=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace("\\", r"\\").replace('"', r"\"").replace("*", r"\*")

    # 0. Determine how many servings the recipe has
    servings_str = _sanitize_for_typst(recipe.servings)

    # 1. Determine the default portion and scaling factor
    default_portion = (
        UnifiedPortion.query.filter(UnifiedPortion.recipe_id == recipe.id)
        .filter(UnifiedPortion.seq_num.isnot(None))
        .order_by(UnifiedPortion.seq_num)
        .first()
    )

    if default_portion and default_portion.gram_weight > 0:
        serving_size_str = _sanitize_for_typst(default_portion.full_description_str_1)
        scaling_factor = default_portion.gram_weight / 100.0
    else:
        # Fallback to 100g if no default portion is found
        serving_size_str = "100g"
        scaling_factor = 1.0

    # 2. Scale the nutrient values
    scaled_nutrients = {
        key: (value or 0) * scaling_factor for key, value in nutrients_for_label.items()
    }

    # Sanitize all user-provided strings
    sanitized_recipe_name = _sanitize_for_typst(recipe.name)

    # Create a string of ingredients for the recipe
    # Manually fetch USDA food data
    usda_food_ids = [ing.fdc_id for ing in recipe.ingredients if ing.fdc_id]
    if usda_food_ids:
        usda_foods = Food.query.filter(Food.fdc_id.in_(usda_food_ids)).all()
        usda_foods_map = {food.fdc_id: food for food in usda_foods}
    ingredients_str = ""
    if recipe.ingredients:
        for ing in recipe.ingredients:
            if ing.fdc_id:
                ing.usda_food = usda_foods_map.get(ing.fdc_id)

            # Calculate nutrition for each individual ingredient
            ingredient_nutrition = calculate_nutrition_for_items([ing])
            ing.calories = ingredient_nutrition["calories"]
            ing.protein = ingredient_nutrition["protein"]
            ing.carbs = ingredient_nutrition["carbs"]
            ing.fat = ingredient_nutrition["fat"]

            # Calculate quantity and portion description
            food_object = None
            if hasattr(ing, "usda_food") and ing.usda_food:
                food_object = ing.usda_food
                ing.description = food_object.description
            elif ing.my_food:
                food_object = ing.my_food
                ing.description = food_object.description
            elif ing.linked_recipe:
                food_object = ing.linked_recipe
                ing.description = food_object.name

            ing.quantity = ing.amount_grams
            ing.portion_description = "g"

            if food_object:
                available_portions = get_available_portions(food_object)
                available_portions.sort(key=lambda p: p.gram_weight, reverse=True)

                for p in available_portions:
                    if p.gram_weight > 0.1:
                        if (
                            abs(ing.amount_grams % p.gram_weight) < 0.01
                            or abs(p.gram_weight - (ing.amount_grams % p.gram_weight))
                            < 0.01
                        ):
                            ing.quantity = round(ing.amount_grams / p.gram_weight, 2)
                            ing.portion_description = p.full_description_str
                            break
            ingredients_str = (
                ingredients_str
                + _sanitize_for_typst(
                    "{:.2f}".format(ing.quantity)
                    + " "
                    + ing.portion_description
                    + " "
                    + ing.description
                )
                + "\\ "
            )
    else:
        ingredients_str = "N/A"

    # Sanitize all user-provided strings
    sanitized_recipe_instructions = _sanitize_for_typst(recipe.instructions)

    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"recipe.upc from DB: {recipe.upc}")
    upc_str = "0"  # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if recipe.upc and len(recipe.upc) == 13 and recipe.upc.startswith("201"):
        upc_str = recipe.upc[:12]  # Slice off the checksum for the label generator
        current_app.logger.debug(
            f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}"
        )

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif recipe.upc and len(recipe.upc) == 12:
        upc_str = f"0{recipe.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif recipe.upc and len(recipe.upc) == 13:
        upc_str = recipe.upc[:12]
        current_app.logger.debug(
            f"Full EAN-13 detected. Using first 12 digits: {upc_str}"
        )

    # Fallback for other lengths
    elif recipe.upc:
        upc_str = recipe.upc.ljust(12, "0")[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(recipe_id=recipe.id).all()
    if food_portions:
        portions_list = [
            f"{_sanitize_for_typst(p.full_description_str_1)} ({p.gram_weight}g)"
            for p in food_portions
        ]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "{servings_str}",
  serving_size: "{serving_size_str}",
  calories: "{scaled_nutrients['Energy']:.0f}",
  total_fat: (value: {scaled_nutrients['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {scaled_nutrients['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {scaled_nutrients['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {scaled_nutrients['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {scaled_nutrients['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {scaled_nutrients['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {scaled_nutrients['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {scaled_nutrients['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {scaled_nutrients['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {scaled_nutrients['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {scaled_nutrients['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {scaled_nutrients['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {scaled_nutrients['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {scaled_nutrients['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if label_only:
        typst_content = (
            typst_content_data
            + f"""
#set page(width: 6in, height: 4in, columns: 2)
#set page(margin: (x: 0.2in, y: 0.05in))
#set text(font: "Liberation Sans", size: 8pt)
#ean13(scale:(2.0, .5), "{upc_str}")

#box(width: 3.25in, height: 3in, clip: true, 
[== Recipe: 
{sanitized_recipe_name}
== Ingredients: 
{ingredients_str}
== Portion Sizes: 
{portions_str}])
#colbreak()
#set align(right)
#show: nutrition-label-nam(data, scale-percent: 75%, show-footnote: false,)
"""
        )
    else:
        typst_content = (
            typst_content_data
            + f"""
#set page(paper: "us-letter", columns: 2)
#set page(margin: (x: 0.75in, y: 0.75in))
#set text(font: "Liberation Sans", size: 10pt)

#box(width: 4.25in, height: 8in, clip: true, 
[= {sanitized_recipe_name}
== Ingredients: 
{ingredients_str}
== Instructions: 
{sanitized_recipe_instructions}])
#colbreak()
#set align(right)
#ean13(scale:(2.0, .5), "{upc_str}")
== Portion Sizes: 
{portions_str}
== Label:
#show: nutrition-label-nam(data, scale-percent: 75%)
"""
        )

    return typst_content


def _get_nutrition_label_data_recipe(recipe_id):
    """
    Fetches a Recipe item and its nutritional data, formatted for the Typst label generator.
    """
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        return None, None

    # The Typst template expects specific keys. We map the Recipe attributes to these keys.
    # All values are per 100g.
    nutrients_for_label = {
        "Energy": recipe.calories_per_100g or 0,
        "Total lipid (fat)": recipe.fat_per_100g or 0,
        "Fatty acids, total saturated": recipe.saturated_fat_per_100g or 0,
        "Fatty acids, total trans": recipe.trans_fat_per_100g or 0,
        "Cholesterol": recipe.cholesterol_mg_per_100g or 0,
        "Sodium": recipe.sodium_mg_per_100g or 0,
        "Carbohydrate, by difference": recipe.carbs_per_100g or 0,
        "Fiber, total dietary": recipe.fiber_per_100g or 0,
        "Sugars, total including NLEA": recipe.sugars_per_100g or 0,
        "Sugars, added": recipe.added_sugars_per_100g or 0,
        "Protein": recipe.protein_per_100g or 0,
        "Vitamin D": recipe.vitamin_d_mcg_per_100g or 0,
        "Calcium": recipe.calcium_mg_per_100g or 0,
        "Iron": recipe.iron_mg_per_100g or 0,
        "Potassium": recipe.potassium_mg_per_100g or 0,
    }
    return recipe, nutrients_for_label


def generate_recipe_label_pdf(recipe_id, label_only=False):
    """
    Generates a PDF nutrition label for a Recipe item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    recipe, nutrients_for_label = _get_nutrition_label_data_recipe(recipe_id)
    if not recipe:
        return "Recipe not found", 404

    typst_content = _generate_typst_content_recipe(
        recipe, nutrients_for_label, label_only=label_only
    )
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(
            tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.typ"
        )
        pdf_file_path = os.path.join(
            tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.pdf"
        )

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                [
                    "typst",
                    "compile",
                    os.path.basename(typ_file_path),
                    "--pages",
                    "1",
                    os.path.basename(pdf_file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=tmpdir,
            )

            download_name = f"{recipe.name}_{file_suffix}.pdf"
            response = send_file(
                pdf_file_path,
                as_attachment=False,
                download_name=download_name,
                mimetype="application/pdf",
            )
            # Add headers to prevent caching
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        except subprocess.CalledProcessError as e:
            current_app.logger.error(
                f"Typst compilation failed for recipe_id {recipe_id}: {e.stderr}"
            )
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error("Typst executable not found.")
            return (
                "Typst executable not found. Please ensure Typst is installed and in your system's PATH.",
                500,
            )


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
    if not portion or not portion.gram_weight or portion.gram_weight == 1.0:
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
    if not portion or not portion.gram_weight or portion.gram_weight == 1.0:
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
