import pytest
from models import db, User
import os
from flask.testing import FlaskCliRunner

def test_first_registered_user_is_admin(client):
    """
    Tests that the first user to register is automatically granted admin rights.
    """
    # Register the first user
    response = client.post(
        '/auth/register',
        data={'username': 'firstuser', 'email': 'first@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'administrator privileges' in response.data

    # Verify the user's admin status in the database
    with client.application.app_context():
        user = User.query.filter_by(username='firstuser').first()
        assert user is not None
        assert user.is_admin is True

    # Register a second user
    client.get('/auth/logout') # Log out the first user
    response = client.post(
        '/auth/register',
        data={'username': 'seconduser', 'email': 'second@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'administrator privileges' not in response.data

    # Verify the second user is not an admin
    with client.application.app_context():
        user = User.query.filter_by(username='seconduser').first()
        assert user is not None
        assert user.is_admin is False

def test_admin_assignment_via_environment_variable(client):
    """
    Tests that a user whose username matches the INITIAL_ADMIN_USERNAME env var is made an admin.
    """
    # Set the environment variable
    os.environ['INITIAL_ADMIN_USERNAME'] = 'env_admin'

    # Register a non-admin user first to ensure the target user is not the first user
    client.post(
        '/auth/register',
        data={'username': 'another_user', 'email': 'another@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    client.get('/auth/logout')

    # Register the user who should become an admin
    response = client.post(
        '/auth/register',
        data={'username': 'env_admin', 'email': 'env_admin@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b'administrator privileges' in response.data

    # Verify the user's admin status
    with client.application.app_context():
        user = User.query.filter_by(username='env_admin').first()
        assert user is not None
        assert user.is_admin is True

    # Clean up the environment variable
    del os.environ['INITIAL_ADMIN_USERNAME']

def test_manage_admin_cli_command(app_with_db):
    """
    Tests the 'flask user manage-admin' CLI command for granting and revoking admin rights.
    """
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        # Create a user to test with
        user = User(username='cli_user', email='cli@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        assert user.is_admin is False

    # Test granting admin rights
    result = runner.invoke(args=['user', 'manage-admin', 'cli_user', '--action', 'grant'])
    assert 'Successfully granted' in result.output
    with app_with_db.app_context():
        user = User.query.filter_by(username='cli_user').first()
        assert user.is_admin is True

    # Test revoking admin rights
    result = runner.invoke(args=['user', 'manage-admin', 'cli_user', '--action', 'revoke'])
    assert 'Successfully revoked' in result.output
    with app_with_db.app_context():
        user = User.query.filter_by(username='cli_user').first()
        assert user.is_admin is False

    # Test with a non-existent user
    result = runner.invoke(args=['user', 'manage-admin', 'no_such_user', '--action', 'grant'])
    assert "Error: User 'no_such_user' not found" in result.output
