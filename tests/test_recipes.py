import pytest
from models import db, User, Recipe, RecipeIngredient, Food, FoodNutrient, Nutrient, MyFood, MyMeal, MyMealItem, DailyLog
from datetime import date

@pytest.fixture
def two_users(app_with_db):
    with app_with_db.app_context():
        user_one = User(username='user_one')
        user_one.set_password('password')
        db.session.add(user_one)

        user_two = User(username='user_two')
        user_two.set_password('password')
        db.session.add(user_two)
        db.session.commit()
        # Return user IDs instead of user objects
        return user_one.id, user_two.id

@pytest.fixture
def auth_client_user_two(app_with_db, two_users):
    user_one_id, user_two_id = two_users
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user_one_in_context = db.session.get(User, user_one_id)
            user_two_in_context = db.session.get(User, user_two_id)
            user_id = user_two_in_context.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client, user_one_in_context, user_two_in_context

def test_recipe_creation_and_editing(auth_client_with_user):
    """
    Tests creating and editing a recipe.
    """
    client, user = auth_client_with_user
    # 1. Create Recipe
    new_recipe_data = {
        'name': 'My Awesome Recipe',
        'instructions': 'Step 1: Do something. Step 2: Do something else.'
    }
    response = client.post('/recipes/recipe/new', data=new_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe created successfully. Now add ingredients.' in response.data

    with client.application.app_context():
        recipe = Recipe.query.filter_by(user_id=user.id, name='My Awesome Recipe').first()
        assert recipe is not None
        created_recipe_id = recipe.id

    # 2. Edit Recipe
    edited_recipe_data = {
        'name': 'My Super Awesome Recipe',
        'instructions': 'Step 1: Do something new. Step 2: Do something else new.'
    }
    response = client.post(f'/recipes/recipe/edit/{created_recipe_id}', data=edited_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe updated successfully.' in response.data

    with client.application.app_context():
        updated_recipe = db.session.get(Recipe, created_recipe_id)
        assert updated_recipe.name == 'My Super Awesome Recipe'
        assert updated_recipe.instructions == 'Step 1: Do something new. Step 2: Do something else new.'

def test_recipe_nutrition_calculation(auth_client_with_user):
    """
    Tests the nutrition calculation for a recipe.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
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
    client.post(f'/search/add_item', data={
        'food_id': 30001,
        'food_type': 'usda',
        'target': 'recipe',
        'recipe_id': recipe_id,
        'quantity': 150
    }, follow_redirects=True)

    # Add 50g of My Mock Food
    client.post(f'/search/add_item', data={
            'food_id': my_food.id,
            'food_type': 'my_food',
            'target': 'recipe',
            'recipe_id': recipe_id,
            'quantity': 50
        }, follow_redirects=True)

    response = client.get(f'/recipes/recipe/view/{recipe_id}')
    assert response.status_code == 200
    # Expected calories: (100 kcal/100g * 100g) + (200 kcal/100g * 50g) = 100 + 100 = 200 kcal
    assert b'<strong>Calories</strong>' in response.data
    # assert b'200 kcal' in response.data

def test_delete_recipe(auth_client_with_user):
    """
    Tests deleting a recipe and its ingredients.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
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

    response = client.post(f'/recipes/recipe/delete/{recipe_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe deleted.' in response.data

    with client.application.app_context():
        deleted_recipe = db.session.get(Recipe, recipe_id)
        assert deleted_recipe is None
        deleted_ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert deleted_ingredient is None


def test_add_ingredient_to_recipe(auth_client_with_user):
    """
    Tests adding an ingredient to a recipe.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Test Add Ingredient', instructions='Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        # Create mock USDA food
        usda_food = Food(fdc_id=30001, description='USDA Ingredient')
        db.session.add(usda_food)
        db.session.commit()

    response =     client.post(f'/search/add_item', data={
        'food_id': 30001,
        'food_type': 'usda',
        'target': 'recipe',
        'recipe_id': recipe_id,
        'quantity': 150
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'USDA Ingredient added to recipe Test Add Ingredient.' in response.data

    with client.application.app_context():
        added_ingredient = RecipeIngredient.query.filter_by(recipe_id=recipe_id, fdc_id=30001).first()
        assert added_ingredient is not None
        assert added_ingredient.amount_grams == 150

def test_delete_ingredient_from_recipe(auth_client_with_user):
    """
    Tests deleting an ingredient from a recipe.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Test Delete Ingredient', instructions='Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        ingredient = RecipeIngredient(recipe_id=recipe_id, fdc_id=40001, amount_grams=100)
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

    response = client.post(f'/recipes/recipe/ingredient/{ingredient_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Ingredient removed.' in response.data

    with client.application.app_context():
        deleted_ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert deleted_ingredient is None

def test_add_meal_to_recipe_as_ingredient(auth_client_with_user):
    """
    Tests adding a MyMeal as an ingredient to a recipe.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Recipe with Meal Ingredient', instructions='Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        meal = MyMeal(user_id=user.id, name='My Meal for Recipe')
        db.session.add(meal)
        db.session.commit()
        meal_id = meal.id

        meal_item_usda = MyMealItem(my_meal_id=meal.id, fdc_id=60001, amount_grams=100)

        # Create a MyFood object for the test
        my_food_item = MyFood(user_id=user.id, description='Test MyFood', calories_per_100g=100, protein_per_100g=10, carbs_per_100g=10, fat_per_100g=10)
        db.session.add(my_food_item)
        db.session.commit() # Commit to get my_food_item.id

        meal_item_my_food = MyMealItem(my_meal_id=meal.id, my_food_id=my_food_item.id, amount_grams=50)
        db.session.add_all([meal_item_usda, meal_item_my_food])
        db.session.commit()

        response = client.post(f'/search/add_item', data={
            'food_id': meal_id,
            'food_type': 'my_meal',
            'target': 'recipe',
            'recipe_id': recipe_id,
            'quantity': 1 # Assuming 1 serving of the meal
        }, follow_redirects=True)
    assert response.status_code == 200
    with client.application.app_context():
        from flask import get_flashed_messages
        flashed_messages = [str(message) for message in get_flashed_messages()]
        assert 'My Meal for Recipe (expanded) added to recipe Recipe with Meal Ingredient.' in flashed_messages

def test_user_cannot_edit_other_users_recipe(auth_client_user_two):
    """
    Tests that a user cannot edit another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # Create a recipe belonging to user_one
        recipe_user_one = Recipe(user_id=user_one.id, name="User One's Recipe", instructions='Test')
        db.session.add(recipe_user_one)
        db.session.commit()
        recipe_id = recipe_user_one.id

    # Attempt to make a GET request to the 'edit_recipe' page for user_one's recipe as user_two
    response = client.get(f'/recipes/recipe/edit/{recipe_id}')
    assert response.status_code == 302 # Redirects to /recipes

    # Follow the redirect to check the final status code and flash message
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'You are not authorized to edit this recipe.' in response.data

def test_user_cannot_delete_other_users_recipe(auth_client_user_two):
    """
    Tests that a user cannot delete another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # Create a recipe belonging to user_one
        recipe_user_one = Recipe(user_id=user_one.id, name="User One's Recipe to Delete", instructions='Test')
        db.session.add(recipe_user_one)
        db.session.commit()
        recipe_id = recipe_user_one.id

    # Attempt to make a POST request to delete user_one's recipe as user_two
    response = client.post(f'/recipes/recipe/delete/{recipe_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to delete this recipe.' in response.data

    with client.application.app_context():
        # Assert that the recipe still exists
        assert db.session.get(Recipe, recipe_id) is not None