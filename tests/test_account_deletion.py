import pytest
from datetime import date
from flask import url_for
from models import db, User, UserGoal, CheckIn, DailyLog, ExerciseLog, MyFood, Recipe, Friendship, RecipeIngredient, MyMealItem
from flask_login import current_user

@pytest.fixture
def user_a(app_with_db):
    with app_with_db.app_context():
        user = User(username='usera', email='usera@example.com')
        user.set_password('passwordA')
        db.session.add(user)
        db.session.commit()
        return user.id

@pytest.fixture
def user_b(app_with_db):
    with app_with_db.app_context():
        user = User(username='userb', email='userb@example.com')
        user.set_password('passwordB')
        db.session.add(user)
        db.session.commit()
        return user.id

@pytest.fixture
def setup_shared_content(app_with_db, user_a, user_b):
    with app_with_db.app_context():
        user_a_obj = db.session.get(User, user_a)
        user_b_obj = db.session.get(User, user_b)

        # User A's shared content
        my_food_a = MyFood(user_id=user_a_obj.id, description="Alice's Chili", calories_per_100g=100)
        recipe_a = Recipe(user_id=user_a_obj.id, name="Alice's Pie", servings=8, calories_per_100g=200, is_public=True)
        db.session.add_all([my_food_a, recipe_a])
        db.session.commit()

        # User B logs Alice's Chili
        daily_log_b = DailyLog(user_id=user_b_obj.id, log_date=date(2025, 1, 1), meal_name='Lunch', my_food_id=my_food_a.id, amount_grams=200)
        db.session.add(daily_log_b)
        db.session.commit()

        # User B creates a recipe using Alice's Pie as an ingredient
        recipe_b = Recipe(user_id=user_b_obj.id, name="Bob's Stew", servings=4, calories_per_100g=150)
        db.session.add(recipe_b)
        db.session.commit()
        recipe_ingredient_b = RecipeIngredient(recipe_id=recipe_b.id, recipe_id_link=recipe_a.id, amount_grams=100)
        db.session.add(recipe_ingredient_b)
        db.session.commit()

        return {
            'my_food_a_id': my_food_a.id,
            'recipe_a_id': recipe_a.id,
            'daily_log_b_id': daily_log_b.id,
            'recipe_b_id': recipe_b.id,
            'recipe_ingredient_b_id': recipe_ingredient_b.id
        }


def login(client, username, password):
    return client.post(
        url_for('auth.login'),
        data={'username_or_email': username, 'password': password},
        follow_redirects=True
    )


def test_account_deletion_anonymizes_and_deletes_correctly(app_with_db, client, user_a):
    with app_with_db.app_context():
        user_a_obj = db.session.get(User, user_a)
        # Setup personal data for User A
        user_goal_a = UserGoal(user_id=user_a_obj.id, calories=2000)
        check_in_a = CheckIn(user_id=user_a_obj.id, weight_kg=70)
        daily_log_a = DailyLog(user_id=user_a_obj.id, log_date=date(2025, 1, 1), meal_name='Breakfast', amount_grams=100)
        exercise_log_a = ExerciseLog(user_id=user_a_obj.id, duration_minutes=30, calories_burned=300)
        db.session.add_all([user_goal_a, check_in_a, daily_log_a, exercise_log_a])

        # Setup shared content for User A
        my_food_a = MyFood(user_id=user_a_obj.id, description="UserA's Food", calories_per_100g=100)
        recipe_a = Recipe(user_id=user_a_obj.id, name="UserA's Recipe", servings=1, calories_per_100g=200)
        db.session.add_all([my_food_a, recipe_a])
        db.session.commit()
        my_food_a_id = my_food_a.id
        recipe_a_id = recipe_a.id

        # Log in as User A
        login(client, user_a_obj.username, 'passwordA')

        # Simulate account deletion
        response = client.post(
            url_for('settings.delete_account'),
            data={'password': 'passwordA'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b'Your account has been permanently deleted' in response.data
        assert b'Sign In' in response.data # Redirected to login/homepage

        # Assertions
        # User A's record should be deleted
        assert User.query.get(user_a) is None

        # Personal data should be deleted
        assert UserGoal.query.filter_by(user_id=user_a).first() is None
        assert CheckIn.query.filter_by(user_id=user_a).first() is None
        assert DailyLog.query.filter_by(user_id=user_a).first() is None
        assert ExerciseLog.query.filter_by(user_id=user_a).first() is None

        # Shared content should exist but be anonymized
        orphaned_my_food = MyFood.query.get(my_food_a_id)
        assert orphaned_my_food is not None
        assert orphaned_my_food.user_id is None

        orphaned_recipe = Recipe.query.get(recipe_a_id)
        assert orphaned_recipe is not None
        assert orphaned_recipe.user_id is None


def test_deletion_does_not_break_other_users_data(app_with_db, client, user_a, user_b, setup_shared_content):
    with app_with_db.app_context():
        user_a_obj = db.session.get(User, user_a)

        my_food_a_id = setup_shared_content['my_food_a_id']
        recipe_a_id = setup_shared_content['recipe_a_id']
        daily_log_b_id = setup_shared_content['daily_log_b_id']
        recipe_b_id = setup_shared_content['recipe_b_id']
        recipe_ingredient_b_id = setup_shared_content['recipe_ingredient_b_id']

        # Log in as User A and delete account
        login(client, user_a_obj.username, 'passwordA')
        client.post(
            url_for('settings.delete_account'),
            data={'password': 'passwordA'},
            follow_redirects=True
        )

        # Assertions
        # User A's shared content should exist but be anonymized
        orphaned_my_food = MyFood.query.get(my_food_a_id)
        assert orphaned_my_food is not None
        assert orphaned_my_food.user_id is None

        orphaned_recipe = Recipe.query.get(recipe_a_id)
        assert orphaned_recipe is not None
        assert orphaned_recipe.user_id is None

        # User B's daily log entry should still exist and link correctly
        retrieved_daily_log_b = DailyLog.query.get(daily_log_b_id)
        assert retrieved_daily_log_b is not None
        assert retrieved_daily_log_b.my_food_id == orphaned_my_food.id

        # User B's recipe and ingredient should still exist and link correctly
        retrieved_recipe_b = Recipe.query.get(recipe_b_id)
        assert retrieved_recipe_b is not None
        retrieved_recipe_ingredient_b = RecipeIngredient.query.get(recipe_ingredient_b_id)
        assert retrieved_recipe_ingredient_b is not None
        assert retrieved_recipe_ingredient_b.recipe_id_link == orphaned_recipe.id


def test_ui_handles_orphaned_content_gracefully(app_with_db, client, user_a, user_b, setup_shared_content):
    with app_with_db.app_context():
        user_a_obj = db.session.get(User, user_a)
        user_b_obj = db.session.get(User, user_b)

        # Establish friendship for search visibility
        friendship = Friendship(requester_id=user_a_obj.id, receiver_id=user_b_obj.id, status='accepted')
        db.session.add(friendship)
        db.session.commit()

        # Log in as User A and delete account
        login(client, user_a_obj.username, 'passwordA')
        client.post(
            url_for('settings.delete_account'),
            data={'password': 'passwordA'},
            follow_redirects=True
        )

        # Log in as User B
        login(client, user_b_obj.username, 'passwordB')

        # Test User B's diary page (should contain Alice's Chili)
        diary_response = client.get(url_for('diary.diary', log_date_str=date(2025, 1, 1).isoformat()))
        assert diary_response.status_code == 200
        assert b'(deleted user)' in diary_response.data
        assert b"Alice&#39;s Chili" in diary_response.data

        # Test search page for friends' content (should show Alice's Pie as orphaned)
        search_response = client.get(url_for('search.search', search_friends=True, search_term="Alice's Pie"))
        assert search_response.status_code == 200
        assert b'(deleted user)' in search_response.data
        assert b"Alice&#39;s Pie" in search_response.data


def test_delete_account_fails_with_incorrect_password(app_with_db, client, user_a):
    with app_with_db.app_context():
        user_a_obj = db.session.get(User, user_a)
        # Setup personal data for User A
        user_goal_a = UserGoal(user_id=user_a_obj.id, calories=2000)
        my_food_a = MyFood(user_id=user_a_obj.id, description="UserA's Food", calories_per_100g=100)
        db.session.add_all([user_goal_a, my_food_a])
        db.session.commit()

        # Log in as User A
        login(client, user_a_obj.username, 'passwordA')

        # Attempt to delete with incorrect password
        response = client.post(
            url_for('settings.delete_account'),
            data={'password': 'wrongpassword'},
            follow_redirects=True
        )

        # Assertions
        assert response.status_code == 200
        assert b'Incorrect password.' in response.data
        assert b'Confirm Account Deletion' in response.data # Should remain on the confirmation page

        # User A's record and data should NOT be deleted
        assert User.query.get(user_a) is not None
        assert UserGoal.query.filter_by(user_id=user_a).first() is not None
        assert MyFood.query.filter_by(user_id=user_a).first() is not None