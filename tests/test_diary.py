import pytest
from models import db, User, Food, FoodNutrient, Nutrient, MyFood, DailyLog, UnifiedPortion
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
        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(fdc_id=10001, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        gram_portion_id = gram_portion.id

    # Add 200g of USDA Apple to diary
    response = auth_client.post('/search/add_item', data={
        'food_id': 10001,
        'food_type': 'usda',
        'target': 'diary',
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Breakfast',
        'amount': 200,
        'portion_id': gram_portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'USDA Apple added to your diary.' in response.data

    # Check total calories on diary page
    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    # Expected calories: 150 kcal/100g * 200g = 300 kcal
    assert b'Consumed: 300.0 kcal' in response.data

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
        db.session.flush() # Get the ID for the portion
        # Add the mandatory 1-gram portion
        gram_portion = UnifiedPortion(my_food_id=my_food.id, portion_description='gram', gram_weight=1.0)
        db.session.add(gram_portion)
        db.session.commit()
        my_food_id = my_food.id
        gram_portion_id = gram_portion.id

    # Add 150g of My Custom Bread to diary
    response = auth_client.post('/search/add_item', data={
        'food_id': my_food_id,
        'food_type': 'my_food',
        'target': 'diary',
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Lunch',
        'amount': 150,
        'portion_id': gram_portion_id
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'My Custom Bread added to your diary.' in response.data

    # Check total calories on diary page
    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    # Expected calories: 250 kcal/100g * 150g = 375 kcal
    assert b'Consumed: 375.0 kcal' in response.data

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

    response = auth_client.post(f'/diary/log/{log_id}/delete', follow_redirects=True)
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
        portion = UnifiedPortion(fdc_id=10002, portion_description='slice', gram_weight=28.0)
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    auth_client.post('/search/add_item', data={
        'food_id': 10002,
        'food_type': 'usda',
        'target': 'diary',
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Snack',
        'amount': 2, # 2 slices
        'portion_id': portion_id
    })

    with auth_client.application.app_context():
        log_entry = DailyLog.query.filter_by(fdc_id=10002).first()
        assert log_entry is not None
        assert log_entry.amount_grams == 56.0 # 2 * 28.0

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

        my_portion = UnifiedPortion(my_food_id=my_food_id, portion_description='handful', gram_weight=40.0)
        db.session.add(my_portion)
        db.session.commit()
        portion_id = my_portion.id

    auth_client.post('/search/add_item', data={
        'food_id': my_food_id,
        'food_type': 'my_food',
        'target': 'diary',
        'log_date': date.today().strftime('%Y-%m-%d'),
        'meal_name': 'Snack',
        'amount': 3, # 3 handfuls
        'portion_id': portion_id
    })

    with auth_client.application.app_context():
        log_entry = DailyLog.query.filter_by(my_food_id=my_food_id).first()
        assert log_entry is not None
        assert log_entry.amount_grams == 120.0 # 3 * 40.0

def test_diary_display_3_meals_empty_day(auth_client):
    """
    Tests that on an empty day, only 3 main meals are displayed when meals_per_day is 3.
    """
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        user.meals_per_day = 3
        db.session.commit()

    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    assert b'Breakfast\n' in response.data
    assert b'Lunch\n' in response.data
    assert b'Dinner\n' in response.data
    assert b'Snack (morning)\n' not in response.data
    assert b'Snack (afternoon)\n' not in response.data
    assert b'Snack (evening)\n' not in response.data
    assert b'Unspecified' not in response.data

def test_diary_display_6_meals_empty_day(auth_client):
    """
    Tests that on an empty day, all 6 meal types are displayed when meals_per_day is 6.
    """
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        user.meals_per_day = 6
        db.session.commit()

    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    assert b'Breakfast' in response.data
    assert b'Snack (morning)' in response.data
    assert b'Lunch' in response.data
    assert b'Snack (afternoon)' in response.data
    assert b'Dinner' in response.data
    assert b'Snack (evening)' in response.data
    assert b'Unspecified' not in response.data

def test_diary_display_snack_in_3_meal_mode(auth_client):
    """
    Tests that a snack logged in 3-meal mode still appears.
    """
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        user.meals_per_day = 3
        db.session.commit()

        # Log a snack
        log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name='Snack (morning)',
            amount_grams=100,
            fdc_id=10001 # Using a dummy fdc_id
        )
        db.session.add(log_entry)
        db.session.commit()

    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    assert b'Breakfast' in response.data
    assert b'Lunch' in response.data
    assert b'Dinner' in response.data
    assert b'Snack (morning)' in response.data # Should still be visible

def test_diary_display_unspecified_meal(auth_client):
    """
    Tests that an unspecified meal logged still appears.
    """
    with auth_client.application.app_context():
        with auth_client.session_transaction() as sess:
            user_id = sess['_user_id']
        user = db.session.get(User, user_id)
        user.meals_per_day = 3 # Can be 3 or 6, unspecified should always show
        db.session.commit()

        # Log an unspecified meal
        log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name='Unspecified',
            amount_grams=100,
            fdc_id=10001 # Using a dummy fdc_id
        )
        db.session.add(log_entry)
        db.session.commit()

    response = auth_client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200
    assert b'Unspecified' in response.data

def test_update_diary_entry(auth_client):
    """
    Tests updating a diary entry's amount and portion.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        my_food = MyFood(user_id=user.id, description='My Test Food', calories_per_100g=100)
        db.session.add(my_food)
        db.session.commit()

        portion1 = UnifiedPortion(my_food_id=my_food.id, portion_description='g', gram_weight=1.0)
        portion2 = UnifiedPortion(my_food_id=my_food.id, portion_description='serving', gram_weight=50.0)
        db.session.add_all([portion1, portion2])
        db.session.commit()

        log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name='Breakfast',
            my_food_id=my_food.id,
            amount_grams=100, # Initially 100g
            portion_id_fk=portion1.id,
            serving_type='g'
        )
        db.session.add(log_entry)
        db.session.commit()
        log_id = log_entry.id
        portion2_id = portion2.id

    # Update to 2 servings of 50g each
    response = auth_client.post(f'/diary/update_entry/{log_id}', data={
        'amount': 2,
        'portion_id': portion2_id
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Entry updated successfully!' in response.data

    with auth_client.application.app_context():
        updated_log = db.session.get(DailyLog, log_id)
        assert updated_log.amount_grams == 100.0 # 2 * 50.0
        assert updated_log.portion_id_fk == portion2_id
        assert updated_log.serving_type == 'serving'