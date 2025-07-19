import pytest
from models import db, User
from flask_login import current_user

@pytest.fixture
def admin_client_two_users(app_with_db):
    """Fixture for providing an admin and a regular user."""
    with app_with_db.app_context():
        admin_user = User(username='admin', email='admin@example.com', is_admin=True, has_completed_onboarding=True)
        admin_user.set_password('password')
        db.session.add(admin_user)

        regular_user = User(username='user', email='user@example.com', has_completed_onboarding=True)
        regular_user.set_password('password')
        db.session.add(regular_user)
        db.session.commit()

        with app_with_db.test_client() as client:
            # Log in as admin
            with client.session_transaction() as sess:
                sess['_user_id'] = admin_user.id
                sess['_fresh'] = True
            yield client, admin_user, regular_user

def test_disabled_user_cannot_login(client):
    """Test that a user whose is_active flag is False cannot log in."""
    # Create a user and disable them
    with client.application.app_context():
        disabled_user = User(username='disableduser', email='disabled@example.com', is_active=False)
        disabled_user.set_password('password')
        db.session.add(disabled_user)
        db.session.commit()

    # Attempt to log in
    response = client.post(
        '/auth/login',
        data={'username_or_email': 'disableduser', 'password': 'password'},
        follow_redirects=True
    )

    assert response.status_code == 200
    assert b'This account has been disabled.' in response.data
    # Ensure the user is redirected back to the login page
    assert b'Sign In' in response.data

def test_admin_can_access_user_management_page(admin_client_two_users):
    client, _, _ = admin_client_two_users
    response = client.get('/admin/users')
    assert response.status_code == 200
    assert b'User Management' in response.data

def test_non_admin_cannot_access_user_management_page(client):
    # Create and log in a non-admin user
    with client.application.app_context():
        user = User(username='nonadmin', email='nonadmin@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
    client.post('/auth/login', data={'username_or_email': 'nonadmin', 'password': 'password'})

    response = client.get('/admin/users', follow_redirects=True)
    assert response.status_code == 200
    assert b'Admin access required.' in response.data

def test_user_management_page_content(admin_client_two_users):
    client, admin_user, regular_user = admin_client_two_users
    response = client.get('/admin/users')
    assert b'admin' in response.data
    assert b'user' in response.data
    assert b'>Admin</span>' in response.data
    assert b'>Active</span>' in response.data
    # Check that there are no action buttons for the admin
    assert b'/users/1/disable' not in response.data

def test_admin_can_disable_and_enable_user(admin_client_two_users):
    client, _, regular_user = admin_client_two_users
    # Disable the user
    client.post(f'/admin/users/{regular_user.id}/disable', follow_redirects=True)
    with client.application.app_context():
        disabled_user = db.session.get(User, regular_user.id)
        assert not disabled_user.is_active

    # Enable the user
    client.post(f'/admin/users/{regular_user.id}/enable', follow_redirects=True)
    with client.application.app_context():
        enabled_user = db.session.get(User, regular_user.id)
        assert enabled_user.is_active

def test_admin_cannot_disable_own_account(admin_client_two_users):
    client, admin_user, _ = admin_client_two_users
    response = client.post(f'/admin/users/{admin_user.id}/disable', follow_redirects=True)
    assert b'You cannot disable your own account.' in response.data
    with client.application.app_context():
        admin = db.session.get(User, admin_user.id)
        assert admin.is_active

def test_navigation_links(admin_client_two_users):
    client, _, _ = admin_client_two_users
    response = client.get('/dashboard/')
    assert b'User Management' in response.data

    # Log out admin and log in as regular user
    client.get('/auth/logout')
    client.post('/auth/login', data={'username_or_email': 'user', 'password': 'password'})
    response = client.get('/dashboard/')
    assert b'User Management' not in response.data
