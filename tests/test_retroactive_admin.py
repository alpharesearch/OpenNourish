import pytest
from models import User, db


@pytest.fixture()
def set_admin_env(monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    yield
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)


@pytest.mark.usefixtures("set_admin_env")
def test_register_admin_user(client):
    """Test that a user is registered as an admin if their username matches INITIAL_ADMIN_USERNAME."""
    # Register the admin user
    client.post(
        "/auth/register",
        data={
            "username": "admin",
            "email": "admin@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=True,
    )
    # Verify that the user is an admin
    admin_user = User.query.filter_by(username="admin").first()
    assert admin_user is not None
    assert admin_user.is_admin


@pytest.mark.usefixtures("set_admin_env")
def test_retroactive_admin_grant_on_login(client):
    """Test that a non-admin user is granted admin rights on login if their username matches INITIAL_ADMIN_USERNAME."""
    # First, register a regular user who is not the admin
    client.post(
        "/auth/register",
        data={
            "username": "regularuser",
            "email": "regularuser@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=True,
    )
    # Log out the user to simulate a new session
    client.get("/auth/logout")

    # Manually set the user's username to match the admin env var and ensure they are not an admin
    user = User.query.filter_by(username="regularuser").first()
    user.is_admin = False
    user.username = (
        "admin"  # Change username to match the one that gets retroactive admin
    )
    db.session.commit()

    # Log in as the user who should be granted admin rights
    client.post(
        "/auth/login",
        data={"username_or_email": "admin", "password": "password"},
        follow_redirects=True,
    )

    # Verify that the user is now an admin
    updated_user = User.query.filter_by(email="regularuser@example.com").first()
    assert updated_user is not None
    assert updated_user.is_admin


def test_first_user_is_admin_when_env_var_is_not_set(client, monkeypatch):
    """Test that the first registered user becomes an admin if INITIAL_ADMIN_USERNAME is not set."""
    # Ensure the environment variable is not set for this test
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)

    # Register the first user
    client.post(
        "/auth/register",
        data={
            "username": "firstuser",
            "email": "first@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=True,
    )
    # Verify the first user is an admin
    first_user = User.query.filter_by(username="firstuser").first()
    assert first_user is not None
    assert first_user.is_admin

    # Log out to ensure session is clean for next registration
    client.get("/auth/logout")

    # Register the second user
    client.post(
        "/auth/register",
        data={
            "username": "seconduser",
            "email": "second@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=True,
    )
    # Verify the second user is NOT an admin
    second_user = User.query.filter_by(username="seconduser").first()
    assert second_user is not None
    assert not second_user.is_admin
