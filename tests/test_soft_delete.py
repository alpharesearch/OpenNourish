
import pytest
from models import db, User, MyFood, Recipe, DailyLog
from datetime import date

@pytest.fixture
def two_users_with_friendship(app_with_db):
    with app_with_db.app_context():
        user_a = User(username='user_a_soft_delete', email='user_a_soft_delete@example.com')
        user_a.set_password('password_a')
        user_b = User(username='user_b_soft_delete', email='user_b_soft_delete@example.com')
        user_b.set_password('password_b')
        user_a.friends.append(user_b)
        db.session.add_all([user_a, user_b])
        db.session.commit()
        return user_a, user_b

def test_delete_anonymizes_item_and_hides_from_owner(client, two_users_with_friendship):
    user_a, _ = two_users_with_friendship
    
    # Log in as User A
    client.post('/auth/login', data={'username_or_email': 'user_a_soft_delete', 'password': 'password_a'}, follow_redirects=True)

    with client.application.app_context():
        user_a = User.query.filter_by(username='user_a_soft_delete').first()
        # User A creates a MyFood item
        my_food = MyFood(user_id=user_a.id, description='Food to be Orphaned')
        db.session.add(my_food)
        db.session.commit()
        food_id = my_food.id

    # User A deletes the item
    client.post(f'/my_foods/{food_id}/delete', follow_redirects=True)

    with client.application.app_context():
        # Assert the record still exists
        orphaned_food = db.session.get(MyFood, food_id)
        assert orphaned_food is not None
        # Assert its user_id is now NULL
        assert orphaned_food.user_id is None

    # Assert the food is not in User A's list view
    response = client.get('/my_foods/')
    assert response.status_code == 200
    assert b'Food to be Orphaned' not in response.data

def test_soft_delete_preserves_other_users_data_integrity(client, two_users_with_friendship):
    user_a, user_b = two_users_with_friendship

    with client.application.app_context():
        user_a = User.query.filter_by(username='user_a_soft_delete').first()
        # User A creates a Recipe
        recipe = Recipe(user_id=user_a.id, name='Shared Pie')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    # Log in as User B
    client.post('/auth/login', data={'username_or_email': 'user_b_soft_delete', 'password': 'password_b'}, follow_redirects=True)

    with client.application.app_context():
        user_b = User.query.filter_by(username='user_b_soft_delete').first()
        # User B logs the recipe
        log_entry = DailyLog(user_id=user_b.id, recipe_id=recipe_id, log_date=date.today(), amount_grams=1, meal_name='Lunch')
        db.session.add(log_entry)
        db.session.commit()
        log_id = log_entry.id

    # Log in as User A
    client.post('/auth/login', data={'username_or_email': 'user_a_soft_delete', 'password': 'password_a'}, follow_redirects=True)

    # User A deletes the recipe
    client.post(f'/recipes/{recipe_id}/delete', follow_redirects=True)

    # Log in as User B again
    client.post('/auth/login', data={'username_or_email': 'user_b_soft_delete', 'password': 'password_b'}, follow_redirects=True)

    with client.application.app_context():
        # Assert User B's log entry still exists and points to the orphaned recipe
        retrieved_log = db.session.get(DailyLog, log_id)
        assert retrieved_log is not None
        assert retrieved_log.recipe_id == recipe_id

    # Assert User B's diary page doesn't crash
    response = client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')
    assert response.status_code == 200

def test_ui_gracefully_displays_orphaned_items(client, two_users_with_friendship):
    user_a, user_b = two_users_with_friendship

    with client.application.app_context():
        user_a = User.query.filter_by(username='user_a_soft_delete').first()
        recipe = Recipe(user_id=user_a.id, name='Shared Pie')
        db.session.add(recipe)
        db.session.commit()
        recipe_id = recipe.id

    client.post('/auth/login', data={'username_or_email': 'user_b_soft_delete', 'password': 'password_b'}, follow_redirects=True)

    with client.application.app_context():
        user_b = User.query.filter_by(username='user_b_soft_delete').first()
        log_entry = DailyLog(user_id=user_b.id, recipe_id=recipe_id, log_date=date.today(), amount_grams=1, meal_name='Dinner')
        db.session.add(log_entry)
        db.session.commit()

    client.post('/auth/login', data={'username_or_email': 'user_a_soft_delete', 'password': 'password_a'}, follow_redirects=True)
    client.post(f'/recipes/{recipe_id}/delete', follow_redirects=True)

    client.post('/auth/login', data={'username_or_email': 'user_b_soft_delete', 'password': 'password_b'}, follow_redirects=True)
    response = client.get(f'/diary/{date.today().strftime("%Y-%m-%d")}')

    assert response.status_code == 200
    html = response.data.decode('utf-8')
    assert 'Shared Pie' in html
    assert '(deleted user)' in html

def test_user_cannot_soft_delete_another_users_item(client, two_users_with_friendship):
    user_a, user_b = two_users_with_friendship

    with client.application.app_context():
        user_a = User.query.filter_by(username='user_a_soft_delete').first()
        # User A creates a food item
        food_a = MyFood(user_id=user_a.id, description="User A's Food")
        db.session.add(food_a)
        db.session.commit()
        food_a_id = food_a.id

    # Log in as User B
    client.post('/auth/login', data={'username_or_email': 'user_b_soft_delete', 'password': 'password_b'}, follow_redirects=True)

    # User B attempts to delete User A's food
    response = client.post(f'/my_foods/{food_a_id}/delete', follow_redirects=False)

    # Assert that the action is not found
    assert response.status_code == 404

    # Assert that the food item still exists and its user_id is unchanged
    with client.application.app_context():
        user_a = User.query.filter_by(username='user_a_soft_delete').first()
        food_still_exists = db.session.get(MyFood, food_a_id)
        assert food_still_exists is not None
        assert food_still_exists.user_id == user_a.id
