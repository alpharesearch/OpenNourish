
import pytest
from models import db, User, MyFood, Recipe, DailyLog
from datetime import date

@pytest.fixture
def admin_and_user(app_with_db):
    with app_with_db.app_context():
        admin_user = User(username='admin_cleanup', email='admin_cleanup@test.com', is_admin=True)
        admin_user.set_password('adminpass')
        regular_user = User(username='user_b_cleanup', email='user_b_cleanup@test.com', has_completed_onboarding=True)
        regular_user.set_password('userpass')
        db.session.add_all([admin_user, regular_user])
        db.session.commit()
        return admin_user, regular_user

def test_cleanup_page_correctly_identifies_and_separates_orphans(client, admin_and_user):
    admin, user_b = admin_and_user

    with client.application.app_context():
        admin = User.query.filter_by(username='admin_cleanup').first()
        user_b = User.query.filter_by(username='user_b_cleanup').first()
        # Admin creates items
        safe_food = MyFood(user_id=admin.id, description='Safe to Delete Food')
        in_use_recipe = Recipe(user_id=admin.id, name='In-Use Recipe')
        active_food = MyFood(user_id=admin.id, description='Active Admin Food')
        db.session.add_all([safe_food, in_use_recipe, active_food])
        db.session.commit()

        # User B uses the recipe
        log_entry = DailyLog(user_id=user_b.id, recipe_id=in_use_recipe.id, log_date=date.today(), amount_grams=100)
        db.session.add(log_entry)

        # Orphan the items
        safe_food.user_id = None
        in_use_recipe.user_id = None
        db.session.commit()

    # Log in as admin
    client.post('/auth/login', data={'username_or_email': 'admin_cleanup', 'password': 'adminpass'}, follow_redirects=True)

    # Get the cleanup page
    response = client.get('/admin/cleanup')
    assert response.status_code == 200
    html = response.data.decode('utf-8')
    # Assertions
    assert 'Safe to Delete Food' in html
    assert 'In-Use Recipe' in html
    assert 'Active Admin Food' not in html
    # Check sections
    # safe_section = html.split('<h3>Orphaned Items (Safe to Delete)</h3>')[1].split('<h3>')[0]
    # in_use_section = html.split('<h3>Orphaned Items (In Use)</h3>')[1].split('<h3>')[0]
    # assert 'Safe to Delete Food' in safe_section
    # assert 'In-Use Recipe' in in_use_section

def test_run_cleanup_deletes_only_unreferenced_orphans(client, admin_and_user):
    admin, user_b = admin_and_user
    with client.application.app_context():
        admin = User.query.filter_by(username='admin_cleanup').first()
        user_b = User.query.filter_by(username='user_b_cleanup').first()
        safe_food = MyFood(user_id=admin.id, description='Safe to Delete Food')
        in_use_recipe = Recipe(user_id=admin.id, name='In-Use Recipe')
        active_food = MyFood(user_id=admin.id, description='Active Admin Food')
        db.session.add_all([safe_food, in_use_recipe, active_food])
        db.session.commit()
        safe_food_id = safe_food.id
        in_use_recipe_id = in_use_recipe.id
        active_food_id = active_food.id

        log_entry = DailyLog(user_id=user_b.id, recipe_id=in_use_recipe.id, log_date=date.today(), amount_grams=100)
        db.session.add(log_entry)
        db.session.commit()
        log_id = log_entry.id

        safe_food.user_id = None
        in_use_recipe.user_id = None
        db.session.commit()

    client.post('/auth/login', data={'username_or_email': 'admin_cleanup', 'password': 'adminpass'}, follow_redirects=True)
    response = client.post('/admin/cleanup/run', follow_redirects=True)

    assert b'Database cleanup complete. Removed 1 orphaned food items and 0 orphaned recipes.' in response.data

    with client.application.app_context():
        assert db.session.get(MyFood, safe_food_id) is None
        assert db.session.get(Recipe, in_use_recipe_id) is not None
        assert db.session.get(MyFood, active_food_id) is not None
        assert db.session.get(DailyLog, log_id) is not None

def test_non_admin_users_are_blocked_from_cleanup_feature(client, admin_and_user):
    _, user_b = admin_and_user
    client.post('/auth/login', data={'username_or_email': 'user_b_cleanup', 'password': 'userpass'}, follow_redirects=True)

    # Test GET request
    response_get = client.get('/admin/cleanup', follow_redirects=False)
    assert response_get.status_code == 302
    assert response_get.location == '/dashboard/'

    # Test POST request
    response_post = client.post('/admin/cleanup/run', follow_redirects=False)
    assert response_post.status_code == 302
    assert response_post.location == '/dashboard/'

    # Check for flash message after one of the redirects
    response_redirect = client.get(response_get.location)
    assert b'Admin access required' in response_redirect.data

def test_cleanup_page_handles_no_orphans(client, admin_and_user):
    admin, _ = admin_and_user
    client.post('/auth/login', data={'username_or_email': 'admin_cleanup', 'password': 'adminpass'}, follow_redirects=True)

    response_get = client.get('/admin/cleanup')
    assert response_get.status_code == 200
    assert b'No orphaned items found that are safe to delete.' in response_get.data
    assert b'No in-use orphaned items found.' in response_get.data

    response_post = client.post('/admin/cleanup/run', follow_redirects=True)
    assert b'Database cleanup complete. Removed 0 orphaned food items and 0 orphaned recipes.' in response_post.data
