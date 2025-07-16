import pytest
from models import db, User, MyFood, Food, Recipe, UnifiedPortion, Friendship

def setup_friendship(app, user1, user2):
    with app.app_context():
        friendship = Friendship(requester_id=user1.id, receiver_id=user2.id, status='accepted')
        db.session.add(friendship)
        reciprocal_friendship = Friendship(requester_id=user2.id, receiver_id=user1.id, status='accepted')
        db.session.add(reciprocal_friendship)
        db.session.commit()

def test_search_by_upc_myfood_over_usda(auth_client, app_with_db):
    """
    GIVEN a user has a MyFood with a specific UPC, and a USDA food exists with the same UPC,
    WHEN the user searches for that UPC,
    THEN the MyFood item should be returned, not the USDA food.
    """
    my_food_id = None
    upc = "012345678901"
    with app_with_db.app_context():
        user = User.query.filter_by(username='testuser').first()

        # Create MyFood
        my_food = MyFood(user_id=user.id, description="My Custom Soda", upc=upc, calories_per_100g=42)
        db.session.add(my_food)
        db.session.commit()
        my_food_portion = UnifiedPortion(my_food_id=my_food.id, amount=1, measure_unit_description="can", gram_weight=355)
        db.session.add(my_food_portion)
        db.session.commit()
        my_food_id = my_food.id

        # Create USDA Food
        usda_food = Food(fdc_id=999999, description="Generic Soda", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(f'/search/by_upc?upc={upc}')
    
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['status'] == 'found'
    assert json_data['source'] == 'my_food'
    assert json_data['food']['description'] == "My Custom Soda"
    assert json_data['food']['id'] == my_food_id

def test_search_by_upc_recipe_over_usda(auth_client, app_with_db):
    """
    GIVEN a user has a Recipe with a specific UPC, and a USDA food exists with the same UPC,
    WHEN the user searches for that UPC,
    THEN the Recipe item should be returned.
    """
    recipe_id = None
    upc = "098765432109"
    with app_with_db.app_context():
        user = User.query.filter_by(username='testuser').first()

        # Create Recipe
        recipe = Recipe(user_id=user.id, name="My Special Recipe", upc=upc)
        db.session.add(recipe)
        db.session.commit()
        recipe_portion = UnifiedPortion(recipe_id=recipe.id, amount=1, measure_unit_description="serving", gram_weight=250)
        db.session.add(recipe_portion)
        db.session.commit()
        recipe_id = recipe.id

        # Create USDA Food
        usda_food = Food(fdc_id=999998, description="Generic Meal", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(f'/search/by_upc?upc={upc}')
    
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['status'] == 'found'
    assert json_data['source'] == 'my_recipe'
    assert json_data['food']['description'] == "My Special Recipe"
    assert json_data['food']['id'] == recipe_id

def test_search_by_upc_only_usda(auth_client, app_with_db):
    """
    GIVEN only a USDA food exists for a specific UPC,
    WHEN the user searches for that UPC,
    THEN the USDA food should be returned.
    """
    usda_fdc_id = 999997
    upc = "111112222233"
    with app_with_db.app_context():
        usda_food = Food(fdc_id=usda_fdc_id, description="Just a USDA Food", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(f'/search/by_upc?upc={upc}')
    
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['status'] == 'found'
    assert json_data['source'] == 'usda'
    assert json_data['food']['description'] == "Just a USDA Food"
    assert json_data['food']['fdc_id'] == usda_fdc_id

def test_search_by_upc_not_found(auth_client, app_with_db):
    """
    GIVEN no food item exists for a specific UPC,
    WHEN the user searches for that UPC,
    THEN a 'not_found' status should be returned.
    """
    upc = "000000000000"
    response = auth_client.get(f'/search/by_upc?upc={upc}')
    
    assert response.status_code == 404
    json_data = response.get_json()
    assert json_data['status'] == 'not_found'

def test_search_by_upc_friend_food(auth_client, app_with_db):
    """
    GIVEN a user has a friend who has a MyFood with a specific UPC,
    WHEN the user searches for that UPC,
    THEN the friend's MyFood item should be returned.
    """
    friend_food_id = None
    upc = "555666777888"
    with app_with_db.app_context():
        user1 = User.query.filter_by(username='testuser').first()
        user2 = User(username='frienduser')
        user2.set_password('password')
        db.session.add(user2)
        db.session.commit()
        
        setup_friendship(app_with_db, user1, user2)

        friend_food = MyFood(user_id=user2.id, description="Friend's Food", upc=upc)
        db.session.add(friend_food)
        db.session.commit()
        friend_food_portion = UnifiedPortion(my_food_id=friend_food.id, amount=1, measure_unit_description="piece", gram_weight=50)
        db.session.add(friend_food_portion)
        db.session.commit()
        friend_food_id = friend_food.id

    response = auth_client.get(f'/search/by_upc?upc={upc}')
    
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['status'] == 'found'
    assert json_data['source'] == 'friend_food'
    assert json_data['food']['description'] == "Friend's Food"
    assert json_data['food']['id'] == friend_food_id

def test_search_by_upc_no_upc_provided(auth_client, app_with_db):
    """
    GIVEN a user is logged in,
    WHEN they call the search_by_upc endpoint without a UPC,
    THEN a 400 error should be returned.
    """
    response = auth_client.get('/search/by_upc')
    
    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    assert json_data['error'] == 'UPC code is required'