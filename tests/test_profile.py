from models import db, User, Friendship


# Helper function to create users
def create_test_user(username, password="password"):
    user = User(username=username, email="testuser_friendship@example.com")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_view_friend_dashboard_authorized(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    friend_user = create_test_user("friend_user")

    # Establish friendship
    friendship = Friendship(
        requester_id=test_user.id, receiver_id=friend_user.id, status="accepted"
    )
    db.session.add(friendship)
    db.session.commit()

    response = test_client.get(f"/user/{friend_user.username}/dashboard")
    assert response.status_code == 200
    assert f"{friend_user.username}" in response.data.decode("utf-8")
    assert b"Nutritional Summary" in response.data


def test_view_friend_dashboard_unauthorized(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    stranger_user = create_test_user("stranger_user")

    response = test_client.get(
        f"/user/{stranger_user.username}/dashboard", follow_redirects=True
    )
    assert response.status_code == 200  # Redirects to friends page
    assert b"You are not friends with" in response.data


def test_view_friend_diary_authorized(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    friend_user = create_test_user("friend_user_diary")

    # Establish friendship
    friendship = Friendship(
        requester_id=test_user.id, receiver_id=friend_user.id, status="accepted"
    )
    db.session.add(friendship)
    db.session.commit()

    response = test_client.get(f"/user/{friend_user.username}/diary")
    assert response.status_code == 200
    assert f"{friend_user.username}" in response.data.decode("utf-8")
    assert b"Food Diary" in response.data


def test_view_friend_diary_unauthorized(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    stranger_user = create_test_user("stranger_user_diary")

    response = test_client.get(
        f"/user/{stranger_user.username}/diary", follow_redirects=True
    )
    assert response.status_code == 200  # Redirects to friends page
    assert b"You are not friends with" in response.data


def test_read_only_mode_dashboard(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    friend_user = create_test_user("read_only_friend")

    # Establish friendship
    friendship = Friendship(
        requester_id=test_user.id, receiver_id=friend_user.id, status="accepted"
    )
    db.session.add(friendship)
    db.session.commit()

    response = test_client.get(f"/user/{friend_user.username}/dashboard")
    assert response.status_code == 200
    # Check for absence of elements that would allow editing/modifying
    # The dashboard.html template does not have any forms or buttons that need to be hidden.
    # This test primarily ensures the page loads correctly in read-only context.
    assert b'<form action="/goals/update"' not in response.data


def test_read_only_mode_diary(auth_client_with_user):
    test_client, test_user = auth_client_with_user
    friend_user = create_test_user("read_only_diary_friend")

    # Establish friendship
    friendship = Friendship(
        requester_id=test_user.id, receiver_id=friend_user.id, status="accepted"
    )
    db.session.add(friendship)
    db.session.commit()

    response = test_client.get(f"/user/{friend_user.username}/diary")
    assert response.status_code == 200
    # Check for absence of elements that would allow editing/modifying
    assert b'<form action="/diary/save_meal"' not in response.data
    assert b'<form action="/diary/update_entry"' not in response.data
    assert b'<form action="/diary/log/\\d+/delete"' not in response.data
    assert b"Add Food" not in response.data
