import pytest
from models import db, Food, MyFood, Recipe, MyMeal, User, DailyLog, RecipeIngredient, MyMealItem, Nutrient, FoodNutrient, UnifiedPortion
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
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(fdc_id=usda_food.fdc_id, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id
        usda_food_id = usda_food.fdc_id
        user_id = user.id

    # Add USDA Food to diary
    response = auth_client.post('/search/add_item', data={
        'food_id': usda_food_id,
        'food_type': 'usda',
        'target': 'diary',
        'log_date': log_date_str,
        'meal_name': 'Breakfast',
        'amount': 150,
        'portion_id': gram_portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test USDA Food added to your diary.' in response.data

    with auth_client.application.app_context():
        daily_log = DailyLog.query.filter_by(user_id=user_id, fdc_id=usda_food_id, log_date=date.today()).first()
        assert daily_log is not None
        assert daily_log.amount_grams == 150

def test_add_item_to_recipe(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(description='Test My Food').first()
        target_recipe = Recipe.query.filter_by(name='Target Recipe').first()
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(my_food_id=my_food.id, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id
        my_food_id = my_food.id
        target_recipe_id = target_recipe.id

    # Add MyFood to recipe
    response = auth_client.post('/search/add_item', data={
        'food_id': my_food_id,
        'food_type': 'my_food',
        'target': 'recipe',
        'recipe_id': target_recipe_id,
        'amount': 75,
        'portion_id': gram_portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test My Food added to recipe Target Recipe.' in response.data

    with auth_client.application.app_context():
        recipe_ingredient = RecipeIngredient.query.filter_by(recipe_id=target_recipe_id, my_food_id=my_food_id).first()
        assert recipe_ingredient is not None
        assert recipe_ingredient.amount_grams == 75

def test_add_item_to_meal(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        recipe = Recipe.query.filter_by(name='Test Recipe').first()
        target_meal = MyMeal.query.filter_by(name='Target Meal').first()
        # Add a portion for the recipe
        portion = UnifiedPortion(recipe_id=recipe.id, portion_description='serving', gram_weight=150.0)
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id
        recipe_id = recipe.id
        target_meal_id = target_meal.id

    # Add Recipe to meal
    response = auth_client.post('/search/add_item', data={
        'food_id': recipe_id,
        'food_type': 'recipe',
        'target': 'meal',
        'recipe_id': target_meal_id, # Using recipe_id for my_meal_id in this context
        'amount': 2, # servings
        'portion_id': portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Test Recipe added to meal Target Meal.' in response.data

    with auth_client.application.app_context():
        my_meal_item = MyMealItem.query.filter_by(my_meal_id=target_meal_id, recipe_id=recipe_id).first()
        assert my_meal_item is not None
        assert my_meal_item.amount_grams == 300 # 2 servings * 150g/serving

def test_add_meal_expands_correctly(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_meal = MyMeal.query.filter_by(name='Test My Meal').first()
        usda_food = Food.query.filter_by(description='Test USDA Food').first()
        my_food = MyFood.query.filter_by(description='Test My Food').first()
        log_date_str = date.today().isoformat()
        my_meal_id = my_meal.id
        # Add MyMeal to diary, expecting expansion
        response = auth_client.post('/search/add_item', data={
            'food_id': my_meal_id,
            'food_type': 'my_meal',
            'target': 'diary',
            'log_date': log_date_str,
            'meal_name': 'Lunch'
        })
        assert response.status_code == 302 # Check for redirect

        # Check for the flash message in the session before following the redirect
        with auth_client.session_transaction() as session:
            flashes = session.get('_flashes', [])
            assert len(flashes) > 0
            assert flashes[0][1] == '"Test My Meal" (expanded) added to your diary.'

        # Manually follow the redirect
        response = auth_client.get(response.headers['Location'])
        assert response.status_code == 200

    # Check if individual items from MyMeal were added to DailyLog
        usda_log_entry = DailyLog.query.filter_by(user_id=user.id, fdc_id=usda_food.fdc_id, log_date=date.today()).first()
        my_food_log_entry = DailyLog.query.filter_by(user_id=user.id, my_food_id=my_food.id, log_date=date.today()).first()

        assert usda_log_entry is not None
        assert my_food_log_entry is not None

        # Assert that the amounts are NOT scaled, but are the original amounts from the meal definition
        assert usda_log_entry.amount_grams == 50
        assert my_food_log_entry.amount_grams == 30

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

def test_usda_food_search_results_include_1g_portion(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        # Create a USDA food with an existing non-gram portion
        usda_food_fdc_id = 100003
        usda_food = Food(fdc_id=usda_food_fdc_id, description='USDA Food with Cup Portion')
        db.session.add(usda_food)
        db.session.commit()

        # Add a '1 cup' portion
        cup_portion = UnifiedPortion(
            fdc_id=usda_food_fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="",
            modifier="",
            gram_weight=240.0 # Example gram weight for 1 cup
        )
        db.session.add(cup_portion)
        db.session.commit()
        cup_portion_id = cup_portion.id # Store the ID

    search_term = 'USDA Food with Cup Portion'
    response = auth_client.get(f'/search/?search_term={search_term}&search_usda=true&target=diary')
    assert response.status_code == 200

    with auth_client.application.app_context():
        # Retrieve the 1-gram portion that should have been created by the search route
        one_gram_portion = UnifiedPortion.query.filter_by(fdc_id=usda_food_fdc_id, gram_weight=1.0).first()
        assert one_gram_portion is not None, "1-gram portion was not created for USDA food"

        # Construct the expected HTML for the 1g option
        expected_1g_option_html = f'<option value="{one_gram_portion.id}"> g</option>'.encode('utf-8')
        assert expected_1g_option_html in response.data, "' g' portion option not found in dropdown HTML"

        # Verify the '1 cup' portion is also still there
        # Retrieve the cup portion again within this context to avoid DetachedInstanceError
        re_queried_cup_portion = UnifiedPortion.query.get(cup_portion_id)
        assert re_queried_cup_portion is not None, "Cup portion not found after re-query"
        expected_1cup_option_html = f'<option value="{re_queried_cup_portion.id}"> cup</option>'.encode('utf-8')
        assert expected_1cup_option_html in response.data, "' cup' portion option not found in dropdown HTML"

def test_usda_portion_p_icon_logic(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        # 1. Create USDA food with NO extra portions (only the auto 1g)
        usda_food_1_id = 200001
        usda_food_1 = Food(fdc_id=usda_food_1_id, description='USDA Food No Portions')
        db.session.add(usda_food_1)

        # 2. Create USDA food with ONE extra portion
        usda_food_2_id = 200002
        usda_food_2 = Food(fdc_id=usda_food_2_id, description='USDA Food With One Portion')
        db.session.add(usda_food_2)
        db.session.commit() # Commit foods first

        portion = UnifiedPortion(fdc_id=usda_food_2_id, portion_description='slice', gram_weight=28.0)
        db.session.add(portion)
        db.session.commit()

    # Search for the first food
    response1 = auth_client.get(f'/search/?search_term=USDA Food No Portions&search_usda=true')
    assert response1.status_code == 200
    # The 'P' icon should NOT be present because there is only 1 portion (the auto-added 1g)
    assert b'<span class="me-2 fw-bold text-primary" title="Portion sizes available">P</span>' not in response1.data

    # Search for the second food
    response2 = auth_client.get(f'/search/?search_term=USDA Food With One Portion&search_usda=true')
    assert response2.status_code == 200
    # The 'P' icon SHOULD be present because there are 2 portions (the auto-added 1g + the slice)
    assert b'<span class="me-2 fw-bold text-primary" title="Portion sizes available">P</span>' in response2.data