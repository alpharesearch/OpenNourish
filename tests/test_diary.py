import pytest
from models import db, User, Food, FoodNutrient, Nutrient, MyFood, DailyLog, Portion, MyPortion, MeasureUnit
from datetime import date
from opennourish.utils import calculate_nutrition_for_items

def test_add_usda_food_to_diary(auth_client):
    """
    Tests adding a USDA food to the diary and correct calorie calculation.
    """
    with auth_client.application.app_context():
        # Create a sample USDA Food and Nutrients
        test_food = Food(fdc_id=10001, description='USDA Apple')
        db.session.add(test_food)
        db.session.add(Nutrient(id=1008, name='Energy', unit_name='kcal'))
        db.session.add(FoodNutrient(fdc_id=10001, nutrient_id=1008, amount=150.0)) # 150 kcal per 100g
        db.session.commit()

    # Add 200g of USDA Apple to diary
    diary_data = {
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Breakfast',
        'quantity': 200,
        'portion_id': 'g',
        'fdc_id': 10001
    }
    response = auth_client.post('/diary/add_entry', data=diary_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Food added to diary.' in response.data

    # Check total calories on diary page
    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    # Expected calories: 150 kcal/100g * 200g = 300 kcal
    assert b'<strong>Calories:</strong> 300' in response.data

def test_add_my_food_to_diary(auth_client):
    """
    Tests adding a custom food to the diary and correct calorie calculation.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood(
            user_id=user.id,
            description='My Custom Bread',
            calories_per_100g=250.0, # 250 kcal per 100g
            protein_per_100g=10.0,
            carbs_per_100g=50.0,
            fat_per_100g=5.0
        )
        db.session.add(my_food)
        db.session.commit()
        my_food_id = my_food.id

    # Add 150g of My Custom Bread to diary
    diary_data = {
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Lunch',
        'quantity': 150,
        'portion_id': 'g',
        'my_food_id': my_food_id
    }
    response = auth_client.post('/diary/add_entry', data=diary_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Food added to diary.' in response.data

    # Check total calories on diary page
    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    # Expected calories: 250 kcal/100g * 150g = 375 kcal
    assert b'<strong>Calories:</strong> 375' in response.data

def test_delete_diary_entry(auth_client):
    """
    Tests deleting a diary entry.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        # Add a dummy entry to delete
        log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name='Dinner',
            amount_grams=100,
            fdc_id=10001 # Using the same fdc_id as in test_add_usda_food_to_diary
        )
        db.session.add(log_entry)
        db.session.commit()
        log_id = log_entry.id

    response = auth_client.post(f'/diary/delete/{log_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Entry deleted.' in response.data

    with auth_client.application.app_context():
        deleted_log = db.session.get(DailyLog, log_id)
        assert deleted_log is None

def test_add_usda_food_with_portion(auth_client):
    """
    Tests adding a USDA food with a specific portion and verifies the gram amount.
    """
    with auth_client.application.app_context():
        test_food = Food(fdc_id=10002, description='USDA Cheese')
        db.session.add(test_food)
        measure_unit = MeasureUnit(id=9999, name='unit')
        db.session.add(measure_unit)
        portion = Portion(id=1, fdc_id=10002, seq_num=1, measure_unit_id=9999, portion_description='slice', gram_weight=28.0)
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    diary_data = {
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Snack',
        'quantity': 2,
        'portion_id': portion_id,
        'fdc_id': 10002
    }
    auth_client.post('/diary/add_entry', data=diary_data)

    with auth_client.application.app_context():
        log_entry = DailyLog.query.filter_by(fdc_id=10002).first()
        assert log_entry is not None
        assert log_entry.amount_grams == 56.0

def test_add_my_food_with_portion(auth_client):
    """
    Tests adding a custom food with a specific portion and verifies the gram amount.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood(user_id=user.id, description='My Custom Nuts', calories_per_100g=600)
        db.session.add(my_food)
        db.session.commit()
        my_food_id = my_food.id

        my_portion = MyPortion(my_food_id=my_food_id, description='handful', gram_weight=40.0)
        db.session.add(my_portion)
        db.session.commit()
        my_portion_id = my_portion.id

    diary_data = {
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Snack',
        'quantity': 3,
        'portion_id': my_portion_id,
        'my_food_id': my_food_id
    }
    auth_client.post('/diary/add_entry', data=diary_data)

    with auth_client.application.app_context():
        log_entry = DailyLog.query.filter_by(my_food_id=my_food_id).first()
        assert log_entry is not None
        assert log_entry.amount_grams == 120.0