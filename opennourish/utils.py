from models import db, Food, MyFood, Nutrient, FoodNutrient, Recipe
from sqlalchemy.orm import selectinload
from config import Config
from flask import send_file
import subprocess
import tempfile
import os
from types import SimpleNamespace

def get_available_portions(food_item):
    available_portions = []
    # Always add grams as an option
    available_portions.append(SimpleNamespace(id='g', display_text='g', value_string='g'))

    if food_item:
        if hasattr(food_item, 'portions'): # USDA Food or MyFood
            for p in food_item.portions:
                # Determine the correct description attribute based on object type
                if hasattr(p, 'portion_description') and p.portion_description: # This is a USDA Portion
                    desc = p.portion_description
                    # Add amount and measure unit for USDA portions
                    if p.amount and p.measure_unit:
                        desc = f"{p.amount} {p.measure_unit.name} {desc}"
                    if p.modifier:
                        desc = f"{desc} ({p.modifier})"
                elif hasattr(p, 'description'): # This is a MyPortion or RecipePortion
                    desc = p.description
                else:
                    desc = "" # Fallback if neither exists (shouldn't happen with current models)

                display_text = f"{desc or ''} ({p.gram_weight}g)"
                available_portions.append(SimpleNamespace(id=p.id, display_text=display_text, value_string=display_text))
        elif hasattr(food_item, 'recipe_portions'): # Recipe
            for p in food_item.recipe_portions:
                display_text = f"{p.description} ({p.gram_weight}g)"
                available_portions.append(SimpleNamespace(id=p.id, display_text=display_text, value_string=display_text))
    return available_portions

def calculate_nutrition_for_items(items):
    """
    Calculates total nutrition for a list of items (DailyLog or RecipeIngredient).
    """
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
                # Calculate nutrition for the nested recipe's ingredients
                nested_nutrition = calculate_nutrition_for_items(nested_recipe.ingredients)
                
                # Determine the scaling factor for the nested recipe
                # item.amount_grams is the total grams of the nested recipe as an ingredient
                # We need to find the total grams of the nested recipe itself.
                total_nested_recipe_grams = sum(ing.amount_grams for ing in nested_recipe.ingredients)

                if total_nested_recipe_grams > 0:
                    # Scale based on the actual grams of the nested recipe used as an ingredient
                    scaling_factor = item.amount_grams / total_nested_recipe_grams
                else:
                    # If nested recipe has no grams, or is 0, then it contributes no nutrition
                    scaling_factor = 0

                for key, value in nested_nutrition.items():
                    totals[key] += value * scaling_factor

    return totals

def generate_nutrition_label_pdf(fdc_id):
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404

    # Map common nutrition label fields to USDA nutrient names and their units
    nutrient_info = {
        "Energy": {"names": ["Energy", "Energy (Atwater General Factors)"], "unit": "kcal", "format": ".0f"},
        "Total lipid (fat)": {"names": ["Total lipid (fat)"], "unit": "g", "format": ".1f"},
        "Fatty acids, total saturated": {"names": ["Fatty acids, total saturated"], "unit": "g", "format": ".1f"},
        "Fatty acids, total trans": {"names": ["Fatty acids, total trans"], "unit": "g", "format": ".1f"},
        "Cholesterol": {"names": ["Cholesterol"], "unit": "mg", "format": ".0f"},
        "Sodium": {"names": ["Sodium"], "unit": "mg", "format": ".0f"},
        "Carbohydrate, by difference": {"names": ["Carbohydrate, by difference"], "unit": "g", "format": ".1f"},
        "Fiber, total dietary": {"names": ["Fiber, total dietary"], "unit": "g", "format": ".1f"},
        "Sugars, total including NLEA": {"names": ["Sugars, total including NLEA"], "unit": "g", "format": ".1f"},
        "Protein": {"names": ["Protein"], "unit": "g", "format": ".1f"},
        "Vitamin D (D2 + D3)": {"names": ["Vitamin D (D2 + D3)"], "unit": "mcg", "format": ".0f", "key": "vitamin_d"},
        "Calcium": {"names": ["Calcium"], "unit": "mg", "format": ".0f", "key": "calcium"},
        "Iron": {"names": ["Iron"], "unit": "mg", "format": ".1f", "key": "iron"},
        "Potassium": {"names": ["Potassium"], "unit": "mg", "format": ".0f", "key": "potassium"},
        "Vitamin A, RAE": {"names": ["Vitamin A, RAE"], "unit": "mcg", "format": ".0f", "key": "vitamin_a"},
        "Vitamin C, total ascorbic acid": {"names": ["Vitamin C, total ascorbic acid"], "unit": "mg", "format": ".0f", "key": "vitamin_c"}
    }

    # Extract nutrient values
    nutrients_for_label = {}
    for label_field, info in nutrient_info.items():
        found_value = 0.0
        for usda_name in info["names"]:
            for fn in food.nutrients:
                if fn.nutrient.name == usda_name:
                    found_value = fn.amount
                    break
            if found_value > 0:
                break
        nutrients_for_label[label_field] = found_value

    # Prepare data for Typst
    # Construct the micronutrients array for Typst
    micronutrients_typst = []
    for label_field, info in nutrient_info.items():
        if "key" in info: # These are micronutrients
            value = nutrients_for_label[label_field]
            micronutrients_typst.append(                    f"(name: \"{label_field}\", key: \"{info['key']}\", value: {value}, unit: \"{info['unit']}\", dv: 0)"
            )

    # Join micronutrients for Typst array syntax
    micronutrients_typst_str = ",\n    ".join(micronutrients_typst)

    typst_content = f"""
#import "@preview/nutrition-label-nam:0.2.0": nutrition-label-nam

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
  added_sugars: (value: 0, unit: "g"), // Assuming no added sugars data for now
  protein: (value: {nutrients_for_label['Protein']:{nutrient_info['Protein']['format']}}, unit: "{nutrient_info['Protein']['unit']}"),
  micronutrients: (
    {micronutrients_typst_str}
  ),
)

#show: nutrition-label-nam(data)

#align(center, text(20pt, "Nutrition Facts for {food.description}"))

"""
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