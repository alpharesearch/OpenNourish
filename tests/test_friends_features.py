import pytest
from models import db, User, Recipe, MyFood, MyMeal, Friendship, RecipeIngredient, MyMealItem, UnifiedPortion
from flask_login import login_user

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
    response = client.post('/search/', data={'search_term': 'Friend', 'include_friends': 'true'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Friend&#39;s Recipe" in response.data
    assert b"Friend&#39;s Food" in response.data
    assert b"by friend" in response.data
    assert b"Copy" in response.data