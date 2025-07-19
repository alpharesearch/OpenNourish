import pytest
from flask import url_for

def test_registration(client):
    """
    Simulates a user submitting the registration form with a new username and valid password.
    It should assert that the response is a redirect (status code 302) to the login page.
    """
    response = client.post(
        '/auth/register',
        data={'username': 'newuser', 'email': 'newuser@example.com', 'password': 'newpassword', 'password2': 'newpassword'},
        follow_redirects=False
    )
    assert response.status_code == 302
    # After registration, the user could be redirected to goals, dashboard, or onboarding
    assert any(s in response.headers['Location'] for s in ['/goals', '/dashboard', '/onboarding'])
    response = client.get(response.headers['Location'], follow_redirects=True)
    assert b'Congratulations, you are now a registered user!' in response.data

def test_duplicate_registration(client):
    """
    Attempts to register with a username that already exists ('testuser' from the 'auth_client' fixture).
    It should assert that the response contains the validation error 'Please use a different username.'.
    """
    # First, register a user
    client.post(
        '/auth/register',
        data={'username': 'testuser', 'email': 'testuser@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    # Log out the user to test registration by an unauthenticated user
    client.get('/auth/logout')
    # Then, attempt to register the same user again
    response = client.post(
        '/auth/register',
        data={'username': 'testuser', 'email': 'testuser2@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=False
    )
    assert response.status_code == 200
    assert b'Please use a different username.' in response.data

def test_login_logout(client):
    """
    First, it logs in by POSTing valid credentials ('testuser', 'password') to the '/auth/login' route.
    It should assert a redirect to the dashboard. Then, it should make a GET request to '/auth/logout'
    and assert that this also results in a redirect.
    """
    # Register a user for login
    client.post(
        '/auth/register',
        data={'username': 'testuser', 'email': 'testuser@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    # Log out to test the login flow separately
    client.get('/auth/logout')

    # Test login
    response = client.post(
        '/auth/login',
        data={'username_or_email': 'testuser', 'password': 'password'},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert '/' in response.headers['Location']
    response = client.get(response.headers['Location'], follow_redirects=True)
    # After login, user might be sent to dashboard or onboarding
    assert any(s in response.request.path for s in ['/dashboard', '/onboarding'])

    # Test logout
    response = client.get('/auth/logout', follow_redirects=False)
    assert response.status_code == 302
    assert '/' in response.headers['Location']
    response = client.get(response.headers['Location'], follow_redirects=True)
    assert '/auth/login' in response.request.path

def test_auto_login_after_registration(client):
    """
    Tests that a user is automatically logged in after successful registration.
    It should assert that after registration, the user is redirected and the subsequent
    page does not contain a link to the login page, indicating an authenticated session.
    """
    response = client.post(
        '/auth/register',
        data={'username': 'autologinuser', 'email': 'autologinuser@example.com', 'password': 'password', 'password2': 'password'},
        follow_redirects=True
    )
    assert response.status_code == 200
    # Check that the user is logged in by ensuring the login link is not present
    assert b'href="/auth/login"' not in response.data
    # Check for a logout link, which should be present for a logged-in user
    assert b'href="/auth/logout"' in response.data
