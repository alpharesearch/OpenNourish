import pytest
from models import (
    db,
    Food,
    MyFood,
    Recipe,
    MyMeal,
    User,
    DailyLog,
    RecipeIngredient,
    MyMealItem,
    Nutrient,
    FoodNutrient,
    UnifiedPortion,
    Friendship,
)
from datetime import date
from flask import url_for
from opennourish.search.routes import ManualPagination


@pytest.fixture
def auth_client_with_data(auth_client):
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        if not user:
            user = User(username="testuser", email="testuser@example.com")
            user.set_password("password")
            db.session.add(user)
            db.session.commit()

        # Create sample data for testing add_item
        usda_food = Food(fdc_id=100001, description="Test USDA Food")
        db.session.add(usda_food)
        db.session.add(Nutrient(id=1008, name="Energy", unit_name="kcal"))
        db.session.add(
            FoodNutrient(fdc_id=100001, nutrient_id=1008, amount=100.0)
        )  # 100 kcal/100g

        my_food = MyFood(
            user_id=user.id, description="Test My Food", calories_per_100g=200
        )
        db.session.add(my_food)

        recipe = Recipe(
            user_id=user.id, name="Test Recipe", instructions="Test instructions"
        )
        db.session.add(recipe)

        my_meal = MyMeal(user_id=user.id, name="Test My Meal")
        db.session.add(my_meal)
        db.session.commit()

        # Add items to my_meal for expansion test
        my_meal_item_usda = MyMealItem(
            my_meal_id=my_meal.id, fdc_id=usda_food.fdc_id, amount_grams=50
        )
        my_meal_item_my_food = MyMealItem(
            my_meal_id=my_meal.id, my_food_id=my_food.id, amount_grams=30
        )
        db.session.add_all([my_meal_item_usda, my_meal_item_my_food])
        db.session.commit()

        # Create a target recipe for adding ingredients
        target_recipe = Recipe(
            user_id=user.id, name="Target Recipe", instructions="Target instructions"
        )
        db.session.add(target_recipe)
        db.session.commit()

        # Create a target meal for adding items
        target_meal = MyMeal(user_id=user.id, name="Target Meal")
        db.session.add(target_meal)
        db.session.commit()

    return auth_client


def test_search_page_loads(auth_client):
    response = auth_client.get("/search/")
    assert response.status_code == 200


def test_search_finds_all_food_types(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # Create one of each food type with a unique keyword
        usda_food = Food(fdc_id=99999, description="SearchUSDAFood")
        my_food = MyFood(
            user_id=user.id, description="SearchMyFood", calories_per_100g=100
        )
        recipe = Recipe(user_id=user.id, name="SearchRecipe", instructions="Test")
        my_meal = MyMeal(user_id=user.id, name="SearchMyMeal")

        db.session.add_all([usda_food, my_food, recipe, my_meal])
        db.session.commit()

    search_term = "Search"
    response = auth_client.post(
        "/search/",
        data={
            "search_term": search_term,
            "search_usda": True,
            "search_my_foods": True,
            "search_recipes": True,
            "search_my_meals": True,
        },
    )
    assert response.status_code == 200

    # Assert that all four items appear in the response
    assert b"SearchUSDAFood" in response.data
    assert b"SearchMyFood" in response.data
    assert b"SearchRecipe" in response.data
    assert b"SearchMyMeal" in response.data


def test_search_preserves_context(auth_client):
    target_value = "diary"
    recipe_id_value = "123"
    response = auth_client.get(
        f"/search/?target={target_value}&recipe_id={recipe_id_value}"
    )
    assert response.status_code == 200

    # Assert that the rendered template's HTML contains these values in hidden form fields
    assert f'name="target" value="{target_value}"'.encode("utf-8") in response.data
    assert (
        f'name="recipe_id" value="{recipe_id_value}"'.encode("utf-8") in response.data
    )


def test_add_item_to_diary(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        usda_food = Food.query.filter_by(description="Test USDA Food").first()
        log_date_str = date.today().isoformat()
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(
            fdc_id=usda_food.fdc_id, portion_description="gram", gram_weight=1.0
        )
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id
        usda_food_id = usda_food.fdc_id
        user_id = user.id

    # Add USDA Food to diary
    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": usda_food_id,
            "food_type": "usda",
            "target": "diary",
            "log_date": log_date_str,
            "meal_name": "Breakfast",
            "amount": 150,
            "portion_id": gram_portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test USDA Food added to your diary." in response.data

    with auth_client.application.app_context():
        daily_log = DailyLog.query.filter_by(
            user_id=user_id, fdc_id=usda_food_id, log_date=date.today()
        ).first()
        assert daily_log is not None
        assert daily_log.amount_grams == 150


def test_add_recipe_to_diary(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        recipe = Recipe.query.filter_by(name="Test Recipe").first()
        log_date_str = date.today().isoformat()
        portion = UnifiedPortion(
            recipe_id=recipe.id, portion_description="serving", gram_weight=125.0
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id
        recipe_id = recipe.id
        user_id = user.id

    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": recipe_id,
            "food_type": "recipe",
            "target": "diary",
            "log_date": log_date_str,
            "meal_name": "Dinner",
            "amount": 1,
            "portion_id": portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test Recipe added to your diary." in response.data

    with auth_client.application.app_context():
        daily_log = DailyLog.query.filter_by(
            user_id=user_id, recipe_id=recipe_id, log_date=date.today()
        ).first()
        assert daily_log is not None
        assert daily_log.amount_grams == 125.0


def test_add_item_to_recipe(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        target_recipe = Recipe.query.filter_by(name="Target Recipe").first()
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(
            my_food_id=my_food.id, portion_description="gram", gram_weight=1.0
        )
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id
        my_food_id = my_food.id
        target_recipe_id = target_recipe.id

    # Add MyFood to recipe
    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": my_food_id,
            "food_type": "my_food",
            "target": "recipe",
            "recipe_id": target_recipe_id,
            "amount": 75,
            "portion_id": gram_portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test My Food added to recipe Target Recipe." in response.data

    with auth_client.application.app_context():
        recipe_ingredient = RecipeIngredient.query.filter_by(
            recipe_id=target_recipe_id, my_food_id=my_food_id
        ).first()
        assert recipe_ingredient is not None
        assert recipe_ingredient.amount_grams == 75


def test_add_usda_food_to_meal(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        usda_food = Food.query.filter_by(description="Test USDA Food").first()
        target_meal = MyMeal.query.filter_by(name="Target Meal").first()
        gram_portion = UnifiedPortion(
            fdc_id=usda_food.fdc_id, portion_description="gram", gram_weight=1.0
        )
        db.session.add(gram_portion)
        db.session.commit()
        portion_id = gram_portion.id
        usda_food_id = usda_food.fdc_id
        target_meal_id = target_meal.id

    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": usda_food_id,
            "food_type": "usda",
            "target": "meal",
            "recipe_id": target_meal_id,
            "amount": 50,
            "portion_id": portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test USDA Food added to meal Target Meal." in response.data

    with auth_client.application.app_context():
        meal_item = MyMealItem.query.filter_by(
            my_meal_id=target_meal_id, fdc_id=usda_food_id
        ).first()
        assert meal_item is not None
        assert meal_item.amount_grams == 50


def test_add_my_food_to_meal(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        target_meal = MyMeal.query.filter_by(name="Target Meal").first()
        gram_portion = UnifiedPortion(
            my_food_id=my_food.id, portion_description="gram", gram_weight=1.0
        )
        db.session.add(gram_portion)
        db.session.commit()
        portion_id = gram_portion.id
        my_food_id = my_food.id
        target_meal_id = target_meal.id

    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": my_food_id,
            "food_type": "my_food",
            "target": "meal",
            "recipe_id": target_meal_id,
            "amount": 80,
            "portion_id": portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test My Food added to meal Target Meal." in response.data

    with auth_client.application.app_context():
        meal_item = MyMealItem.query.filter_by(
            my_meal_id=target_meal_id, my_food_id=my_food_id
        ).first()
        assert meal_item is not None
        assert meal_item.amount_grams == 80


def test_add_item_to_meal(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        recipe = Recipe.query.filter_by(name="Test Recipe").first()
        target_meal = MyMeal.query.filter_by(name="Target Meal").first()
        # Add a portion for the recipe
        portion = UnifiedPortion(
            recipe_id=recipe.id, portion_description="serving", gram_weight=150.0
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id
        recipe_id = recipe.id
        target_meal_id = target_meal.id

    # Add Recipe to meal
    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": recipe_id,
            "food_type": "recipe",
            "target": "meal",
            "recipe_id": target_meal_id,  # Using recipe_id for my_meal_id in this context
            "amount": 2,  # servings
            "portion_id": portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test Recipe added to meal Target Meal." in response.data

    with auth_client.application.app_context():
        my_meal_item = MyMealItem.query.filter_by(
            my_meal_id=target_meal_id, recipe_id=recipe_id
        ).first()
        assert my_meal_item is not None
        assert my_meal_item.amount_grams == 300  # 2 servings * 150g/serving


def test_add_meal_expands_correctly(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_meal = MyMeal.query.filter_by(name="Test My Meal").first()
        usda_food = Food.query.filter_by(description="Test USDA Food").first()
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        log_date_str = date.today().isoformat()
        my_meal_id = my_meal.id
        # Add MyMeal to diary, expecting expansion
        response = auth_client.post(
            "/search/add_item",
            data={
                "food_id": my_meal_id,
                "food_type": "my_meal",
                "target": "diary",
                "log_date": log_date_str,
                "meal_name": "Lunch",
            },
        )
        assert response.status_code == 302  # Check for redirect

        # Check for the flash message in the session before following the redirect
        with auth_client.session_transaction() as session:
            flashes = session.get("_flashes", [])
            assert len(flashes) > 0
            assert flashes[0][1] == '"Test My Meal" (expanded) added to your diary.'

        # Manually follow the redirect
        response = auth_client.get(response.headers["Location"])
        assert response.status_code == 200

        # Check if individual items from MyMeal were added to DailyLog
        usda_log_entry = DailyLog.query.filter_by(
            user_id=user.id, fdc_id=usda_food.fdc_id, log_date=date.today()
        ).first()
        my_food_log_entry = DailyLog.query.filter_by(
            user_id=user.id, my_food_id=my_food.id, log_date=date.today()
        ).first()

        assert usda_log_entry is not None
        assert my_food_log_entry is not None

        # Assert that the amounts are NOT scaled, but are the original amounts from the meal definition
        assert usda_log_entry.amount_grams == 50
        assert my_food_log_entry.amount_grams == 30


def test_search_result_includes_details_link_for_usda_food(auth_client_with_data):
    auth_client = auth_client_with_data
    usda_food_fdc_id = 0  # Initialize outside context
    with auth_client.application.app_context():
        usda_food_fdc_id = 100002
        usda_food = Food(fdc_id=usda_food_fdc_id, description="Details USDA Food")
        db.session.add(usda_food)
        db.session.commit()

    search_term = "Details USDA Food"
    response = auth_client.get(f"/search/?search_term={search_term}&search_usda=true")
    assert response.status_code == 200
    assert f'href="/food/{usda_food_fdc_id}"' in response.data.decode("utf-8")


def test_usda_food_search_results_include_1g_portion(
    auth_client_with_data, monkeypatch
):
    auth_client = auth_client_with_data

    # Define a fixed date for the test
    fixed_date = date(2025, 1, 1)
    monkeypatch.setattr(
        "opennourish.search.routes.get_user_today", lambda tz: fixed_date
    )

    with auth_client.application.app_context():
        # Create a USDA food with an existing non-gram portion
        usda_food_fdc_id = 100003
        usda_food = Food(
            fdc_id=usda_food_fdc_id, description="USDA Food with Cup Portion"
        )
        db.session.add(usda_food)
        db.session.commit()

        # Add a '1 cup' portion
        cup_portion = UnifiedPortion(
            fdc_id=usda_food_fdc_id,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="",
            modifier="",
            gram_weight=240.0,  # Example gram weight for 1 cup
        )
        db.session.add(cup_portion)
        db.session.commit()

    search_term = "USDA Food with Cup Portion"
    response = auth_client.get(
        f"/search/?search_term={search_term}&search_usda=true&target=diary"
    )
    assert response.status_code == 200

    # Check that the "Add" button is present and has the correct data attributes
    response_data_str = response.data.decode("utf-8")

    # Assert the button's basic structure and class
    assert (
        '<button type="button" class="btn btn-sm btn-outline-success add-item-btn me-2"'
        in response_data_str
    )

    # Assert specific data attributes
    assert f'data-food-id="{usda_food_fdc_id}"' in response_data_str
    assert 'data-food-type="usda_food"' in response_data_str
    assert 'data-food-name="USDA Food with Cup Portion"' in response_data_str
    assert 'data-target="diary"' in response_data_str
    assert f'data-log-date="{fixed_date.isoformat()}"' in response_data_str
    assert 'data-meal-name=""' in response_data_str
    assert 'data-recipe-id=""' in response_data_str
    assert (
        '<button type="button" class="btn btn-sm btn-outline-success add-item-btn me-2"'
        in response_data_str
    )


def test_usda_portion_p_icon_logic(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        # 1. Create USDA food with NO extra portions (only the auto 1g)
        usda_food_1_id = 200001
        usda_food_1 = Food(fdc_id=usda_food_1_id, description="USDA Food No Portions")
        db.session.add(usda_food_1)

        # 2. Create USDA food with ONE extra portion
        usda_food_2_id = 200002
        usda_food_2 = Food(
            fdc_id=usda_food_2_id, description="USDA Food With One Portion"
        )
        db.session.add(usda_food_2)
        db.session.commit()  # Commit foods first

        portion = UnifiedPortion(
            fdc_id=usda_food_2_id, portion_description="slice", gram_weight=28.0
        )
        db.session.add(portion)
        db.session.commit()

    # Search for the first food
    response1 = auth_client.get(
        "/search/?search_term=USDA Food No Portions&search_usda=true"
    )
    assert response1.status_code == 200
    # The 'P' icon should NOT be present because there is only 1 portion (the auto-added 1g)
    assert (
        b'<span class="me-2 fw-bold text-primary" title="Portion sizes available">P</span>'
        not in response1.data
    )

    # Search for the second food
    response2 = auth_client.get(
        "/search/?search_term=USDA Food With One Portion&search_usda=true"
    )
    assert response2.status_code == 200
    # The 'P' icon SHOULD be present because there are 2 portions (the auto-added 1g + the slice)
    assert (
        b'<span class="me-2 fw-bold text-primary" title="Portion sizes available">P2</span>'
        in response2.data
    )


def test_usda_search_ranking(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        # Create several food items with descriptions designed to test the ranking logic.
        food1 = Food(fdc_id=300001, description="Milk")  # Exact match, should be first.
        food2 = Food(
            fdc_id=300002, description="Milk, whole"
        )  # Starts with, should be second.
        food3 = Food(
            fdc_id=300003, description="Soy milk"
        )  # Contains, but not at start.
        food4 = Food(
            fdc_id=300004, description="Milk chocolate"
        )  # Starts with, but longer.
        food5 = Food(
            fdc_id=300005, description="A long description about almond milk"
        )  # Contains, but long.
        food6 = Food(
            fdc_id=300006, description="Milk with many portions"
        )  # Test portion count ranking

        db.session.add_all([food1, food2, food3, food4, food5, food6])
        db.session.commit()

        # Add portions to food6 to test ranking
        db.session.add(
            UnifiedPortion(fdc_id=300006, portion_description="cup", gram_weight=240.0)
        )
        db.session.add(
            UnifiedPortion(fdc_id=300006, portion_description="oz", gram_weight=28.35)
        )
        db.session.commit()

    # Search for "Milk"
    response = auth_client.get("/search/?search_term=Milk&search_usda=true")
    assert response.status_code == 200

    response_data = response.data.decode("utf-8")

    # Find the indices of each food description in the response.
    # A lower index means a higher ranking.
    idx_milk_with_portions = response_data.find(
        "<strong>Milk with many portions</strong>"
    )
    idx_milk = response_data.find("<strong>Milk</strong>")
    idx_milk_whole = response_data.find("<strong>Milk, whole</strong>")
    idx_milk_chocolate = response_data.find("<strong>Milk chocolate</strong>")
    idx_soy_milk = response_data.find("<strong>Soy milk</strong>")
    idx_almond_milk = response_data.find(
        "<strong>A long description about almond milk</strong>"
    )

    # Assert that all items were found
    assert all(
        idx != -1
        for idx in [
            idx_milk,
            idx_milk_whole,
            idx_milk_chocolate,
            idx_soy_milk,
            idx_almond_milk,
            idx_milk_with_portions,
        ]
    )

    # Assert the ranking order based on their position in the HTML
    assert idx_milk_with_portions < idx_milk
    assert idx_milk < idx_milk_whole
    assert idx_milk_whole < idx_milk_chocolate
    assert idx_milk_chocolate < idx_soy_milk
    assert idx_soy_milk < idx_almond_milk


def test_copy_diary_meal(auth_client_with_data):
    """
    Tests copying a meal from the diary to another meal using the add_item route.
    """
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        today = date.today()

        # Create dummy food items to reference
        food1 = Food(fdc_id=99998, description="Test Coffee")
        food2 = Food(fdc_id=99999, description="Test Toast")
        db.session.add_all([food1, food2])

        # Log two items to Breakfast
        log1 = DailyLog(
            user_id=user.id,
            log_date=today,
            meal_name="Breakfast",
            amount_grams=100,
            fdc_id=99998,
        )
        log2 = DailyLog(
            user_id=user.id,
            log_date=today,
            meal_name="Breakfast",
            amount_grams=200,
            fdc_id=99999,
        )
        db.session.add_all([log1, log2])
        db.session.commit()

        # Verify initial state
        breakfast_items_count = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Breakfast"
        ).count()
        assert breakfast_items_count == 2
        lunch_items_count = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Lunch"
        ).count()
        assert lunch_items_count == 0
        return_url = url_for("diary.diary", log_date_str=today.isoformat())

    # Perform the copy operation from Breakfast to Lunch via the search.add_item route
    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": "Breakfast",  # Source meal name
            "food_type": "diary_meal",
            "target": "diary",
            "source_log_date": today.isoformat(),
            "log_date": today.isoformat(),
            "meal_name": "Lunch",  # Target meal name
            "return_url": return_url,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Successfully copied items from Breakfast to Lunch." in response.data

    # Verify the result
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # Original meal should be unchanged
        breakfast_items_count = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Breakfast"
        ).count()
        assert breakfast_items_count == 2

        # New meal should have the copied items
        lunch_items = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Lunch"
        ).all()
        assert len(lunch_items) == 2

        fdc_ids = {item.fdc_id for item in lunch_items}
        assert 99998 in fdc_ids
        assert 99999 in fdc_ids


def test_copy_friend_diary_meal(auth_client_with_data):
    """
    Tests copying a meal from a friend's diary to the current user's diary.
    """
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        friend = User(username="friend", email="friend@example.com")
        friend.set_password("password")
        db.session.add(friend)
        db.session.commit()

        friendship = Friendship(
            requester_id=user.id, receiver_id=friend.id, status="accepted"
        )
        db.session.add(friendship)

        today = date.today()

        # Create dummy food items to reference
        food1 = Food(fdc_id=99998, description="Test Coffee")
        food2 = Food(fdc_id=99999, description="Test Toast")
        db.session.add_all([food1, food2])

        # Log two items to the FRIEND's Breakfast
        log1 = DailyLog(
            user_id=friend.id,
            log_date=today,
            meal_name="Breakfast",
            amount_grams=100,
            fdc_id=99998,
        )
        log2 = DailyLog(
            user_id=friend.id,
            log_date=today,
            meal_name="Breakfast",
            amount_grams=200,
            fdc_id=99999,
        )
        db.session.add_all([log1, log2])
        db.session.commit()

        # Verify initial state
        friend_breakfast_items_count = DailyLog.query.filter_by(
            user_id=friend.id, log_date=today, meal_name="Breakfast"
        ).count()
        assert friend_breakfast_items_count == 2
        user_lunch_items_count = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Lunch"
        ).count()
        assert user_lunch_items_count == 0
        return_url = url_for("diary.diary", log_date_str=today.isoformat())

    # Perform the copy operation from the FRIEND's Breakfast to the USER's Lunch
    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": "Breakfast",  # Source meal name
            "food_type": "diary_meal",
            "target": "diary",
            "source_log_date": today.isoformat(),
            "log_date": today.isoformat(),
            "meal_name": "Lunch",  # Target meal name
            "friend_username": "friend",  # The source of the meal
            "return_url": return_url,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Successfully copied items from Breakfast to Lunch." in response.data

    # Verify the result
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # Friend's meal should be unchanged
        friend_breakfast_items_count = DailyLog.query.filter_by(
            user_id=friend.id, log_date=today, meal_name="Breakfast"
        ).count()
        assert friend_breakfast_items_count == 2

        # User's new meal should have the copied items
        user_lunch_items = DailyLog.query.filter_by(
            user_id=user.id, log_date=today, meal_name="Lunch"
        ).all()
        assert len(user_lunch_items) == 2

        fdc_ids = {item.fdc_id for item in user_lunch_items}
        assert 99998 in fdc_ids
        assert 99999 in fdc_ids


@pytest.fixture
def search_coverage_data(auth_client):
    with auth_client.application.app_context():
        user1 = User.query.filter_by(username="testuser").first()
        if not user1:
            user1 = User(username="testuser", email="test@test.com")
            user1.set_password("password")
            db.session.add(user1)
            db.session.commit()

        user2 = User(username="user2", email="user2@example.com")
        user2.set_password("password")
        deleted_user = User(username="deleteduser", email="deleted@example.com")
        deleted_user.set_password("password")
        db.session.add_all([user2, deleted_user])
        db.session.commit()

        # Data for user2 (not a friend)
        my_food_user2 = MyFood(
            user_id=user2.id, description="User2 Food", calories_per_100g=100
        )
        recipe_user2 = Recipe(user_id=user2.id, name="User2 Recipe", instructions="...")
        db.session.add_all([my_food_user2, recipe_user2])
        db.session.commit()

        # Data for deleted user
        my_food_deleted = MyFood(
            user_id=deleted_user.id,
            description="Deleted User Food",
            calories_per_100g=100,
        )
        recipe_deleted = Recipe(
            user_id=deleted_user.id, name="Deleted User Recipe", instructions="..."
        )
        public_recipe_deleted = Recipe(
            user_id=deleted_user.id,
            name="Orphaned Public Recipe",
            instructions="...",
            is_public=True,
        )
        db.session.add_all([my_food_deleted, recipe_deleted, public_recipe_deleted])
        db.session.commit()

        portion_my_food_deleted = UnifiedPortion(
            my_food_id=my_food_deleted.id,
            gram_weight=100,
            portion_description="serving",
        )
        portion_recipe_deleted = UnifiedPortion(
            recipe_id=recipe_deleted.id, gram_weight=200, portion_description="serving"
        )
        db.session.add_all([portion_my_food_deleted, portion_recipe_deleted])
        db.session.commit()

        # "Delete" the user
        db.session.delete(deleted_user)
        db.session.commit()

        # Target recipe for current user
        target_recipe = Recipe(
            user_id=user1.id, name="My Target Recipe", instructions="..."
        )
        db.session.add(target_recipe)
        db.session.commit()
    return auth_client


def test_add_meal_to_recipe(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        my_meal = MyMeal.query.filter_by(name="Test My Meal").first()
        target_recipe = Recipe.query.filter_by(name="Target Recipe").first()
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        my_meal_id = my_meal.id
        target_recipe_id = target_recipe.id
        my_food_id = my_food.id

        response = auth_client.post(
            url_for("search.add_item"),
            data={
                "food_id": my_meal_id,
                "food_type": "my_meal",
                "target": "recipe",
                "recipe_id": target_recipe_id,
                "amount": 1,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        with auth_client.session_transaction() as session:
            flashes = session.get("_flashes", [])
            assert len(flashes) > 0
            assert (
                flashes[0][1]
                == '"Test My Meal" (expanded) added to recipe Target Recipe.'
            )

        # follow redirect to check final state
        response = auth_client.get(response.location, follow_redirects=True)
        assert response.status_code == 200

        with auth_client.application.app_context():
            target_recipe = db.session.get(Recipe, target_recipe_id)
            assert len(target_recipe.ingredients) == 2
            assert any(
                i.fdc_id == 100001 and i.amount_grams == 50
                for i in target_recipe.ingredients
            )
            assert any(
                i.my_food_id == my_food_id and i.amount_grams == 30
                for i in target_recipe.ingredients
            )


def test_add_item_invalid_portion_id(auth_client_with_data):
    auth_client = auth_client_with_data
    with auth_client.application.app_context():
        usda_food = Food.query.filter_by(description="Test USDA Food").first()
        log_date_str = date.today().isoformat()
        usda_food_id = usda_food.fdc_id

    response = auth_client.post(
        url_for("search.add_item"),
        data={
            "food_id": usda_food_id,
            "food_type": "usda",
            "target": "diary",
            "log_date": log_date_str,
            "meal_name": "Breakfast",
            "amount": 150,
            "portion_id": "999999",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Test USDA Food added to your diary." in response.data


def test_add_item_from_deleted_user(search_coverage_data):
    client = search_coverage_data
    with client.application.app_context():
        deleted_food = MyFood.query.filter_by(description="Deleted User Food").first()
        deleted_recipe = Recipe.query.filter_by(name="Deleted User Recipe").first()
        portion_food = UnifiedPortion.query.filter_by(
            my_food_id=deleted_food.id
        ).first()
        portion_recipe = UnifiedPortion.query.filter_by(
            recipe_id=deleted_recipe.id
        ).first()
        target_recipe = Recipe.query.filter_by(name="My Target Recipe").first()
        log_date_str = date.today().isoformat()

    # Test adding MyFood from deleted user to diary
    response = client.post(
        url_for("search.add_item"),
        data={
            "food_id": deleted_food.id,
            "food_type": "my_food",
            "target": "diary",
            "log_date": log_date_str,
            "meal_name": "Lunch",
            "amount": 1,
            "portion_id": portion_food.id,
        },
        follow_redirects=True,
    )
    assert b"This food belongs to a deleted user and cannot be added." in response.data

    # Test adding Recipe from deleted user to recipe
    response = client.post(
        url_for("search.add_item"),
        data={
            "food_id": deleted_recipe.id,
            "food_type": "recipe",
            "target": "recipe",
            "recipe_id": target_recipe.id,
            "amount": 1,
            "portion_id": portion_recipe.id,
        },
        follow_redirects=True,
    )
    assert (
        b"This recipe belongs to a deleted user and cannot be added as an ingredient."
        in response.data
    )


def test_add_recipe_to_itself(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        recipe = Recipe.query.filter_by(name="Test Recipe").first()
        portion = UnifiedPortion(
            recipe_id=recipe.id, gram_weight=100, portion_description="serving"
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id
        recipe_id = recipe.id

        response = client.post(
            url_for("search.add_item"),
            data={
                "food_id": recipe_id,
                "food_type": "recipe",
                "target": "recipe",
                "recipe_id": recipe_id,
                "amount": 1,
                "portion_id": portion_id,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"A recipe cannot be an ingredient of itself." in response.data


def test_get_portions_unauthorized(search_coverage_data):
    client = search_coverage_data
    with client.application.app_context():
        food_user2 = MyFood.query.filter_by(description="User2 Food").first()
        recipe_user2 = Recipe.query.filter_by(name="User2 Recipe").first()

    # Test my_food
    response = client.get(f"/search/api/get-portions/my_food/{food_user2.id}")
    assert response.status_code == 404
    assert b"Not Found or Unauthorized" in response.data

    # Test recipe
    response = client.get(f"/search/api/get-portions/recipe/{recipe_user2.id}")
    assert response.status_code == 404
    assert b"Not Found or Unauthorized" in response.data


def test_get_portions_not_found(auth_client):
    response = auth_client.get("/search/api/get-portions/usda/99999999")
    assert response.status_code == 404
    assert b"Not Found" in response.data


def test_get_portions_empty_meal(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        empty_meal = MyMeal(user_id=user.id, name="Empty Meal")
        db.session.add(empty_meal)
        db.session.commit()
        meal_id = empty_meal.id

    response = client.get(f"/search/api/get-portions/my_meal/{meal_id}")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["calories_per_100g"] == 0
    assert json_data["portions"][0]["gram_weight"] == 1.0


def test_get_portions_diary_meal(auth_client):
    response = auth_client.get(
        "/search/api/get-portions/diary_meal/1"
    )  # id is not used
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["portions"][0]["description"] == "1 serving"
    assert json_data["portions"][0]["gram_weight"] == 1.0


def test_get_portions_no_portions_exist(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        UnifiedPortion.query.filter_by(my_food_id=my_food.id).delete()
        db.session.commit()
        food_id = my_food.id

    response = client.get(f"/search/api/get-portions/my_food/{food_id}")
    assert response.status_code == 200
    json_data = response.get_json()
    assert len(json_data["portions"]) == 1
    assert json_data["portions"][0]["description"] == "g"


def test_search_my_food_by_upc(auth_client_with_data):
    client = auth_client_with_data
    upc = "123456789012"
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        food = MyFood(
            user_id=user.id, description="UPC Food", upc=upc, calories_per_100g=1
        )
        db.session.add(food)
        db.session.commit()

    response = client.post(
        "/search/", data={"search_term": upc, "search_my_foods": "true"}
    )
    assert response.status_code == 200
    assert b"UPC Food" in response.data


def test_search_finds_orphaned_public_recipe(search_coverage_data):
    client = search_coverage_data
    response = client.post(
        "/search/",
        data={"search_term": "Orphaned Public Recipe", "search_recipes": "true"},
    )
    assert response.status_code == 200
    assert b"Orphaned Public Recipe" in response.data


def test_search_frequent_items(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        recipe = Recipe.query.filter_by(name="Test Recipe").first()
        # Log items to make them "frequent"
        db.session.add(
            DailyLog(user_id=user.id, my_food_id=my_food.id, log_date=date.today())
        )
        db.session.add(
            DailyLog(user_id=user.id, recipe_id=recipe.id, log_date=date.today())
        )
        db.session.commit()

    response = client.get("/search/?search_my_foods=true&search_recipes=true")
    assert response.status_code == 200
    assert b"Test My Food" in response.data
    assert b"Test Recipe" in response.data


def test_manual_pagination():
    pagination = ManualPagination(page=2, per_page=10, total=30, items=[])
    assert pagination.has_prev
    assert pagination.has_next
    assert list(pagination.iter_pages()) == [1, 2, 3]


def test_search_return_url_for_meal(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        meal = MyMeal.query.filter_by(name="Test My Meal").first()
        meal_id = meal.id
    response = client.get(f"/search/?target=meal&recipe_id={meal_id}")
    assert response.status_code == 200
    assert f"/my_meals/edit/{meal_id}" in response.data.decode()


def test_search_no_results(auth_client):
    response = auth_client.get(
        "/search/?search_term=nonexistentfood123asdf&search_usda=true&search_my_foods=false&search_recipes=false&search_my_meals=false"
    )
    assert response.status_code == 200
    assert b"Search" in response.data


def test_add_non_usda_to_my_foods(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        my_food = MyFood.query.filter_by(description="Test My Food").first()
        food_id = my_food.id
        portion = UnifiedPortion(my_food_id=food_id, gram_weight=100)
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    response = client.post(
        url_for("search.add_item"),
        data={
            "food_id": food_id,
            "food_type": "my_food",
            "target": "my_foods",
            "portion_id": portion_id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert (
            flashes[0][1]
            == "Only USDA foods can be copied to My Foods via this method."
        )


def test_add_item_exception(auth_client_with_data, monkeypatch):
    client = auth_client_with_data
    with client.application.app_context():
        usda_food = Food.query.filter_by(description="Test USDA Food").first()
        food_id = usda_food.fdc_id
        portion = UnifiedPortion(fdc_id=food_id, gram_weight=1)
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    def mock_commit():
        raise Exception("DB error")

    monkeypatch.setattr(db.session, "commit", mock_commit)

    response = client.post(
        url_for("search.add_item"),
        data={
            "food_id": food_id,
            "food_type": "usda",
            "target": "diary",
            "log_date": date.today().isoformat(),
            "meal_name": "Breakfast",
            "amount": 1,
            "portion_id": portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"An error occurred: DB error" in response.data


def test_add_invalid_food_type_to_recipe(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        target_recipe = Recipe.query.filter_by(name="Target Recipe").first()
        dummy_portion = UnifiedPortion(gram_weight=1)
        db.session.add(dummy_portion)
        db.session.commit()
        portion_id = dummy_portion.id
        target_recipe_id = target_recipe.id

        response = client.post(
            url_for("search.add_item"),
            data={
                "food_id": 1,
                "food_type": "invalid_type",
                "target": "recipe",
                "recipe_id": target_recipe_id,
                "amount": 1,
                "portion_id": portion_id,
            },
            follow_redirects=True,
        )
        assert b"Invalid food type for recipe." in response.data


def test_add_meal_to_meal(auth_client_with_data):
    client = auth_client_with_data
    with client.application.app_context():
        meal1 = MyMeal.query.filter_by(name="Test My Meal").first()
        meal2 = MyMeal.query.filter_by(name="Target Meal").first()
        meal1_id = meal1.id
        meal2_id = meal2.id

    response = client.post(
        url_for("search.add_item"),
        data={
            "food_id": meal1_id,
            "food_type": "my_meal",
            "target": "meal",
            "recipe_id": meal2_id,
            "amount": 1,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Cannot add a meal to the selected target: meal."
