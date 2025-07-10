import pytest
from models import db, User
from flask import url_for, current_app, get_flashed_messages

# Helper function to create users
def create_test_user(username, password='password', user_id=None):
    user = User(username=username, id=user_id) if user_id else User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture(scope='function')
def auth_client_non_admin(app_with_db):
    """A test client that is authenticated as a non-admin user."""
    with app_with_db.app_context():
        # Create a non-admin user (ID != 1)
        non_admin_user = create_test_user('normaluser', user_id=2)
        non_admin_user_id = non_admin_user.id

    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            non_admin_user_in_context = db.session.get(User, non_admin_user_id)
        with client.session_transaction() as sess:
            sess['_user_id'] = non_admin_user_in_context.id
            sess['_fresh'] = True
        yield client, non_admin_user_in_context

@pytest.fixture(scope='function')
def admin_client(app_with_db):
    """A test client that is authenticated as the admin user (ID=1)."""
    with app_with_db.app_context():
        admin_user = create_test_user('adminuser', user_id=1)
        admin_user_id = admin_user.id

    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            admin_user_in_context = db.session.get(User, admin_user_id)
        with client.session_transaction() as sess:
            sess['_user_id'] = admin_user_in_context.id
            sess['_fresh'] = True
        yield client, admin_user_in_context

def test_non_admin_cannot_access_admin_page(auth_client_non_admin):
    """Test that a non-admin user cannot access the admin page."""
    client, _ = auth_client_non_admin
    response = client.get('/admin/', follow_redirects=True)
    assert response.status_code == 200
    assert b'Admin access required.' in response.data
    assert b'/dashboard' in response.request.path.encode()

def test_unauthenticated_user_is_redirected(client):
    """Test that an unauthenticated user is redirected from the admin page to login."""
    response = client.get('/admin/', follow_redirects=False)
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']

def test_admin_can_access_and_view_settings(admin_client):
    """Test that the admin user can access and view the admin settings page."""
    client, _ = admin_client
    response = client.get('/admin/')
    assert response.status_code == 200
    assert b'Admin Settings' in response.data
    assert b'Allow New User Registrations?' in response.data

def test_admin_can_disable_registration(admin_client):
    """Test that the admin can disable user registration via the admin interface."""
    admin_client_instance, admin_user = admin_client

    # 1. Admin disables registration
    response = admin_client_instance.post('/admin/', data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Settings saved!' in response.data

    # 2. Log out admin user
    response = admin_client_instance.get('/auth/logout', follow_redirects=True)
    assert b'Sign In' in response.data

    # 3. Verify unauthenticated user cannot register
    register_initial_response = admin_client_instance.get('/auth/register', follow_redirects=False)
    assert register_initial_response.status_code == 302
    assert '/auth/login' in register_initial_response.headers['Location']

    # Follow the redirect and check for the flashed message on the login page
    login_page_response = admin_client_instance.get(register_initial_response.headers['Location'])
    assert b'New user registration is currently disabled.' in login_page_response.data
    assert b'<form' in login_page_response.data  # The login form should still be present

    # 4. Log admin user back in
    login_response = admin_client_instance.post('/auth/login', data={'username': admin_user.username, 'password': 'password'}, follow_redirects=True)
    assert b'Dashboard' in login_response.data

    # 5. Re-enable registration
    response = admin_client_instance.post('/admin/', data={'allow_registration': 'y'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Settings saved!' in response.data

    # 6. Log out admin user again
    admin_client_instance.get('/auth/logout', follow_redirects=True)

    # 7. Verify unauthenticated user can now register
    register_enabled_response = admin_client_instance.get('/auth/register', follow_redirects=False)
    assert register_enabled_response.status_code == 200  # Should not redirect
    assert b'New user registration is currently disabled.' not in register_enabled_response.data
    assert b'<form' in register_enabled_response.data