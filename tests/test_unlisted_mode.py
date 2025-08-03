import pytest
from flask import url_for
from models import db, User, Friendship


# Helper function to create users
def create_test_user(username, password="password", is_verified=True, is_private=False):
    user = User(
        username=username,
        email=f"{username}@example.com",
        is_verified=is_verified,
        is_private=is_private,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def auth_client_public_user(app_with_db):
    with app_with_db.app_context():
        user = create_test_user("public_user", is_private=False)
        # Re-fetch the user within the app_context to ensure it's bound to the session
        user_in_context = db.session.get(User, user.id)
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess["_user_id"] = user_in_context.id
                sess["_fresh"] = True
            yield client, user_in_context


def test_is_private_checkbox_on_settings_page(auth_client_public_user):
    client, user = auth_client_public_user
    response = client.get(url_for("settings.settings"))
    assert response.status_code == 200
    assert b'name="is_private"' in response.data
    assert (
        b"When enabled, other users will not be able to find you in searches or send you new friend requests. This will not affect your existing friendships."
        in response.data
    )


def test_save_is_private_setting(auth_client_public_user):
    client, user = auth_client_public_user

    # Initially, user is public
    with client.application.app_context():
        user_in_context = db.session.get(User, user.id)
        assert user_in_context.is_private is False

    response = client.post(
        url_for("settings.settings"),
        data={
            "email": user.email,
            "measurement_system": user.measurement_system,
            "meals_per_day": user.meals_per_day,
            "theme_preference": user.theme_preference,
            "navbar_preference": user.navbar_preference,
            "is_private": "y",  # Checkbox checked
            "submit_settings": "Save Settings",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Your settings have been updated." in response.data

    with client.application.app_context():
        user_in_context = db.session.get(User, user.id)
        assert user_in_context.is_private is True

    # Disable unlisted mode
    response = client.post(
        url_for("settings.settings"),
        data={
            "email": user.email,
            "measurement_system": user.measurement_system,
            "meals_per_day": user.meals_per_day,
            "theme_preference": user.theme_preference,
            "navbar_preference": user.navbar_preference,
            "is_private": "",  # Checkbox unchecked
            "submit_settings": "Save Settings",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Your settings have been updated." in response.data

    with client.application.app_context():
        user_in_context = db.session.get(User, user.id)
        assert user_in_context.is_private is False


def test_cannot_send_friend_request_to_private_user(auth_client_public_user):
    client, requester_user = auth_client_public_user

    # Create a private user
    # Create a private user
    with client.application.app_context():
        private_user = create_test_user("hidden_user", is_private=True)
        requester_user_in_context = db.session.get(User, requester_user.id)
        private_user_in_context = db.session.get(User, private_user.id)

    # Attempt to send friend request to the private user
    response = client.post(
        url_for("friends.add_friend"),
        data={"username": "hidden_user"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"User not found." in response.data  # Should behave as if user not found

    with client.application.app_context():
        # Verify no friendship was created
        friendship = Friendship.query.filter_by(
            requester_id=requester_user_in_context.id,
            receiver_id=private_user_in_context.id,
        ).first()
        assert friendship is None


def test_can_send_friend_request_to_public_user(auth_client_public_user):
    client, requester_user = auth_client_public_user

    # Create a public user
    with client.application.app_context():
        public_user = create_test_user("visible_user", is_private=False)
        requester_user_in_context = db.session.get(User, requester_user.id)
        public_user_in_context = db.session.get(User, public_user.id)

    # Attempt to send friend request to the public user
    response = client.post(
        url_for("friends.add_friend"),
        data={"username": "visible_user"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Friend request sent to visible_user." in response.data

    with client.application.app_context():
        # Verify friendship was created
        friendship = Friendship.query.filter_by(
            requester_id=requester_user_in_context.id,
            receiver_id=public_user_in_context.id,
        ).first()
        assert friendship is not None
        assert friendship.status == "pending"


def test_existing_friendship_unaffected_by_private_mode(app_with_db):
    with app_with_db.app_context():
        user1 = create_test_user("user1_friend", is_private=False)
        user2 = create_test_user("user2_friend", is_private=False)

        # Establish initial friendship
        friendship = Friendship(
            requester_id=user1.id, receiver_id=user2.id, status="accepted"
        )
        db.session.add(friendship)
        db.session.commit()

        # User1 goes private
        user1.is_private = True
        db.session.commit()

        # Verify friendship still exists
        existing_friendship = Friendship.query.filter_by(
            requester_id=user1.id, receiver_id=user2.id, status="accepted"
        ).first()
        assert existing_friendship is not None

        # Verify user2 can still see user1 as a friend (requires fetching user1's friends)
        db.session.refresh(user2)
        assert user1 in user2.friends
        assert user2 in user1.friends  # Friendship is bidirectional in the model
