import pytest
from models import db, User, MyFood

def test_add_my_food_with_all_details(auth_client):
    """
    Tests creating a new custom food with all nutritional details.
    """
    food_data = {
        'description': 'Super Health Bar',
        'calories_per_100g': 350.0,
        'protein_per_100g': 15.0,
        'carbs_per_100g': 40.0,
        'fat_per_100g': 18.0,
        'saturated_fat_per_100g': 5.0,
        'trans_fat_per_100g': 0.5,
        'cholesterol_mg_per_100g': 10.0,
        'sodium_mg_per_100g': 90.0,
        'fiber_per_100g': 8.0,
        'sugars_per_100g': 12.0,
        'vitamin_d_mcg_per_100g': 2.0,
        'calcium_mg_per_100g': 100.0,
        'iron_mg_per_100g': 4.0,
        'potassium_mg_per_100g': 300.0
    }
    response = auth_client.post('/database/my_foods', data=food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Custom food added successfully!' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(user_id=user.id, description='Super Health Bar').first()
        assert my_food is not None
        assert my_food.calories_per_100g == 350.0
        assert my_food.saturated_fat_per_100g == 5.0
        assert my_food.potassium_mg_per_100g == 300.0

def test_edit_my_food_with_all_details(auth_client):
    """
    Tests editing an existing custom food with all nutritional details.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        initial_food = MyFood(
            user_id=user.id,
            description='Old Health Bar',
            calories_per_100g=300.0,
            protein_per_100g=12.0,
            carbs_per_100g=35.0,
            fat_per_100g=15.0
        )
        db.session.add(initial_food)
        db.session.commit()
        food_id = initial_food.id

    updated_food_data = {
        'description': 'New and Improved Health Bar',
        'calories_per_100g': 320.0,
        'protein_per_100g': 14.0,
        'carbs_per_100g': 38.0,
        'fat_per_100g': 16.0,
        'saturated_fat_per_100g': 4.0,
        'trans_fat_per_100g': 0.2,
        'cholesterol_mg_per_100g': 8.0,
        'sodium_mg_per_100g': 85.0,
        'fiber_per_100g': 9.0,
        'sugars_per_100g': 11.0,
        'vitamin_d_mcg_per_100g': 2.5,
        'calcium_mg_per_100g': 110.0,
        'iron_mg_per_100g': 4.5,
        'potassium_mg_per_100g': 320.0
    }
    response = auth_client.post(f'/database/my_foods/edit/{food_id}', data=updated_food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Food updated successfully!' in response.data

    with auth_client.application.app_context():
        updated_food = db.session.get(MyFood, food_id)
        assert updated_food is not None
        assert updated_food.description == 'New and Improved Health Bar'
        assert updated_food.calories_per_100g == 320.0
        assert updated_food.saturated_fat_per_100g == 4.0
        assert updated_food.potassium_mg_per_100g == 320.0

def test_delete_my_food_still_works(auth_client):
    """
    Tests deleting a custom food after the model changes.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        food_to_delete = MyFood(
            user_id=user.id,
            description='Food To Be Deleted',
            calories_per_100g=100.0,
            protein_per_100g=10.0,
            carbs_per_100g=10.0,
            fat_per_100g=10.0,
            fiber_per_100g=5.0
        )
        db.session.add(food_to_delete)
        db.session.commit()
        food_id = food_to_delete.id

    response = auth_client.post(f'/database/my_foods/delete/{food_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Food deleted successfully!' in response.data

    with auth_client.application.app_context():
        deleted_food = db.session.get(MyFood, food_id)
        assert deleted_food is None

def test_add_food_with_zero_values(auth_client):
    """
    Tests creating a new custom food with zero values for nutrients (like water).
    """
    food_data = {
        'description': 'Water',
        'calories_per_100g': 0.0,
        'protein_per_100g': 0.0,
        'carbs_per_100g': 0.0,
        'fat_per_100g': 0.0
    }
    response = auth_client.post('/database/my_foods', data=food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Custom food added successfully!' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood.query.filter_by(user_id=user.id, description='Water').first()
        assert my_food is not None
        assert my_food.calories_per_100g == 0.0
        assert my_food.protein_per_100g == 0.0
        assert my_food.carbs_per_100g == 0.0
        assert my_food.fat_per_100g == 0.0
        assert my_food.fiber_per_100g is None
