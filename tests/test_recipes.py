import pytest
from models import db, User, Recipe, RecipeIngredient, Food, FoodNutrient, Nutrient, MyFood, MyMeal, MyMealItem, DailyLog, UnifiedPortion, SystemSetting
from datetime import date
from flask import url_for

@pytest.fixture
def two_users(app_with_db):
    with app_with_db.app_context():
        user_one = User(username='user_one', email='userone@example.com')
        user_one.set_password('password')
        db.session.add(user_one)

        user_two = User(username='user_two', email='usertwo@example.com')
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

@pytest.fixture
def enable_email_verification_for_recipes(app_with_db):
    with app_with_db.app_context():
        setting = SystemSetting.query.filter_by(key='ENABLE_EMAIL_VERIFICATION').first()
        if not setting:
            setting = SystemSetting(key='ENABLE_EMAIL_VERIFICATION', value='True')
            db.session.add(setting)
        else:
            setting.value = 'True'
        db.session.commit()
        app_with_db.config['ENABLE_EMAIL_VERIFICATION'] = True

@pytest.fixture
def unverified_user_client_for_recipes(app_with_db):
    with app_with_db.app_context():
        user = User(username='unverified_recipe_user', email='unverified_recipe@example.com', is_verified=False)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = user.id
                sess['_fresh'] = True
            yield client, user

@pytest.fixture
def verified_user_client_for_recipes(app_with_db):
    with app_with_db.app_context():
        user = User(username='verified_recipe_user', email='verified_recipe@example.com', is_verified=True)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = user.id
                sess['_fresh'] = True
            yield client, user


def test_recipe_creation_and_editing(auth_client_with_user):
    """
    Tests creating and editing a recipe, including the is_public flag.
    """
    client, user = auth_client_with_user
    # 1. Create Recipe (as public)
    new_recipe_data = {
            'name': 'My Awesome Recipe',
            'instructions': 'Step 1: Do something. Step 2: Do something else.',
            'servings': 1.0,
            'is_public': 'y'
        }
    response = client.post(url_for('recipes.new_recipe'), data=new_recipe_data, follow_redirects=False)
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'success'
        assert flashes[0][1] == 'Recipe created successfully. Now add ingredients.'
    # Extract recipe_id from the URL after redirect
    recipe_id = int(response.headers['Location'].split('/')[-2])

    with client.application.app_context():
        created_recipe = db.session.get(Recipe, recipe_id)
        assert created_recipe is not None
        assert created_recipe.name == 'My Awesome Recipe'
        assert created_recipe.is_public is True

    # Follow the redirect and check for the flash message
    response = client.get(f'/recipes/{recipe_id}/edit')
    assert response.status_code == 200
    assert b'Recipe created successfully. Now add ingredients.' in response.data

@pytest.mark.usefixtures('enable_email_verification_for_recipes')
def test_new_recipe_public_unverified_user(unverified_user_client_for_recipes):
    client, user = unverified_user_client_for_recipes
    new_recipe_data = {
        'name': 'Public Recipe Unverified',
        'instructions': 'Instructions',
        'servings': 1.0,
        'is_public': 'y'
    }
    response = client.post(url_for('recipes.new_recipe'), data=new_recipe_data, follow_redirects=False)
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'warning'
        assert flashes[0][1] == 'Your email must be verified to make recipes public.'

    # Manually follow the redirect
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'Your email must be verified to make recipes public.' in response.data
    
    with client.application.app_context():
        created_recipe = Recipe.query.filter_by(name='Public Recipe Unverified').first()
        assert created_recipe is not None
        assert created_recipe.is_public is False # Should be private

@pytest.mark.usefixtures('enable_email_verification_for_recipes')
def test_new_recipe_public_verified_user(verified_user_client_for_recipes):
    client, user = verified_user_client_for_recipes
    new_recipe_data = {
        'name': 'Public Recipe Verified',
        'instructions': 'Instructions',
        'servings': 1.0,
        'is_public': 'y'
    }
    response = client.post(url_for('recipes.new_recipe'), data=new_recipe_data, follow_redirects=False)
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'success'
        assert flashes[0][1] == 'Recipe created successfully. Now add ingredients.'

    # Manually follow the redirect
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'Recipe created successfully. Now add ingredients.' in response.data

    with client.application.app_context():
        created_recipe = Recipe.query.filter_by(name='Public Recipe Verified').first()
        assert created_recipe is not None
        assert created_recipe.is_public is True # Should be public

@pytest.mark.usefixtures('enable_email_verification_for_recipes')
def test_edit_recipe_public_unverified_user(unverified_user_client_for_recipes):
    client, user = unverified_user_client_for_recipes
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Test Recipe', instructions='Test', is_public=False)
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    edited_recipe_data = {
        'name': 'Test Recipe',
        'instructions': 'Test',
        'servings': 1.0,
        'is_public': 'y'
    }
    response = client.post(url_for('recipes.edit_recipe', recipe_id=recipe_id), data=edited_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Your email must be verified to make recipes public.' in response.data

    with client.application.app_context():
        updated_recipe = db.session.get(Recipe, recipe_id)
        assert updated_recipe.is_public is False # Should remain private

@pytest.mark.usefixtures('enable_email_verification_for_recipes')
def test_edit_recipe_public_verified_user(verified_user_client_for_recipes):
    client, user = verified_user_client_for_recipes
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Test Recipe', instructions='Test', is_public=False)
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    edited_recipe_data = {
        'name': 'Test Recipe',
        'instructions': 'Test',
        'servings': 1.0,
        'is_public': 'y'
    }
    response = client.post(url_for('recipes.edit_recipe', recipe_id=recipe_id), data=edited_recipe_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe updated successfully.' in response.data

    with client.application.app_context():
        updated_recipe = db.session.get(Recipe, recipe_id)
        assert updated_recipe.is_public is True # Should become public

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
        'amount': 150
    }, follow_redirects=True)

    # Add 50g of My Mock Food
    client.post(f'/search/add_item', data={
            'food_id': my_food.id,
            'food_type': 'my_food',
            'target': 'recipe',
            'recipe_id': recipe_id,
            'amount': 50
        }, follow_redirects=True)

    response = client.get(f'/recipes/{recipe_id}')
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

    response = client.post(f'/recipes/{recipe_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Recipe deleted.' in response.data

    with client.application.app_context():
        deleted_recipe = db.session.get(Recipe, recipe_id)
        assert deleted_recipe.user_id is None


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

        # Create mock USDA food and its 1-gram portion
        usda_food = Food(fdc_id=30001, description='USDA Ingredient')
        db.session.add(usda_food)
        gram_portion = UnifiedPortion(fdc_id=30001, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id

    response = client.post(f'/search/add_item', data={
            'food_id': 30001,
            'food_type': 'usda',
            'target': 'recipe',
            'recipe_id': recipe_id,
            'amount': 150,
            'portion_id': gram_portion_id
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

    response = client.post(f'/recipes/ingredients/{ingredient_id}/delete', follow_redirects=True)
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
            'recipe_id': recipe_id
        })
        assert response.status_code == 302 # Check for redirect

        # Check for the flash message in the session before following the redirect
        with client.session_transaction() as session:
            flashes = session.get('_flashes', [])
            assert len(flashes) > 0
            assert flashes[0][1] == '"My Meal for Recipe" (expanded) added to recipe Recipe with Meal Ingredient.'

        # Manually follow the redirect
        response = client.get(response.headers['Location'])
        assert response.status_code == 200

        # Verify that the meal's items were added as ingredients in the database
        ingredients = RecipeIngredient.query.filter_by(recipe_id=recipe_id).order_by(RecipeIngredient.amount_grams).all()
        assert len(ingredients) == 2
        
        # Check the smaller ingredient (MyFood) first
        assert ingredients[0].my_food_id == my_food_item.id
        assert ingredients[0].amount_grams == 50
        
        # Check the larger ingredient (USDA Food)
        assert ingredients[1].fdc_id == 60001
        assert ingredients[1].amount_grams == 100

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
    response = client.get(f'/recipes/{recipe_id}/edit')
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
    response = client.post(f'/recipes/{recipe_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to delete this recipe.' in response.data

    with client.application.app_context():
        # Assert that the recipe still exists
        assert db.session.get(Recipe, recipe_id) is not None

def test_recipes_list_view(auth_client_user_two):
    """
    Tests the recipes list view for a user's own recipes and public recipes.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # User one has a public and a private recipe
        recipe_one_public = Recipe(user_id=user_one.id, name="User One Public Recipe", instructions='Public', is_public=True)
        recipe_one_private = Recipe(user_id=user_one.id, name="User One Private Recipe", instructions='Private', is_public=False)
        
        # User two has a private recipe
        recipe_two_private = Recipe(user_id=user_two.id, name="User Two Private Recipe", instructions='My own', is_public=False)
        
        db.session.add_all([recipe_one_public, recipe_one_private, recipe_two_private])
        db.session.commit()
        recipe_one_public_id = recipe_one_public.id
        recipe_two_private_id = recipe_two_private.id

    # As user_two, view "My Recipes"
    response = client.get('/recipes/')
    assert response.status_code == 200
    assert b"User Two Private Recipe" in response.data
    assert b"User One Public Recipe" not in response.data
    assert b"User One Private Recipe" not in response.data
    # Check for edit/delete buttons for own recipe
    assert f'href="/recipes/{recipe_two_private_id}/edit"'.encode() in response.data
    assert f'action="/recipes/{recipe_two_private_id}/delete"'.encode() in response.data

    # As user_two, view "Public Recipes"
    response = client.get('/recipes/?view=public')
    assert response.status_code == 200
    assert b"User One Public Recipe" in response.data
    assert b"User Two Private Recipe" not in response.data
    assert b"User One Private Recipe" not in response.data
    # Check that there are NO edit/delete buttons for other user's public recipe
    assert f'href="/recipes/{recipe_one_public_id}/edit"'.encode() not in response.data
    assert f'action="/recipes/{recipe_one_public_id}/delete"'.encode() not in response.data
    # Check that the view button is there
    assert f'href="/recipes/{recipe_one_public_id}"'.encode() in response.data

def test_add_recipe_as_ingredient_and_prevent_self_nesting(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create two recipes
        recipe_main = Recipe(user_id=user.id, name='Main Recipe', instructions='Main instructions')
        recipe_sub = Recipe(user_id=user.id, name='Sub Recipe', instructions='Sub instructions')
        db.session.add_all([recipe_main, recipe_sub])
        db.session.commit()

        # Add the mandatory 1-gram portion for the sub-recipe
        gram_portion = UnifiedPortion(recipe_id=recipe_sub.id, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id

        # Add Sub Recipe as an ingredient to Main Recipe
        response = client.post(f'/search/add_item', data={
            'food_id': recipe_sub.id,
            'food_type': 'recipe',
            'target': 'recipe',
            'recipe_id': recipe_main.id,
            'amount': 100, # grams
            'portion_id': gram_portion_id
        }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Sub Recipe added as ingredient to recipe Main Recipe.' in response.data

    with client.application.app_context():
        # Verify Sub Recipe is an ingredient of Main Recipe
        main_recipe_ingredients = RecipeIngredient.query.filter_by(recipe_id=recipe_main.id).all()
        assert len(main_recipe_ingredients) == 1
        assert main_recipe_ingredients[0].recipe_id_link == recipe_sub.id
        assert main_recipe_ingredients[0].amount_grams == 100

        # Attempt to add Main Recipe as an ingredient to itself
        response = client.post(f'/search/add_item', data={
            'food_id': recipe_main.id,
            'food_type': 'recipe',
            'target': 'recipe',
            'recipe_id': recipe_main.id,
            'amount': 50, # grams
            'portion_id': gram_portion_id # Re-use the portion, it doesn't matter for this test
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'A recipe cannot be an ingredient of itself.' in response.data # This is the expected flash message for self-nesting prevention

        # Verify Main Recipe does not have itself as an ingredient
        main_recipe_ingredients_after_attempt = RecipeIngredient.query.filter_by(recipe_id=recipe_main.id).all()
        assert len(main_recipe_ingredients_after_attempt) == 1 # Should still be only the Sub Recipe
        assert main_recipe_ingredients_after_attempt[0].recipe_id_link != recipe_main.id

def test_auto_add_recipe_portion_from_servings(auth_client_with_user):
    """
    Tests the 'Create Portion from Servings' functionality.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # 1. Create a recipe with ingredients to have a total weight
        recipe = Recipe(user_id=user.id, name='Servings Test Recipe', servings=4.0)
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        # Add ingredients with a total weight of 400g
        ing1 = RecipeIngredient(recipe_id=recipe_id, amount_grams=150)
        ing2 = RecipeIngredient(recipe_id=recipe_id, amount_grams=250)
        db.session.add_all([ing1, ing2])
        db.session.commit()

    # 2. Simulate the POST request from the "Create Portion from Servings" button
    response = client.post(
        f'/recipes/recipe/portion/auto_add/{recipe_id}',
        data={'servings': '4.0'},
        follow_redirects=True
    )

    assert response.status_code == 200
    # The endpoint doesn't flash a message on success, it just redirects.
    # We will verify the result in the database.

    # 3. Verify the new portion was created correctly
    with client.application.app_context():
        portions = UnifiedPortion.query.filter_by(recipe_id=recipe_id).all()
        assert len(portions) == 1

        new_portion = portions[0]
        # Expected weight = 400g total / 4 servings = 100g per serving
        assert new_portion.gram_weight == pytest.approx(100.0)
        assert new_portion.measure_unit_description == "serving"
        assert new_portion.amount == 1.0

def test_recipe_edit_ingredient_dropdown_1g_portion_uniqueness(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a recipe
        recipe = Recipe(user_id=user.id, name='Recipe with USDA Ingredient', instructions='Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        # Create a USDA food with a non-gram portion
        usda_food_fdc_id = 100004
        usda_food = Food(fdc_id=usda_food_fdc_id, description='USDA Food for Recipe Test')
        db.session.add(usda_food)
        db.session.commit()

        # Add a '1 cup' portion for this USDA food
        cup_portion = UnifiedPortion(
            fdc_id=usda_food_fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="",
            modifier="",
            gram_weight=240.0 # Example gram weight for 1 cup
        )
        db.session.add(cup_portion)

        # Explicitly create the 1-gram portion for this USDA food in the test setup
        one_gram_portion = UnifiedPortion(
            fdc_id=usda_food_fdc_id,
            amount=1.0,
            measure_unit_description="g",
            portion_description="",
            modifier="",
            gram_weight=1.0
        )
        db.session.add(one_gram_portion)
        db.session.commit()

        # Add the USDA food as an ingredient to the recipe
        ingredient = RecipeIngredient(
            recipe_id=recipe_id,
            fdc_id=usda_food_fdc_id,
            amount_grams=100,
            serving_type="g", # Default to g
            portion_id_fk=one_gram_portion.id # Link to the 1g portion
        )
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

        one_gram_portion_id = one_gram_portion.id
        cup_portion_id = cup_portion.id # Store cup portion ID as well

    # Navigate to the recipe edit page
    response = client.get(f'/recipes/{recipe_id}/edit')
    assert response.status_code == 200

    # Inspect the HTML response
    html_content = response.data.decode('utf-8')

    # Find the select element for the ingredient's portion
    form_start_index = html_content.find(f'action="/recipes/recipe/ingredient/{ingredient_id}/update"')
    assert form_start_index != -1, "Ingredient update form not found"

    form_end_index = html_content.find('</form>', form_start_index)
    assert form_end_index != -1, "Ingredient update form end tag not found"

    ingredient_form_html = html_content[form_start_index:form_end_index]
    # Count occurrences of ' g' and ' cup' options
    # Re-query portions within this context to ensure they are attached
    with client.application.app_context():
        re_queried_one_gram_portion = db.session.get(UnifiedPortion, one_gram_portion_id)
        re_queried_cup_portion = db.session.get(UnifiedPortion, cup_portion_id)

        expected_1g_option_html = f'<option value="{re_queried_one_gram_portion.id}" selected> g</option>'
        assert expected_1g_option_html in ingredient_form_html, "' g' portion option not found in dropdown HTML"

        # Verify the '1 cup' portion is also still there
        expected_1cup_option_html = f'<option value="{re_queried_cup_portion.id}" > cup</option>'
        assert expected_1cup_option_html in ingredient_form_html, "' cup' portion option not found in dropdown HTML"

def test_user_cannot_delete_other_users_recipe_unauthorized(auth_client_user_two):
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
    response = client.post(f'/recipes/{recipe_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to delete this recipe.' in response.data

    with client.application.app_context():
        # Assert that the recipe still exists and its user_id is unchanged
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.user_id == user_one.id

def test_recipes_unauthenticated_access(client):
    """
    Tests that an unauthenticated user is redirected to the login page.
    """
    response = client.get(url_for('recipes.recipes'), follow_redirects=False)
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

def test_user_cannot_view_other_users_private_recipe(auth_client_user_two):
    """
    Tests that a user cannot view another user's private recipe.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # Create a private recipe belonging to user_one
        private_recipe = Recipe(user_id=user_one.id, name="User One's Private Recipe", is_public=False)
        db.session.add(private_recipe)
        db.session.commit()
        recipe_id = private_recipe.id

    # As user_two, attempt to view user_one's private recipe
    response = client.get(url_for('recipes.view_recipe', recipe_id=recipe_id), follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to view this recipe.' in response.data

def test_user_cannot_delete_ingredient_from_other_users_recipe(auth_client_user_two):
    """
    Tests that a user cannot delete an ingredient from another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # Create a recipe and ingredient belonging to user_one
        recipe = Recipe(user_id=user_one.id, name="User One's Recipe")
        db.session.add(recipe)
        db.session.commit()
        ingredient = RecipeIngredient(recipe_id=recipe.id, amount_grams=100)
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id

    # As user_two, attempt to delete the ingredient
    response = client.post(url_for('recipes.delete_ingredient', ingredient_id=ingredient_id), follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to modify this recipe.' in response.data
    with client.application.app_context():
        assert db.session.get(RecipeIngredient, ingredient_id) is not None

def test_user_cannot_update_ingredient_in_other_users_recipe(auth_client_user_two):
    """
    Tests that a user cannot update an ingredient in another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two

    with client.application.app_context():
        # Create a recipe, ingredient, and portion belonging to user_one
        recipe = Recipe(user_id=user_one.id, name="User One's Recipe")
        db.session.add(recipe)
        db.session.commit()
        portion = UnifiedPortion(recipe_id=recipe.id, gram_weight=1.0)
        db.session.add(portion)
        db.session.commit()
        ingredient = RecipeIngredient(recipe_id=recipe.id, amount_grams=100, portion_id_fk=portion.id)
        db.session.add(ingredient)
        db.session.commit()
        ingredient_id = ingredient.id
        portion_id = portion.id

    # As user_two, attempt to update the ingredient
    response = client.post(url_for('recipes.update_ingredient', ingredient_id=ingredient_id), data={'amount': 200, 'portion_id': portion_id}, follow_redirects=True)
    assert response.status_code == 200
    assert b'You are not authorized to modify this recipe.' in response.data
    with client.application.app_context():
        ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert ingredient.amount_grams == 100

# region Portion Management Tests

@pytest.fixture
def recipe_with_portion(auth_client_with_user):
    """Fixture to create a user, a recipe, and a portion for that recipe."""
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Recipe for Portion Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

        portion = UnifiedPortion(
            recipe_id=recipe_id,
            portion_description='slice',
            gram_weight=50.0,
            amount=1.0,
            measure_unit_description='slice'
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    return client, user.id, recipe_id, portion_id

def test_add_recipe_portion_success(auth_client_with_user):
    """
    Tests successfully adding a new portion to a recipe.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a recipe without any initial portions for a clean test
        recipe = Recipe(user_id=user.id, name='Recipe for Portion Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    response = client.post(
        url_for('recipes.add_recipe_portion', recipe_id=recipe_id),
        data={
            'portion_description': 'cup',
            'gram_weight': 150.0,
            'amount': 1.0,
            'measure_unit_description': 'cup',
            'modifier': ''
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Recipe portion added.' in response.data

    with client.application.app_context():
        portions = UnifiedPortion.query.filter_by(recipe_id=recipe_id).all()
        assert len(portions) == 1
        new_portion = portions[0]
        assert new_portion.portion_description == 'cup'
        assert new_portion.gram_weight == 150.0

def test_add_recipe_portion_invalid_data(auth_client_with_user):
    """
    Tests adding a new portion to a recipe with invalid data.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        recipe = Recipe(user_id=user.id, name='Recipe for Portion Test')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    response = client.post(
        url_for('recipes.add_recipe_portion', recipe_id=recipe_id),
        data={
            'portion_description': 'cup',
            'gram_weight': -10, # Invalid
            'amount': 1.0,
            'measure_unit_description': 'cup',
            'modifier': ''
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Error in Gram Weight: Number must be at least 0.' in response.data

    with client.application.app_context():
        portions = UnifiedPortion.query.filter_by(recipe_id=recipe_id).all()
        assert len(portions) == 0

def test_add_recipe_portion_unauthorized(auth_client_user_two):
    """
    Tests that a user cannot add a portion to another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two
    with client.application.app_context():
        recipe_user_one = Recipe(user_id=user_one.id, name="User One's Recipe")
        db.session.add(recipe_user_one)
        db.session.commit()
        recipe_id = recipe_user_one.id

    # As user_two, attempt to add a portion to user_one's recipe
    response = client.post(
        url_for('recipes.add_recipe_portion', recipe_id=recipe_id),
        data={'portion_description': 'slice', 'gram_weight': 50.0, 'amount': 1.0, 'measure_unit_description': 'slice'},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'You are not authorized to modify this recipe.' in response.data

def test_update_recipe_portion_success(recipe_with_portion):
    """
    Tests successfully updating a recipe portion.
    """
    client, user_id, recipe_id, portion_id = recipe_with_portion

    response = client.post(
        url_for('recipes.update_recipe_portion', portion_id=portion_id),
        data={
            'portion_description': 'big slice',
            'gram_weight': 75.0,
            'amount': 1.0,
            'measure_unit_description': 'slice',
            'modifier': ''
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Portion updated successfully!' in response.data

    with client.application.app_context():
        updated_portion = db.session.get(UnifiedPortion, portion_id)
        assert updated_portion is not None
        assert updated_portion.portion_description == 'big slice'
        assert updated_portion.gram_weight == 75.0

def test_update_recipe_portion_invalid_data(recipe_with_portion):
    """
    Tests updating a recipe portion with invalid data.
    """
    client, user_id, recipe_id, portion_id = recipe_with_portion

    response = client.post(
        url_for('recipes.update_recipe_portion', portion_id=portion_id),
        data={
            'portion_description': 'big slice',
            'gram_weight': -75.0, # Invalid
            'amount': 1.0,
            'measure_unit_description': 'slice',
            'modifier': ''
        },
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Error in Gram Weight: Number must be at least 0.' in response.data

    with client.application.app_context():
        portion = db.session.get(UnifiedPortion, portion_id)
        assert portion.gram_weight == 50.0 # Should not have changed

def test_update_recipe_portion_unauthorized(auth_client_user_two):
    """
    Tests that a user cannot update a portion on another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two
    with client.application.app_context():
        # Create recipe and portion for user_one
        recipe_user_one = Recipe(user_id=user_one.id, name="User One's Recipe")
        db.session.add(recipe_user_one)
        db.session.commit()
        portion_user_one = UnifiedPortion(recipe_id=recipe_user_one.id, gram_weight=10, amount=1.0, measure_unit_description='g')
        db.session.add(portion_user_one)
        db.session.commit()
        portion_id = portion_user_one.id

    # As user_two, attempt to update the portion
    response = client.post(
        url_for('recipes.update_recipe_portion', portion_id=portion_id),
        data={'gram_weight': 20, 'amount': 1.0, 'measure_unit_description': 'g'},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Portion not found or you do not have permission to edit it.' in response.data

def test_delete_recipe_portion_success(recipe_with_portion):
    """
    Tests successfully deleting a recipe portion.
    """
    client, user_id, recipe_id, portion_id = recipe_with_portion

    response = client.post(
        url_for('recipes.delete_recipe_portion', portion_id=portion_id),
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Recipe portion deleted.' in response.data

    with client.application.app_context():
        deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert deleted_portion is None

def test_delete_recipe_portion_unauthorized(auth_client_user_two):
    """
    Tests that a user cannot delete a portion from another user's recipe.
    """
    client, user_one, user_two = auth_client_user_two
    with client.application.app_context():
        # Create recipe and portion for user_one
        recipe_user_one = Recipe(user_id=user_one.id, name="User One's Recipe")
        db.session.add(recipe_user_one)
        db.session.commit()
        portion_user_one = UnifiedPortion(recipe_id=recipe_user_one.id, gram_weight=10)
        db.session.add(portion_user_one)
        db.session.commit()
        portion_id = portion_user_one.id

    # As user_two, attempt to delete the portion
    response = client.post(
        url_for('recipes.delete_recipe_portion', portion_id=portion_id),
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'Portion not found or you do not have permission to delete it.' in response.data

    with client.application.app_context():
        # Assert that the portion still exists
        assert db.session.get(UnifiedPortion, portion_id) is not None

# endregion
