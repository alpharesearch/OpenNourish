import pytest
from models import db, User, Recipe, RecipeIngredient, Food, FoodNutrient, Nutrient, MyFood
from datetime import date

def test_recipe_creation_and_editing(auth_client):
    """
    Tests creating and editing a recipe.
    """
    # 1. Create Recipe
    new_recipe_data = {
        'name': 'My Awesome Recipe',
        'instructions': 'Step 1: Do something. Step 2: Do something else.'
    }
    response = auth_client.post('/recipes/recipe/new', data=new_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe created successfully. Now add ingredients.' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        recipe = Recipe.query.filter_by(user_id=user.id, name='My Awesome Recipe').first()
        assert recipe is not None
        created_recipe_id = recipe.id

    # 2. Edit Recipe
    edited_recipe_data = {
        'name': 'My Super Awesome Recipe',
        'instructions': 'Step 1: Do something new. Step 2: Do something else new.'
    }
    response = auth_client.post(f'/recipes/recipe/edit/{created_recipe_id}', data=edited_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe updated successfully.' in response.data

    with auth_client.application.app_context():
        updated_recipe = db.session.get(Recipe, created_recipe_id)
        assert updated_recipe.name == 'My Super Awesome Recipe'
        assert updated_recipe.instructions == 'Step 1: Do something new. Step 2: Do something else new.'

def test_recipe_nutrition_calculation(auth_client):
    """
    Tests the nutrition calculation for a recipe.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        recipe = Recipe(user_id=user.id, name='Nutrient Test Recipe', instructions='Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        # Create mock USDA food
        usda_food = Food(fdc_id=20001, description='USDA Mock Food')
        db.session.add(usda_food)
        db.session.add(Nutrient(id=1008, name='Energy', unit_name='kcal'))
        db.session.add(FoodNutrient(fdc_id=20001, nutrient_id=1008, amount=100.0)) # 100 kcal/100g
        db.session.commit()

        # Create mock MyFood
        my_food = MyFood(
            user_id=user.id,
            description='My Mock Food',
            calories_per_100g=200.0,
            protein_per_100g=10.0,
            carbs_per_100g=20.0,
            fat_per_100g=5.0
        )
        db.session.add(my_food)
        db.session.commit()
        my_food_id = my_food.id

    # Add 100g of USDA Mock Food
    auth_client.post(f'/recipes/recipe/{recipe_id}/add_ingredient', data={
        'food_id': 20001,
        'food_type': 'usda',
        'amount': 100
    }, follow_redirects=True)

    # Add 50g of My Mock Food
    auth_client.post(f'/recipes/recipe/{recipe_id}/add_ingredient', data={
        'food_id': my_food.id,
        'food_type': 'my_food',
        'amount': 50
    }, follow_redirects=True)

    response = auth_client.get(f'/recipes/recipe/view/{recipe_id}')
    assert response.status_code == 200
    # Expected calories: (100 kcal/100g * 100g) + (200 kcal/100g * 50g) = 100 + 100 = 200 kcal
    assert b'Calories: 200' in response.data

def test_delete_recipe(auth_client):
    """
    Tests deleting a recipe and its ingredients.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        recipe_to_delete = Recipe(user_id=user.id, name='Recipe to Delete', instructions='Delete me!')
        db.session.add(recipe_to_delete)
        db.session.commit()
        recipe_id = recipe_to_delete.id

        # Add an ingredient to the recipe
        ingredient = RecipeIngredient(
            recipe_id=recipe_id,
            fdc_id=10001, # Use a dummy fdc_id
            amount_grams=100
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

    response = auth_client.post(f'/recipes/recipe/delete/{recipe_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe deleted.' in response.data

    with auth_client.application.app_context():
        deleted_recipe = db.session.get(Recipe, recipe_id)
        assert deleted_recipe is None
        deleted_ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert deleted_ingredient is None
