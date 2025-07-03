from models import db, Food, MyFood, Nutrient
from config import Config

def calculate_nutrition_for_items(items):
    """
    Calculates total nutrition for a list of items (DailyLog or RecipeIngredient).
    """
    totals = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
    
    # Get nutrient IDs for common nutrients to avoid repeated lookups
    # This is a performance optimization
    # Using .first() which is available on the query object
    # The query is constructed by db.session.query(Nutrient)
    # then filtered by .filter(Nutrient.name == name)
    # and finally executed with .first()
    # This is a valid SQLAlchemy pattern
    protein_id = Config.CORE_NUTRIENT_IDS['protein']
    fat_id = Config.CORE_NUTRIENT_IDS['fat']
    carbs_id = Config.CORE_NUTRIENT_IDS['carbs']
    calories_id = Config.CORE_NUTRIENT_IDS['calories']


    for item in items:
        if item.fdc_id:
            food = db.session.get(Food, item.fdc_id)
            if food:
                scaling_factor = item.amount_grams / 100.0
                for nutrient in food.nutrients:
                    if nutrient.nutrient_id == protein_id:
                        totals['protein'] += nutrient.amount * scaling_factor
                    elif nutrient.nutrient_id == fat_id:
                        totals['fat'] += nutrient.amount * scaling_factor
                    elif nutrient.nutrient_id == carbs_id:
                        totals['carbs'] += nutrient.amount * scaling_factor
                    elif nutrient.nutrient_id == calories_id:
                        totals['calories'] += nutrient.amount * scaling_factor
        elif item.my_food_id:
            my_food = db.session.get(MyFood, item.my_food_id)
            if my_food:
                scaling_factor = item.amount_grams / 100.0
                totals['calories'] += my_food.calories_per_100g * scaling_factor
                totals['protein'] += my_food.protein_per_100g * scaling_factor
                totals['carbs'] += my_food.carbs_per_100g * scaling_factor
                totals['fat'] += my_food.fat_per_100g * scaling_factor

    return totals
