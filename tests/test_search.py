import pytest
from models import db, Food, MyFood, Recipe, MyMeal, User, DailyLog, RecipeIngredient, MyMealItem, Nutrient, FoodNutrient
from datetime import date

@pytest.fixture
def auth_client_with_data(auth_client):
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        if not user:
            user = User(username='testuser')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()

        # Create sample data for testing add_item
        usda_food = Food(fdc_id=100001, description='Test USDA Food')
        db.session.add(usda_food)
        db.session.add(Nutrient(id=1008, name='Energy', unit_name='kcal'))
        db.session.add(FoodNutrient(fdc_id=100001, nutrient_id=1008, amount=100.0)) # 100 kcal/100g

        my_food = MyFood(user_id=user.id, description='Test My Food', calories_per_100g=200)
        db.session.add(my_food)

        recipe = Recipe(user_id=user.id, name='Test Recipe', instructions='Test instructions')
        db.session.add(recipe)

        my_meal = MyMeal(user_id=user.id, name='Test My Meal')
        db.session.add(my_meal)
        db.session.commit()

        # Add items to my_meal for expansion test
        my_meal_item_usda = MyMealItem(my_meal_id=my_meal.id, fdc_id=usda_food.fdc_id, amount_grams=50)
        my_meal_item_my_food = MyMealItem(my_meal_id=my_meal.id, my_food_id=my_food.id, amount_grams=30)
        db.session.add_all([my_meal_item_usda, my_meal_item_my_food])
        db.session.commit()

        # Create a target recipe for adding ingredients
        target_recipe = Recipe(user_id=user.id, name='Target Recipe', instructions='Target instructions')
        db.session.add(target_recipe)
        db.session.commit()

        # Create a target meal for adding items
        target_meal = MyMeal(user_id=user.id, name='Target Meal')
        db.session.add(target_meal)
        db.session.commit()

    return auth_client

def test_search_page_loads(auth_client):
    response = auth_client.get('/search/')
    assert response.status_code == 200

def test_search_finds_all_food_types(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        # Create one of each food type with a unique keyword
        usda_food = Food(fdc_id=99999, description='SearchUSDAFood')
        my_food = MyFood(user_id=user.id, description='SearchMyFood', calories_per_100g=100)
        recipe = Recipe(user_id=user.id, name='SearchRecipe', instructions='Test')
        my_meal = MyMeal(user_id=user.id, name='SearchMyMeal')

        db.session.add_all([usda_food, my_food, recipe, my_meal])
        db.session.commit()

    search_term = 'Search'
    response = auth_client.post('/search/', data={'search_term': search_term})
    assert response.status_code == 200

    # Assert that all four items appear in the response
    assert b'SearchUSDAFood' in response.data
    assert b'SearchMyFood' in response.data
    assert b'SearchRecipe' in response.data
    assert b'SearchMyMeal' in response.data

def test_search_preserves_context(auth_client):
    target_value = 'diary'
    recipe_id_value = '123'
    response = auth_client.get(f'/search/?target={target_value}&recipe_id={recipe_id_value}')
    assert response.status_code == 200

    # Assert that the rendered template's HTML contains these values in hidden form fields
    assert f'name="target" value="{target_value}"'.encode('utf-8') in response.data
    assert f'name="recipe_id" value="{recipe_id_value}"'.encode('utf-8') in response.data

def test_add_item_to_diary(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        usda_food = Food.query.filter_by(description='Test USDA Food').first()
        log_date_str = date.today().isoformat()

    # Add USDA Food to diary
    response = auth_client.post('/search/add_item', data={
        'food_id': usda_food.fdc_id,
        'food_type': 'usda',
        'target': 'diary',
        'log_date': log_date_str,
        'meal_name': 'Breakfast',
        'quantity': 150
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test USDA Food added to your diary.' in response.data

    with auth_client.application.app_context():
        daily_log = DailyLog.query.filter_by(user_id=user.id, fdc_id=usda_food.fdc_id, log_date=date.today()).first()
        assert daily_log is not None
        assert daily_log.amount_grams == 150

def test_add_item_to_recipe(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(description='Test My Food').first()
        target_recipe = Recipe.query.filter_by(name='Target Recipe').first()

    # Add MyFood to recipe
    response = auth_client.post('/search/add_item', data={
        'food_id': my_food.id,
        'food_type': 'my_food',
        'target': 'recipe',
        'recipe_id': target_recipe.id,
        'quantity': 75
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test My Food added to recipe Target Recipe.' in response.data

    with auth_client.application.app_context():
        recipe_ingredient = RecipeIngredient.query.filter_by(recipe_id=target_recipe.id, my_food_id=my_food.id).first()
        assert recipe_ingredient is not None
        assert recipe_ingredient.amount_grams == 75

def test_add_item_to_meal(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        recipe = Recipe.query.filter_by(name='Test Recipe').first()
        target_meal = MyMeal.query.filter_by(name='Target Meal').first()

    # Add Recipe to meal
    response = auth_client.post('/search/add_item', data={
        'food_id': recipe.id,
        'food_type': 'recipe',
        'target': 'meal',
        'recipe_id': target_meal.id, # Using recipe_id for my_meal_id in this context
        'quantity': 2 # servings
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test Recipe added to meal Target Meal.' in response.data

    with auth_client.application.app_context():
        my_meal_item = MyMealItem.query.filter_by(my_meal_id=target_meal.id, recipe_id=recipe.id).first()
        assert my_meal_item is not None
        assert my_meal_item.amount_grams == 2 # Should be servings for recipe

def test_add_meal_expands_correctly(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_meal = MyMeal.query.filter_by(name='Test My Meal').first()
        usda_food = Food.query.filter_by(description='Test USDA Food').first()
        my_food = MyFood.query.filter_by(description='Test My Food').first()
        log_date_str = date.today().isoformat()

    # Add MyMeal to diary, expecting expansion
    response = auth_client.post('/search/add_item', data={
        'food_id': my_meal.id,
        'food_type': 'my_meal',
        'target': 'diary',
        'log_date': log_date_str,
        'meal_name': 'Lunch',
        'quantity': 200 # This quantity should scale the meal items
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test My Meal (expanded) added to your diary.' in response.data

    with auth_client.application.app_context():
        # Check if individual items from MyMeal were added to DailyLog
        usda_log_entry = DailyLog.query.filter_by(user_id=user.id, fdc_id=usda_food.fdc_id, log_date=date.today()).first()
        my_food_log_entry = DailyLog.query.filter_by(user_id=user.id, my_food_id=my_food.id, log_date=date.today()).first()

        assert usda_log_entry is not None
        assert my_food_log_entry is not None

        # Assert scaled quantities (original amount_grams * (quantity / 100))
        # Original usda_food in meal: 50g. Scaled by 200/100 = 2. Expected: 100g
        assert usda_log_entry.amount_grams == 50 * (200 / 100)
        # Original my_food in meal: 30g. Scaled by 200/100 = 2. Expected: 60g
        assert my_food_log_entry.amount_grams == 30 * (200 / 100)

def test_search_result_includes_details_link_for_usda_food(auth_client_with_data):
    auth_client = auth_client_with_data
    usda_food_fdc_id = 0 # Initialize outside context
    with auth_client.application.app_context():
        usda_food_fdc_id = 100002
        usda_food = Food(fdc_id=usda_food_fdc_id, description='Details USDA Food')
        db.session.add(usda_food)
        db.session.commit()

    search_term = 'Details USDA Food'
    response = auth_client.get(f'/search/?search_term={search_term}')
    assert response.status_code == 200
    assert f'href="/food/{usda_food_fdc_id}"' in response.data.decode('utf-8')
