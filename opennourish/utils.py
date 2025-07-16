import os
import json
from models import db, Food, MyFood, Nutrient, FoodNutrient, Recipe, UnifiedPortion
from sqlalchemy.orm import selectinload
from config import Config
from flask import send_file, current_app
import subprocess
import tempfile
from types import SimpleNamespace

# --- Unit Conversion Utilities ---

# Height
def cm_to_ft_in(cm):
    if not cm:
        return None, None
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
    if system == 'us':
        return kg_to_lbs(weight_kg)
    return weight_kg

def get_display_waist(waist_cm, system):
    if system == 'us':
        return cm_to_in(waist_cm)
    return waist_cm

def get_display_height(height_cm, system):
    if system == 'us':
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
        if gender == 'Male':
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
        elif gender == 'Female':
            bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161
        else:
            return None, None # Or raise an error for invalid gender
    return bmr, formula_name

def calculate_goals_from_preset(bmr, preset_name):
    """
    Calculates nutritional goals based on a BMR and a diet preset.
    """
    preset = Config.DIET_PRESETS.get(preset_name)
    if not preset:
        return None

    # For simplicity, we'll use BMR as the calorie target.
    # In a real app, you might add an activity multiplier.
    calories = bmr
    protein_grams = (calories * preset['protein']) / 4
    carbs_grams = (calories * preset['carbs']) / 4
    fat_grams = (calories * preset['fat']) / 9

    return {
        'calories': round(calories),
        'protein': round(protein_grams),
        'carbs': round(carbs_grams),
        'fat': round(fat_grams)
    }

def get_available_portions(food_item):
    """
    Returns a list of all available portions for a given food item from the database.
    """
    if not food_item:
        return []

    # The 1-gram portion is now guaranteed to be in the database for all
    # food types (USDA, MyFood, Recipe), so we can simply query for all portions.
    if hasattr(food_item, 'portions'):
        return food_item.portions
    
    return []

def remove_leading_one(input_string):
    """
    If a string starts with '1', returns the rest of the string.
    Otherwise, returns the original string.
    """
    if input_string.startswith('1'):
        return input_string[1:]
    else:
        return input_string

def get_allow_registration_status():
    """
    Checks the system setting in the database to see if user registration is currently allowed.
    Returns True if allowed, False otherwise.
    """
    from models import SystemSetting # Import here to avoid circular dependency issues
    
    # Query the database for the setting
    allow_registration_setting = SystemSetting.query.filter_by(key='allow_registration').first()
    
    # If the setting exists and its value is 'False', registration is disabled
    if allow_registration_setting and allow_registration_setting.value.lower() == 'false':
        current_app.logger.debug("get_allow_registration_status: Setting found and is 'False'. Registration disabled.")
        return False
        
    # In all other cases (setting doesn't exist, or value is not 'False'), registration is allowed
    current_app.logger.debug("get_allow_registration_status: Setting not found or not 'False'. Registration enabled.")
    return True

def calculate_nutrition_for_items(items, processed_recipes=None):
    """
    Calculates total nutrition for a list of items (DailyLog or RecipeIngredient).
    `processed_recipes` is a set used to prevent infinite recursion for nested recipes.
    """
    if processed_recipes is None:
        processed_recipes = set()

    totals = {
        'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0,
        'saturated_fat': 0, 'trans_fat': 0, 'cholesterol': 0, 'sodium': 0,
        'fiber': 0, 'sugars': 0, 'vitamin_d': 0, 'calcium': 0, 'iron': 0, 'potassium': 0
    }

    # Get nutrient IDs for common nutrients to avoid repeated lookups
    nutrient_ids = Config.CORE_NUTRIENT_IDS

    usda_fdc_ids = set()
    for item in items:
        if item.fdc_id:
            usda_fdc_ids.add(item.fdc_id)

    nutrients_map = {}
    if usda_fdc_ids:
        # Fetch all relevant FoodNutrient objects in one query
        # Use .all() to execute the query and fetch results
        food_nutrients = db.session.query(FoodNutrient).filter(FoodNutrient.fdc_id.in_(usda_fdc_ids)).all()
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
                totals['calories'] += (my_food.calories_per_100g or 0) * scaling_factor
                totals['protein'] += (my_food.protein_per_100g or 0) * scaling_factor
                totals['carbs'] += (my_food.carbs_per_100g or 0) * scaling_factor
                totals['fat'] += (my_food.fat_per_100g or 0) * scaling_factor
                totals['saturated_fat'] += (my_food.saturated_fat_per_100g or 0) * scaling_factor
                totals['trans_fat'] += (my_food.trans_fat_per_100g or 0) * scaling_factor
                totals['cholesterol'] += (my_food.cholesterol_mg_per_100g or 0) * scaling_factor
                totals['sodium'] += (my_food.sodium_mg_per_100g or 0) * scaling_factor
                totals['fiber'] += (my_food.fiber_per_100g or 0) * scaling_factor
                totals['sugars'] += (my_food.sugars_per_100g or 0) * scaling_factor
                totals['vitamin_d'] += (my_food.vitamin_d_mcg_per_100g or 0) * scaling_factor
                totals['calcium'] += (my_food.calcium_mg_per_100g or 0) * scaling_factor
                totals['iron'] += (my_food.iron_mg_per_100g or 0) * scaling_factor
                totals['potassium'] += (my_food.potassium_mg_per_100g or 0) * scaling_factor

        elif item.recipe_id:
            # Handle nested recipes recursively
            from models import Recipe # Import here to avoid circular dependency
            nested_recipe = db.session.query(Recipe).options(selectinload(Recipe.ingredients)).get(item.recipe_id)
            if nested_recipe:
                # Prevent infinite recursion for circular recipe dependencies
                if nested_recipe.id in processed_recipes:
                    current_app.logger.warning(f"Circular recipe dependency detected for recipe ID {nested_recipe.id}. Skipping nutrition calculation for this instance.")
                    continue
                
                processed_recipes.add(nested_recipe.id)
                nested_nutrition = calculate_nutrition_for_items(nested_recipe.ingredients, processed_recipes)
                processed_recipes.remove(nested_recipe.id)
                
                # Determine the scaling factor for the nested recipe
                total_nested_recipe_grams = sum(ing.amount_grams for ing in nested_recipe.ingredients)

                if total_nested_recipe_grams > 0:
                    scaling_factor = item.amount_grams / total_nested_recipe_grams
                else:
                    scaling_factor = 0

                for key, value in nested_nutrition.items():
                    totals[key] += value * scaling_factor

    return totals

def _get_nutrition_label_data(fdc_id):
    food = db.session.query(Food).options(selectinload(Food.nutrients).selectinload(FoodNutrient.nutrient)).get(fdc_id)
    if not food:
        return None, None, None

    # Map common nutrition label fields to USDA nutrient names and their units
    nutrient_info = {
        "Energy": {"names": ["Energy", "Energy (Atwater General Factors)", "Energy (Atwater Specific Factors)"], "unit": "kcal", "format": ".0f"},
        "Total lipid (fat)": {"names": ["Total lipid (fat)", "Lipids"], "unit": "g", "format": ".1f"},
        "Fatty acids, total saturated": {"names": ["Fatty acids, total saturated"], "unit": "g", "format": ".1f"},
        "Fatty acids, total trans": {"names": ["Fatty acids, total trans"], "unit": "g", "format": ".1f"},
        "Cholesterol": {"names": ["Cholesterol"], "unit": "mg", "format": ".0f"},
        "Sodium": {"names": ["Sodium", "Sodium, Na"], "unit": "mg", "format": ".0f"},
        "Carbohydrate, by difference": {"names": ["Carbohydrate, by difference", "Carbohydrates"], "unit": "g", "format": ".1f"},
        "Fiber, total dietary": {"names": ["Fiber, total dietary", "Total dietary fiber (AOAC 2011.25)"], "unit": "g", "format": ".1f"},
        "Sugars, total including NLEA": {"names": ["Sugars, total including NLEA", "Sugars, total", "Total Sugars"], "unit": "g", "format": ".1f"},
        "Sugars, added": {"names": ["Sugars, added"], "unit": "g", "format": ".1f"},
        "Protein": {"names": ["Protein", "Adjusted Protein"], "unit": "g", "format": ".1f"},
        "Vitamin D": {"names": ["Vitamin D (D2 + D3)"], "unit": "mcg", "format": ".0f", "key": "vitamin_d"},
        "Calcium": {"names": ["Calcium", "Calcium, Ca", "Calcium, added", "Calcium, intrinsic"], "unit": "mg", "format": ".0f", "key": "calcium"},
        "Iron": {"names": ["Iron", "Iron, Fe", "Iron, heme", "Iron, non-heme", "Iron, added", "Iron, intrinsic"], "unit": "mg", "format": ".1f", "key": "iron"},
        "Potassium": {"names": ["Potassium", "Potassium, K"], "unit": "mg", "format": ".0f", "key": "potassium"}
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
        nutrients_for_label[label_field] = found_value if found_value is not None else 0.0 # Assign 0.0 if not found
    return food, nutrient_info, nutrients_for_label

def _generate_typst_content(food, nutrient_info, nutrients_for_label, include_extra_info=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping the '*' character."""
        if not isinstance(text, str):
            return text
        return text.replace('*', r'\*')

    ingredients_str = food.ingredients if food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)
    
    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(fdc_id=food.fdc_id).all()
    if food_portions:
        portions_list = [f"{p.full_description_str} ({p.gram_weight}g)" for p in food_portions]
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
        upc_str = food.upc.ljust(12, '0')[:12]

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "{nutrients_for_label['Energy']:{nutrient_info['Energy']['format']}}",
  total_fat: (value: {nutrients_for_label['Total lipid (fat)']:{nutrient_info['Total lipid (fat)']['format']}}, unit: "{nutrient_info['Total lipid (fat)']['unit']}"),
  saturated_fat: (value: {nutrients_for_label['Fatty acids, total saturated']:{nutrient_info['Fatty acids, total saturated']['format']}}, unit: "{nutrient_info['Fatty acids, total saturated']['unit']}"),
  trans_fat: (value: {nutrients_for_label['Fatty acids, total trans']:{nutrient_info['Fatty acids, total trans']['format']}}, unit: "{nutrient_info['Fatty acids, total trans']['unit']}"),
  cholesterol: (value: {nutrients_for_label['Cholesterol']:{nutrient_info['Cholesterol']['format']}}, unit: "{nutrient_info['Cholesterol']['unit']}"),
  sodium: (value: {nutrients_for_label['Sodium']:{nutrient_info['Sodium']['format']}}, unit: "{nutrient_info['Sodium']['unit']}"),
  carbohydrate: (value: {nutrients_for_label['Carbohydrate, by difference']:{nutrient_info['Carbohydrate, by difference']['format']}}, unit: "{nutrient_info['Carbohydrate, by difference']['unit']}"),
  fiber: (value: {nutrients_for_label['Fiber, total dietary']:{nutrient_info['Fiber, total dietary']['format']}}, unit: "{nutrient_info['Fiber, total dietary']['unit']}"),
  sugars: (value: {nutrients_for_label['Sugars, total including NLEA']:{nutrient_info['Sugars, total including NLEA']['format']}}, unit: "{nutrient_info['Sugars, total including NLEA']['unit']}"),
  added_sugars: (value: {nutrients_for_label['Sugars, added']:{nutrient_info['Sugars, added']['format']}}, unit: "{nutrient_info['Sugars, added']['unit']}"),
  protein: (value: {nutrients_for_label['Protein']:{nutrient_info['Protein']['format']}}, unit: "{nutrient_info['Protein']['unit']}"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {nutrients_for_label['Vitamin D']:{nutrient_info['Vitamin D']['format']}}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {nutrients_for_label['Calcium']:{nutrient_info['Calcium']['format']}}, unit: "mg"),
    (name: "Iron", key: "iron", value: {nutrients_for_label['Iron']:{nutrient_info['Iron']['format']}}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {nutrients_for_label['Potassium']:{nutrient_info['Potassium']['format']}}, unit: "mg"),
  ),
)
"""

    if include_extra_info:
        typst_content = typst_content_data + f"""
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
    else:
        typst_content = typst_content_data + f"""
#set page(width: 12cm, height: 18cm)
#show: nutrition-label-nam(data)
"""

    return typst_content

def generate_nutrition_label_pdf(fdc_id):
    food, nutrient_info, nutrients_for_label = _get_nutrition_label_data(fdc_id)
    if not food:
        return "Food not found", 404

    typst_content = _generate_typst_content(food, nutrient_info, nutrients_for_label, include_extra_info=True)
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        typ_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.typ")
        pdf_file_path = os.path.join(tmpdir, f"nutrition_label_{fdc_id}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            result = subprocess.run(
                ["typst", "compile", os.path.basename(typ_file_path), os.path.basename(pdf_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            return send_file(pdf_file_path, as_attachment=False, download_name=f"nutrition_label_{fdc_id}.pdf", mimetype='application/pdf')
        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500

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
            result = subprocess.run(
                ["typst", "compile", "--format", "svg", os.path.basename(typ_file_path), os.path.basename(svg_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            return send_file(svg_file_path, as_attachment=False, download_name=f"nutrition_label_{fdc_id}.svg", mimetype='image/svg+xml')
        except subprocess.CalledProcessError as e:
            print(f"Typst compilation failed: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500

def calculate_recipe_nutrition_per_100g(recipe):
    """
    Calculates the nutritional values per 100g for a given recipe.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = sum(ing.amount_grams for ing in recipe.ingredients)

    nutrition_per_100g = {
        'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0
    }

    if total_grams > 0:
        scaling_factor = 100.0 / total_grams
        nutrition_per_100g['calories'] = total_nutrition['calories'] * scaling_factor
        nutrition_per_100g['protein'] = total_nutrition['protein'] * scaling_factor
        nutrition_per_100g['carbs'] = total_nutrition['carbs'] * scaling_factor
        nutrition_per_100g['fat'] = total_nutrition['fat'] * scaling_factor
    
    return nutrition_per_100g


def update_recipe_nutrition(recipe):
    """
    Calculates and updates the nutritional data for a recipe based on its ingredients.
    The session is not committed here.
    """
    total_nutrition = calculate_nutrition_for_items(recipe.ingredients)
    total_grams = sum(ing.amount_grams for ing in recipe.ingredients if ing.amount_grams is not None)

    if total_grams > 0:
        scaling_factor = 100.0 / total_grams
        recipe.calories_per_100g = total_nutrition.get('calories', 0) * scaling_factor
        recipe.protein_per_100g = total_nutrition.get('protein', 0) * scaling_factor
        recipe.carbs_per_100g = total_nutrition.get('carbs', 0) * scaling_factor
        recipe.fat_per_100g = total_nutrition.get('fat', 0) * scaling_factor
        recipe.saturated_fat_per_100g = total_nutrition.get('saturated_fat', 0) * scaling_factor
        recipe.trans_fat_per_100g = total_nutrition.get('trans_fat', 0) * scaling_factor
        recipe.cholesterol_mg_per_100g = total_nutrition.get('cholesterol', 0) * scaling_factor
        recipe.sodium_mg_per_100g = total_nutrition.get('sodium', 0) * scaling_factor
        recipe.fiber_per_100g = total_nutrition.get('fiber', 0) * scaling_factor
        recipe.sugars_per_100g = total_nutrition.get('sugars', 0) * scaling_factor
        recipe.vitamin_d_mcg_per_100g = total_nutrition.get('vitamin_d', 0) * scaling_factor
        recipe.calcium_mg_per_100g = total_nutrition.get('calcium', 0) * scaling_factor
        recipe.iron_mg_per_100g = total_nutrition.get('iron', 0) * scaling_factor
        recipe.potassium_mg_per_100g = total_nutrition.get('potassium', 0) * scaling_factor
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
        'Energy': my_food.calories_per_100g or 0,
        'Total lipid (fat)': my_food.fat_per_100g or 0,
        'Fatty acids, total saturated': my_food.saturated_fat_per_100g or 0,
        'Fatty acids, total trans': my_food.trans_fat_per_100g or 0,
        'Cholesterol': my_food.cholesterol_mg_per_100g or 0,
        'Sodium': my_food.sodium_mg_per_100g or 0,
        'Carbohydrate, by difference': my_food.carbs_per_100g or 0,
        'Fiber, total dietary': my_food.fiber_per_100g or 0,
        'Sugars, total including NLEA': my_food.sugars_per_100g or 0,
        'Sugars, added': 0,  # MyFood model does not have 'added sugars'
        'Protein': my_food.protein_per_100g or 0,
        'Vitamin D': my_food.vitamin_d_mcg_per_100g or 0,
        'Calcium': my_food.calcium_mg_per_100g or 0,
        'Iron': my_food.iron_mg_per_100g or 0,
        'Potassium': my_food.potassium_mg_per_100g or 0,
    }
    return my_food, nutrients_for_label
def _generate_typst_content_myfood(my_food, nutrients_for_label, label_only=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace('\\', r'\\').replace('"', r'\"').replace('*', r'\*')

    # Sanitize all user-provided strings
    sanitized_food_name = _sanitize_for_typst(my_food.description)
    brand_name = "OpenNourish MyFood"
    sanitized_brand = _sanitize_for_typst(brand_name)

    ingredients_str = my_food.ingredients if my_food.ingredients else "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)
    
    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"my_food.upc from DB: {my_food.upc}")
    upc_str = "0" # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if my_food.upc and len(my_food.upc) == 13 and my_food.upc.startswith('200'):
        upc_str = my_food.upc[:12] # Slice off the checksum for the label generator
        current_app.logger.debug(f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}")

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif my_food.upc and len(my_food.upc) == 12:
        upc_str = f"0{my_food.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif my_food.upc and len(my_food.upc) == 13:
        upc_str = my_food.upc[:12]
        current_app.logger.debug(f"Full EAN-13 detected. Using first 12 digits: {upc_str}")

    # Fallback for other lengths
    elif my_food.upc:
        upc_str = my_food.upc.ljust(12, '0')[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(my_food_id=my_food.id).all()
    if food_portions:
        portions_list = [f"{_sanitize_for_typst(p.full_description_str)} ({p.gram_weight}g)" for p in food_portions]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "{nutrients_for_label['Energy']:.0f}",
  total_fat: (value: {nutrients_for_label['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {nutrients_for_label['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {nutrients_for_label['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {nutrients_for_label['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {nutrients_for_label['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {nutrients_for_label['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {nutrients_for_label['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {nutrients_for_label['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {nutrients_for_label['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {nutrients_for_label['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {nutrients_for_label['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {nutrients_for_label['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {nutrients_for_label['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {nutrients_for_label['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if label_only:
        typst_content = typst_content_data + f"""
#set page(width: 2in, height: 1in)
#set page(margin: (x: 0.1cm, y: 0.1cm))
#set text(font: "Liberation Sans", size: 8pt)
#ean13(scale:(1.6, .5), "{upc_str}")
{sanitized_food_name}
"""
    else:
        typst_content = typst_content_data + f"""
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

    return typst_content

def generate_myfood_label_pdf(my_food_id, label_only=False):
    """
    Generates a PDF nutrition label for a MyFood item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    my_food, nutrients_for_label = _get_nutrition_label_data_myfood(my_food_id)
    if not my_food:
        return "Food not found", 404

    typst_content = _generate_typst_content_myfood(my_food, nutrients_for_label, label_only=label_only)
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.typ")
        pdf_file_path = os.path.join(tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                ["typst", "compile", os.path.basename(typ_file_path), "--pages", "1", os.path.basename(pdf_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            download_name = f"{my_food.description}_{file_suffix}.pdf"
            return send_file(pdf_file_path, as_attachment=False, download_name=download_name, mimetype='application/pdf')
        except subprocess.CalledProcessError as e:
            current_app.logger.error(f"Typst compilation failed for my_food_id {my_food_id}: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error("Typst executable not found.")
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500
        
def _generate_typst_content_recipe(recipe, nutrients_for_label, label_only=False):
    def _sanitize_for_typst(text):
        """Sanitizes text to be safely included in Typst markup by escaping special characters."""
        if not isinstance(text, str):
            return text
        return text.replace('\\', r'\\').replace('"', r'\"').replace('*', r'\*')

    # Sanitize all user-provided strings
    sanitized_recipe_name = _sanitize_for_typst(recipe.name)

    # Create a string of ingredients for the recipe
    ingredients_str = ""
    if recipe.ingredients:
        ingredient_names = []
        for ing in recipe.ingredients:
            if ing.fdc_id:
                food = db.session.get(Food, ing.fdc_id)
                if food:
                    ingredient_names.append(food.description)
            elif ing.my_food_id:
                my_food = db.session.get(MyFood, ing.my_food_id)
                if my_food:
                    ingredient_names.append(my_food.description)
            elif ing.recipe_id_link:
                linked_recipe = db.session.get(Recipe, ing.recipe_id_link)
                if linked_recipe:
                    ingredient_names.append(linked_recipe.name)
        ingredients_str = ", ".join(ingredient_names)
    else:
        ingredients_str = "N/A"
    ingredients_str = _sanitize_for_typst(ingredients_str)
    
    # Prepare UPC for EAN-13. The typst ean13 function takes the first 12 digits.
    current_app.logger.debug(f"recipe.upc from DB: {recipe.upc}")
    upc_str = "0" # Default

    # Check for our internal 13-digit UPCs (now stored with checksum)
    if recipe.upc and len(recipe.upc) == 13 and recipe.upc.startswith('201'):
        upc_str = recipe.upc[:12] # Slice off the checksum for the label generator
        current_app.logger.debug(f"Internal EAN-13 detected. Passing first 12 digits to label: {upc_str}")

    # Check for a standard 12-digit UPC-A, which needs a leading '0'
    elif recipe.upc and len(recipe.upc) == 12:
        upc_str = f"0{recipe.upc}"[:12]
        current_app.logger.debug(f"Standard UPC-A detected. Prepending 0: {upc_str}")

    # Handle existing full 13-digit EANs that are NOT our internal ones
    elif recipe.upc and len(recipe.upc) == 13:
        upc_str = recipe.upc[:12]
        current_app.logger.debug(f"Full EAN-13 detected. Using first 12 digits: {upc_str}")

    # Fallback for other lengths
    elif recipe.upc:
        upc_str = recipe.upc.ljust(12, '0')[:12]
        current_app.logger.debug(f"Fallback sizing applied: {upc_str}")

    portions_str = ""
    food_portions = UnifiedPortion.query.filter_by(recipe_id=recipe.id).all()
    if food_portions:
        portions_list = [f"{_sanitize_for_typst(p.full_description_str)} ({p.gram_weight}g)" for p in food_portions]
        portions_str = "\\ ".join(portions_list)
    else:
        portions_str = "N/A"

    typst_content_data = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam
#import "@preview/codetastic:0.2.2": ean13
#let data = (
  servings: "1", // Assuming 1 serving for 100g
  serving_size: "100g",
  calories: "{nutrients_for_label['Energy']:.0f}",
  total_fat: (value: {nutrients_for_label['Total lipid (fat)']:.1f}, unit: "g"),
  saturated_fat: (value: {nutrients_for_label['Fatty acids, total saturated']:.1f}, unit: "g"),
  trans_fat: (value: {nutrients_for_label['Fatty acids, total trans']:.1f}, unit: "g"),
  cholesterol: (value: {nutrients_for_label['Cholesterol']:.0f}, unit: "mg"),
  sodium: (value: {nutrients_for_label['Sodium']:.0f}, unit: "mg"),
  carbohydrate: (value: {nutrients_for_label['Carbohydrate, by difference']:.1f}, unit: "g"),
  fiber: (value: {nutrients_for_label['Fiber, total dietary']:.1f}, unit: "g"),
  sugars: (value: {nutrients_for_label['Sugars, total including NLEA']:.1f}, unit: "g"),
  added_sugars: (value: {nutrients_for_label['Sugars, added']:.1f}, unit: "g"),
  protein: (value: {nutrients_for_label['Protein']:.1f}, unit: "g"),
  micronutrients: (
    (name: "Vitamin D", key: "vitamin_d", value: {nutrients_for_label['Vitamin D']:.0f}, unit: "mcg"),
    (name: "Calcium", key: "calcium", value: {nutrients_for_label['Calcium']:.0f}, unit: "mg"),
    (name: "Iron", key: "iron", value: {nutrients_for_label['Iron']:.1f}, unit: "mg"),
    (name: "Potassium", key: "potassium", value: {nutrients_for_label['Potassium']:.0f}, unit: "mg"),
  ),
)
"""

    if label_only:
        typst_content = typst_content_data + f"""
#set page(width: 2in, height: 1in)
#set page(margin: (x: 0.1cm, y: 0.1cm))
#set text(font: "Liberation Sans", size: 8pt)
#ean13(scale:(1.6, .5), "{upc_str}")
{sanitized_recipe_name}
"""
    else:
        typst_content = typst_content_data + f"""
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

    return typst_content

def generate_myfood_label_pdf(my_food_id, label_only=False):
    """
    Generates a PDF nutrition label for a MyFood item.
    Can generate a label-only PDF or a full-page PDF with additional details.
    """
    my_food, nutrients_for_label = _get_nutrition_label_data_myfood(my_food_id)
    if not my_food:
        return "Food not found", 404

    typst_content = _generate_typst_content_myfood(my_food, nutrients_for_label, label_only=label_only)
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.typ")
        pdf_file_path = os.path.join(tmpdir, f"myfood_label_{my_food.id}_{file_suffix}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                ["typst", "compile", os.path.basename(typ_file_path), "--pages", "1", os.path.basename(pdf_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            download_name = f"{my_food.description}_{file_suffix}.pdf"
            return send_file(pdf_file_path, as_attachment=False, download_name=download_name, mimetype='application/pdf')
        except subprocess.CalledProcessError as e:
            current_app.logger.error(f"Typst compilation failed for my_food_id {my_food_id}: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error("Typst executable not found.")
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500
        
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
        'Energy': recipe.calories_per_100g or 0,
        'Total lipid (fat)': recipe.fat_per_100g or 0,
        'Fatty acids, total saturated': recipe.saturated_fat_per_100g or 0,
        'Fatty acids, total trans': recipe.trans_fat_per_100g or 0,
        'Cholesterol': recipe.cholesterol_mg_per_100g or 0,
        'Sodium': recipe.sodium_mg_per_100g or 0,
        'Carbohydrate, by difference': recipe.carbs_per_100g or 0,
        'Fiber, total dietary': recipe.fiber_per_100g or 0,
        'Sugars, total including NLEA': recipe.sugars_per_100g or 0,
        'Sugars, added': 0,  # Recipe model does not have 'added sugars'
        'Protein': recipe.protein_per_100g or 0,
        'Vitamin D': recipe.vitamin_d_mcg_per_100g or 0,
        'Calcium': recipe.calcium_mg_per_100g or 0,
        'Iron': recipe.iron_mg_per_100g or 0,
        'Potassium': recipe.potassium_mg_per_100g or 0,
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

    typst_content = _generate_typst_content_recipe(recipe, nutrients_for_label, label_only=label_only)
    current_app.logger.debug(f"typst_content: {typst_content}")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_suffix = "label_only" if label_only else "details"
        typ_file_path = os.path.join(tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.typ")
        pdf_file_path = os.path.join(tmpdir, f"recipe_label_{recipe.id}_{file_suffix}.pdf")

        with open(typ_file_path, "w", encoding="utf-8") as f:
            f.write(typst_content)

        try:
            # Run Typst command
            subprocess.run(
                ["typst", "compile", os.path.basename(typ_file_path), "--pages", "1", os.path.basename(pdf_file_path)],
                capture_output=True, text=True, check=True, cwd=tmpdir
            )

            download_name = f"{recipe.name}_{file_suffix}.pdf"
            return send_file(pdf_file_path, as_attachment=False, download_name=download_name, mimetype='application/pdf')
        except subprocess.CalledProcessError as e:
            current_app.logger.error(f"Typst compilation failed for recipe_id {recipe_id}: {e.stderr}")
            return f"Error generating PDF: {e.stderr}", 500
        except FileNotFoundError:
            current_app.logger.error("Typst executable not found.")
            return "Typst executable not found. Please ensure Typst is installed and in your system's PATH.", 500