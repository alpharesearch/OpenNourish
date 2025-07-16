import pytest
from datetime import date
from models import db, DailyLog, MyMeal, MyMealItem, Food, MyFood, User

def test_save_meal_from_diary(auth_client_with_user):
    """
    Test saving a meal from the diary.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a DailyLog entry
        daily_log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name='Breakfast',
            fdc_id=12345,  # Example FDC ID
            amount_grams=100
        )
        db.session.add(daily_log_entry)
        db.session.commit()

        # POST to save the meal
        response = client.post('/diary/save_meal', data={
            'log_date': date.today().isoformat(),
            'meal_name': 'Breakfast',
            'new_meal_name': 'My Saved Breakfast'
        }, follow_redirects=True)
        assert response.status_code == 200

        # Assert that new MyMeal and MyMealItem objects are created
        saved_meal = MyMeal.query.filter_by(user_id=user.id, name='My Saved Breakfast').first()
        assert saved_meal is not None
        assert len(saved_meal.items) == 1
        assert saved_meal.items[0].fdc_id == 12345
        assert saved_meal.items[0].amount_grams == 100

def test_my_meals_list_view(auth_client_with_user):
    """
    Test the My Meals list view.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a MyMeal object
        meal = MyMeal(user_id=user.id, name='My Test Meal')
        db.session.add(meal)
        db.session.commit()

        # Perform GET request to /my_meals
        response = client.get('/my_meals')
        assert response.status_code == 200
        assert b'My Test Meal' in response.data

def test_delete_my_meal(auth_client_with_user):
    """
    Test deleting a MyMeal object.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a MyMeal object with an item
        meal = MyMeal(user_id=user.id, name='Meal to Delete')
        db.session.add(meal)
        db.session.commit() # Commit to get meal.id

        meal_item = MyMealItem(my_meal_id=meal.id, fdc_id=54321, amount_grams=50)
        db.session.add(meal_item)
        db.session.commit()

        meal_id = meal.id

        # POST to delete the meal
        response = client.post(f'/my_meals/{meal_id}/delete', follow_redirects=True)
        assert response.status_code == 200

        # Assert that the meal and its items are deleted
        deleted_meal = db.session.get(MyMeal, meal_id)
        assert deleted_meal is None
        deleted_item = MyMealItem.query.filter_by(my_meal_id=meal_id).first()
        assert deleted_item is None