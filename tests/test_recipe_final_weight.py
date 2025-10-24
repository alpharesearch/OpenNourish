from datetime import date

import pytest
from models import db, Recipe, RecipeIngredient, MyFood, DailyLog, UnifiedPortion
from opennourish.utils import calculate_nutrition_for_items


def test_diary_logging_with_final_weight(client, auth_client):
    """
    Tests that when a recipe with a final_weight_grams is logged in the diary,
    the nutrition is calculated based on the final_weight_grams, not the sum
    of the ingredients.
    """
    with auth_client.application.app_context():
        # 1. Create a recipe
        recipe = Recipe(
            user_id=1,
            name="Test Recipe with Final Weight",
            servings=1,
            final_weight_grams=150.0,  # Cooked weight is less than raw
        )
        db.session.add(recipe)
        db.session.flush()

        # 2. Create ingredients (raw weight is 100g + 100g = 200g)
        # Ingredient 1: 100g, 100 kcal
        food1 = MyFood(
            user_id=1,
            description="Raw Ingredient 1",
            calories_per_100g=100,
            protein_per_100g=10,
            carbs_per_100g=10,
            fat_per_100g=10,
        )
        db.session.add(food1)
        db.session.flush()
        portion1 = UnifiedPortion(
            my_food_id=food1.id, gram_weight=1.0, measure_unit_description="g"
        )
        db.session.add(portion1)
        db.session.flush()
        ing1 = RecipeIngredient(
            recipe_id=recipe.id,
            my_food_id=food1.id,
            amount_grams=100,
            portion_id_fk=portion1.id,
        )
        db.session.add(ing1)

        # Ingredient 2: 100g, 200 kcal
        food2 = MyFood(
            user_id=1,
            description="Raw Ingredient 2",
            calories_per_100g=200,
            protein_per_100g=20,
            carbs_per_100g=20,
            fat_per_100g=20,
        )
        db.session.add(food2)
        db.session.flush()
        portion2 = UnifiedPortion(
            my_food_id=food2.id, gram_weight=1.0, measure_unit_description="g"
        )
        db.session.add(portion2)
        db.session.flush()
        ing2 = RecipeIngredient(
            recipe_id=recipe.id,
            my_food_id=food2.id,
            amount_grams=100,
            portion_id_fk=portion2.id,
        )
        db.session.add(ing2)

        # Add a portion for the recipe itself
        recipe_portion = UnifiedPortion(
            recipe_id=recipe.id, gram_weight=150.0, measure_unit_description="serving"
        )
        db.session.add(recipe_portion)

        db.session.commit()

        # 3. Log the recipe to the diary - log 75g (half of the final cooked weight)
        log_entry = DailyLog(
            user_id=1,
            recipe_id=recipe.id,
            amount_grams=75.0,
            portion_id_fk=recipe_portion.id,
            log_date=date.today(),
            meal_name="Lunch",
        )
        db.session.add(log_entry)
        db.session.commit()

        # 4. Calculate nutrition for the diary entry
        diary_nutrition = calculate_nutrition_for_items([log_entry])

        # 5. Define expected nutrition
        # Total nutrition of raw ingredients: 300 kcal, 30p, 30c, 30f
        # Final cooked weight: 150g
        # Nutrition per gram of cooked food: 300kcal / 150g = 2 kcal/g
        # We logged 75g, so expected calories = 75g * 2 kcal/g = 150 kcal
        expected_calories = 150.0
        # Protein: (10g + 20g) / 150g * 75g = 15g
        expected_protein = 15.0

        # 6. Assert
        assert diary_nutrition is not None
        assert "calories" in diary_nutrition
        assert "protein" in diary_nutrition
        assert pytest.approx(diary_nutrition["calories"], 0.01) == expected_calories
        assert pytest.approx(diary_nutrition["protein"], 0.01) == expected_protein
