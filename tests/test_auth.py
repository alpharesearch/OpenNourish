import pytest
from flask import url_for

def test_registration(client):
    """
    Simulates a user submitting the registration form with a new username and valid password.
    It should assert that the response is a redirect (status code 302) to the login page.
    """
    response = client.post(
        '/auth/register',
        data={'username': 'newuser', 'password': 'newpassword', 'password2': 'newpassword'},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']
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
        data={'username': 'testuser', 'password': 'password', 'password2': 'password', 'confirm_password': 'password'},
        follow_redirects=True
    )
    # Then, attempt to register the same user again
    response = client.post(
        '/auth/register',
        data={'username': 'testuser', 'password': 'password', 'password2': 'password'},
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
        data={'username': 'testuser', 'password': 'password', 'password2': 'password', 'confirm_password': 'password'},
        follow_redirects=True
    )

    # Test login
    response = client.post(
        '/auth/login',
        data={'username': 'testuser', 'password': 'password'},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert '/' in response.headers['Location']
    response = client.get(response.headers['Location'], follow_redirects=True)
    assert '/dashboard' in response.request.path

    # Test logout
    response = client.get('/auth/logout', follow_redirects=False)
    assert response.status_code == 302
    assert '/' in response.headers['Location']
    response = client.get(response.headers['Location'], follow_redirects=True)
    assert '/auth/login' in response.request.path
