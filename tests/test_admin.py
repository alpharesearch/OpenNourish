import pytest
from models import db, User
from flask import url_for, current_app, get_flashed_messages
import os
import json

# Helper function to create users
def create_test_user(username, password='password', user_id=None, email=None):
    if email is None:
        email = f'{username}@example.com'
    user = User(username=username, id=user_id, email=email) if user_id else User(username=username, email=email)
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
        non_admin_user.has_completed_onboarding = True
        db.session.add(non_admin_user)
        db.session.commit()
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
        admin_user_in_context = db.session.get(User, admin_user_id)
        with client.session_transaction() as sess:
            sess['_user_id'] = admin_user_in_context.id
            sess['_fresh'] = True
        yield client, admin_user_in_context, app_with_db

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

def test_admin_can_access_admin_dashboard(admin_client):
    """Test that the admin user can access the admin dashboard page."""
    client, _, app = admin_client
    response = client.get('/admin/')
    assert response.status_code == 302
    assert response.headers['Location'] == '/admin/dashboard'

def test_admin_can_view_admin_dashboard(admin_client):
    """Test that the admin user can view the admin dashboard content."""
    client, _, app = admin_client
    response = client.get('/admin/dashboard')
    assert response.status_code == 200
    assert b'Admin Dashboard' in response.data
    assert b'Total Users' in response.data

def test_admin_can_access_admin_settings_page_directly(admin_client):
    """Test that the admin user can access the admin settings page directly."""
    client, _, app = admin_client
    response = client.get('/admin/settings')
    assert response.status_code == 200
    assert b'Admin Settings' in response.data

def test_admin_can_disable_and_enable_registration(admin_client):
    """
    Test that the admin can disable and re-enable user registration,
    and that the system correctly handles flash messages on redirect.
    """
    admin_client_instance, admin_user, app = admin_client

    # 1. Admin disables registration by submitting the form without the 'allow_registration' checkbox checked
    response = admin_client_instance.post('/admin/settings', data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Settings have been saved.' in response.data

    # 2. Log out admin user
    response = admin_client_instance.get('/auth/logout', follow_redirects=True)
    assert b'Sign In' in response.data

    # 3. Verify unauthenticated user is redirected from register to login
    # Make the request WITHOUT following redirects to check the session
    register_redirect_response = admin_client_instance.get('/auth/register', follow_redirects=False)
    assert register_redirect_response.status_code == 302
    assert register_redirect_response.headers['Location'] == '/auth/login'

    # Check the session for the flashed message
    with admin_client_instance.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'danger'
        assert flashes[0][1] == 'New user registration is currently disabled.'

    # 4. Follow the redirect and check for the message on the login page
    login_page_response = admin_client_instance.get(register_redirect_response.headers['Location'])
    assert login_page_response.status_code == 200
    assert b'New user registration is currently disabled.' in login_page_response.data
    assert b'<form' in login_page_response.data  # The login form should be present

    # 5. Log admin user back in
    login_response = admin_client_instance.post('/auth/login', data={'username': admin_user.username, 'password': 'password'}, follow_redirects=True)
    assert b'Dashboard' in login_response.data

    # 6. Re-enable registration
    response = admin_client_instance.post('/admin/settings', data={'allow_registration': 'y'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Settings have been saved.' in response.data

    # 7. Log out admin user again
    admin_client_instance.get('/auth/logout', follow_redirects=True)

    # 8. Verify unauthenticated user can now access the register page
    register_enabled_response = admin_client_instance.get('/auth/register', follow_redirects=False)
    assert register_enabled_response.status_code == 200
    assert b'New user registration is currently disabled.' not in register_enabled_response.data
    assert b'Register' in register_enabled_response.data

    # 9. Verify that a new user can be created
    new_user_response = admin_client_instance.post('/auth/register', data={
        'username': 'newuser',
        'password': 'newpassword',
        'password2': 'newpassword'
    }, follow_redirects=True)
    assert new_user_response.status_code == 200
    assert b'Congratulations, you are now a registered user!' in new_user_response.data
    # After registration, user is redirected to the dashboard if goals exist
    assert b'Dashboard' in new_user_response.data