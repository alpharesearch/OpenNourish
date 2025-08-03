import pytest
from models import db, Recipe, RecipeIngredient, MyFood, User
from opennourish.utils import update_recipe_nutrition


@pytest.fixture
def client_with_recipe(client):
    recipe_id = None
    with client.application.app_context():
        user = User(username="testuser_recipe_nutrition", email="testuser@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()

        client.post(
            "/auth/login",
            data={"username": "testuser_recipe_nutrition", "password": "password"},
        )

        recipe = Recipe(user_id=user.id, name="Test Recipe", servings=2)
        db.session.add(recipe)
        db.session.commit()

        my_food1 = MyFood(
            user_id=user.id,
            description="Chicken Breast",
            calories_per_100g=165,
            protein_per_100g=31,
            carbs_per_100g=0,
            fat_per_100g=3.6,
        )
        db.session.add(my_food1)

        my_food2 = MyFood(
            user_id=user.id,
            description="Broccoli",
            calories_per_100g=55,
            protein_per_100g=3.7,
            carbs_per_100g=11.2,
            fat_per_100g=0.6,
        )
        db.session.add(my_food2)
        db.session.commit()

        ingredient1 = RecipeIngredient(
            recipe_id=recipe.id, my_food_id=my_food1.id, amount_grams=200
        )
        ingredient2 = RecipeIngredient(
            recipe_id=recipe.id, my_food_id=my_food2.id, amount_grams=150
        )
        db.session.add_all([ingredient1, ingredient2])
        db.session.commit()
        recipe_id = recipe.id

    return client, recipe_id


def test_update_recipe_nutrition(client_with_recipe):
    client, recipe_id = client_with_recipe

    with client.application.app_context():
        # Reload the recipe to ensure we have the latest data
        recipe = db.session.get(Recipe, recipe_id)

        # Call the function to update the recipe's nutrition
        update_recipe_nutrition(recipe)
        db.session.commit()

        # Reload the recipe again to get the updated values
        updated_recipe = db.session.get(Recipe, recipe_id)

        # Expected values:
        # Chicken: 200g -> 165*2=330 cal, 31*2=62g pro, 3.6*2=7.2g fat
        # Broccoli: 150g -> 55*1.5=82.5 cal, 3.7*1.5=5.55g pro, 11.2*1.5=16.8g carb, 0.6*1.5=0.9g fat
        # Total grams: 350g
        # Total nutrition: 412.5 cal, 67.55g pro, 16.8g carb, 8.1g fat
        # Per 100g: 412.5/3.5=117.857 cal, 67.55/3.5=19.3g pro, 16.8/3.5=4.8g carb, 8.1/3.5=2.31g fat

        assert updated_recipe.calories_per_100g == pytest.approx(117.857, 0.01)
        assert updated_recipe.protein_per_100g == pytest.approx(19.3, 0.01)
        assert updated_recipe.carbs_per_100g == pytest.approx(4.8, 0.01)
        assert updated_recipe.fat_per_100g == pytest.approx(2.31, 0.01)
