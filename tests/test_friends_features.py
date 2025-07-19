import pytest
from models import db, User, Recipe, MyFood, MyMeal, Friendship, RecipeIngredient, MyMealItem, UnifiedPortion, DailyLog
from flask_login import login_user
from datetime import date

# Helper function to create users
def create_test_user(username, password='password'):
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def setup_friend_data(friend_user):
    """Helper function to create test data for the friend user."""
    # Friend_user creates a recipe, a food, and a meal
    friend_recipe = Recipe(user_id=friend_user.id, name="Friend's Recipe", instructions="Friend's instructions", servings=2, is_public=False)
    db.session.add(friend_recipe)

    friend_food = MyFood(user_id=friend_user.id, description="Friend's Food", calories_per_100g=100)
    db.session.add(friend_food)

    friend_meal = MyMeal(user_id=friend_user.id, name="Friend's Meal")
    db.session.add(friend_meal)
    db.session.commit()

    return friend_recipe, friend_food, friend_meal

def test_view_friends_recipes(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    friend_recipe, _, _ = setup_friend_data(friend_user)

    # Access friends' recipes page
    response = client.get('/recipes?view=friends', follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Recipe" in response.data
    assert b"Copy" in response.data
    assert b"Edit" not in response.data

def test_copy_recipe(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    friend_recipe, _, _ = setup_friend_data(friend_user)

    # Copy the recipe
    response = client.post(f'/recipes/{friend_recipe.id}/copy', follow_redirects=True)
    assert response.status_code == 200
    assert b"Successfully copied" in response.data

    # Verify the new recipe exists and is owned by the current user
    copied_recipe = Recipe.query.filter_by(name="Friend's Recipe", user_id=test_user.id).first()
    assert copied_recipe is not None
    assert copied_recipe.id != friend_recipe.id

def test_view_friends_foods(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    _, friend_food, _ = setup_friend_data(friend_user)

    response = client.get('/my_foods?view=friends', follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Food" in response.data
    assert b"Copy" in response.data

def test_copy_my_food(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    _, friend_food, _ = setup_friend_data(friend_user)

    response = client.post(f'/my_foods/{friend_food.id}/copy', follow_redirects=True)
    assert response.status_code == 200
    assert b"Successfully copied" in response.data

    copied_food = MyFood.query.filter_by(description="Friend's Food", user_id=test_user.id).first()
    assert copied_food is not None
    assert copied_food.id != friend_food.id

def test_view_friends_meals(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    _, _, friend_meal = setup_friend_data(friend_user)

    response = client.get('/my_meals?view=friends', follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Meal" in response.data
    assert b"Copy" in response.data

def test_copy_my_meal(auth_client_with_friendship, faker):
    client, test_user, friend_user = auth_client_with_friendship
    _, _, friend_meal = setup_friend_data(friend_user)

    response = client.post(f'/my_meals/{friend_meal.id}/copy', follow_redirects=True)
    assert response.status_code == 200
    assert b"Successfully copied" in response.data

    copied_meal = MyMeal.query.filter_by(name="Friend's Meal", user_id=test_user.id).first()
    assert copied_meal is not None
    assert copied_meal.id != friend_meal.id

def test_search_friends_content(auth_client_with_friendship):
    client, test_user, friend_user = auth_client_with_friendship
    setup_friend_data(friend_user)

    # Search without including friends
    response = client.post('/search/', data={'search_term': 'Friend'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Recipe" not in response.data
    assert b"Friend&#39;s Food" not in response.data

    # Search including friends
    response = client.post('/search/', data={'search_term': 'Friend', 'search_friends': 'true'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Recipe" in response.data
    assert b"Friend&#39;s Food" in response.data
    assert b"by friend" in response.data
    assert b"Copy" in response.data

def test_friends_diary_display_3_meals_empty_day(auth_client_with_friendship):
    """
    Tests that on an empty day, only 3 main meals are displayed for a friend's diary when their meals_per_day is 3.
    """
    client, test_user, friend_user = auth_client_with_friendship
    with client.application.app_context():
        # Re-associate the detached friend_user object with the current session
        db.session.add(friend_user)
        friend_user.meals_per_day = 3
        db.session.commit()

        response = client.get(f'/user/{friend_user.username}/diary/{date.today().strftime("%Y-%m-%d")}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Breakfast' in response.data
        assert b'Lunch' in response.data
        assert b'Dinner' in response.data
        assert b'Snack (morning)' not in response.data
        assert b'Snack (afternoon)' not in response.data
        assert b'Snack (evening)' not in response.data
        assert b'Unspecified' not in response.data

def test_friends_diary_display_6_meals_empty_day(auth_client_with_friendship):
    """
    Tests that on an empty day, all 6 meal types are displayed for a friend's diary when their meals_per_day is 6.
    """
    client, test_user, friend_user = auth_client_with_friendship
    with client.application.app_context():
        db.session.add(friend_user)
        friend_user.meals_per_day = 6
        db.session.commit()

        response = client.get(f'/user/{friend_user.username}/diary/{date.today().strftime("%Y-%m-%d")}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Breakfast' in response.data
        assert b'Snack (morning)' in response.data
        assert b'Lunch' in response.data
        assert b'Snack (afternoon)' in response.data
        assert b'Dinner' in response.data
        assert b'Snack (evening)' in response.data
        assert b'Unspecified' not in response.data

def test_friends_diary_display_snack_in_3_meal_mode(auth_client_with_friendship):
    """
    Tests that a snack logged by a friend in 3-meal mode still appears in their diary.
    """
    client, test_user, friend_user = auth_client_with_friendship
    with client.application.app_context():
        db.session.add(friend_user)
        friend_user.meals_per_day = 3
        db.session.commit()

        # Log a snack for the friend
        log_entry = DailyLog(
            user_id=friend_user.id,
            log_date=date.today(),
            meal_name='Snack (morning)',
            amount_grams=100,
            fdc_id=10001 # Using a dummy fdc_id
        )
        db.session.add(log_entry)
        db.session.commit()

        response = client.get(f'/user/{friend_user.username}/diary/{date.today().strftime("%Y-%m-%d")}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Breakfast' in response.data
        assert b'Lunch' in response.data
        assert b'Dinner' in response.data
        assert b'Snack (morning)' in response.data # Should still be visible

def test_friends_diary_display_unspecified_meal(auth_client_with_friendship):
    """
    Tests that an unspecified meal logged by a friend still appears in their diary.
    """
    client, test_user, friend_user = auth_client_with_friendship
    with client.application.app_context():
        db.session.add(friend_user)
        friend_user.meals_per_day = 3 # Can be 3 or 6, unspecified should always show
        #db.session.commit()

        # Log an unspecified meal for the friend
        log_entry = DailyLog(
            user_id=friend_user.id,
            log_date=date.today(),
            meal_name='Unspecified',
            amount_grams=100,
            fdc_id=10001 # Using a dummy fdc_id
        )
        db.session.add(log_entry)
        db.session.commit()

        response = client.get(f'/user/{friend_user.username}/diary/{date.today().strftime("%Y-%m-%d")}', follow_redirects=True)
        assert response.status_code == 200
        assert b'Unspecified' in response.data
