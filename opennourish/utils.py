from models import db, Food, MyFood, Nutrient, FoodNutrient
from config import Config

def calculate_nutrition_for_items(items):
    """
    Calculates total nutrition for a list of items (DailyLog or RecipeIngredient).
    """
    totals = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
    
    # Get nutrient IDs for common nutrients to avoid repeated lookups
    protein_id = Config.CORE_NUTRIENT_IDS['protein']
    fat_id = Config.CORE_NUTRIENT_IDS['fat']
    carbs_id = Config.CORE_NUTRIENT_IDS['carbs']
    calories_id = Config.CORE_NUTRIENT_IDS['calories']


    for item in items:
        if item.fdc_id:
            food = db.session.get(Food, item.fdc_id)
            if food:
                scaling_factor = item.amount_grams / 100.0
                
                calories_nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=food.fdc_id, nutrient_id=calories_id).first()
                protein_nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=food.fdc_id, nutrient_id=protein_id).first()
                carbs_nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=food.fdc_id, nutrient_id=carbs_id).first()
                fat_nutrient = db.session.query(FoodNutrient).filter_by(fdc_id=food.fdc_id, nutrient_id=fat_id).first()

                if calories_nutrient: totals['calories'] += calories_nutrient.amount * scaling_factor
                if protein_nutrient: totals['protein'] += protein_nutrient.amount * scaling_factor
                if carbs_nutrient: totals['carbs'] += carbs_nutrient.amount * scaling_factor
                if fat_nutrient: totals['fat'] += fat_nutrient.amount * scaling_factor

        elif item.my_food_id:
            my_food = db.session.get(MyFood, item.my_food_id)
            if my_food:
                scaling_factor = item.amount_grams / 100.0
                totals['calories'] += my_food.calories_per_100g * scaling_factor
                totals['protein'] += my_food.protein_per_100g * scaling_factor
                totals['carbs'] += my_food.carbs_per_100g * scaling_factor
                totals['fat'] += my_food.fat_per_100g * scaling_factor

    return totals
