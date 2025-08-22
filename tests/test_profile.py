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
    assert b'<form action="/diary/log/\d+/delete"' not in response.data
    assert b"Add Food" not in response.data


def test_copy_log_from_friend(auth_client_with_user):
    """
    Tests copying a diary entry from a friend's diary.
    """
    from datetime import date, timedelta
    from models import DailyLog

    test_client, test_user = auth_client_with_user
    friend_user = create_test_user("friend_for_copy")

    # Establish friendship
    friendship = Friendship(
        requester_id=test_user.id, receiver_id=friend_user.id, status="accepted"
    )
    db.session.add(friendship)

    # Log an entry for the friend
    friend_log = DailyLog(
        user_id=friend_user.id,
        log_date=date.today(),
        meal_name="Breakfast",
        amount_grams=100,
        fdc_id=10001,  # Dummy FDC ID
    )
    db.session.add(friend_log)
    db.session.commit()
    friend_log_id = friend_log.id

    target_date = date.today() + timedelta(days=1)
    target_meal = "Lunch"

    response = test_client.post(
        f"/user/{friend_user.username}/copy_log",
        data={
            "log_id": friend_log_id,
            "target_date": target_date.strftime("%Y-%m-%d"),
            "target_meal_name": target_meal,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Successfully copied item from friend_for_copy&#39;s diary." in response.data
    )

    # Verify the new log was created for the current user
    copied_log = DailyLog.query.filter_by(
        user_id=test_user.id, log_date=target_date, meal_name=target_meal
    ).first()
    assert copied_log is not None
    assert copied_log.amount_grams == 100
    assert copied_log.fdc_id == 10001

    # Verify the friend's original log still exists
    original_log = db.session.get(DailyLog, friend_log_id)
    assert original_log is not None
    assert original_log.user_id == friend_user.id


def test_copy_log_from_non_friend(auth_client_with_user):
    """
    Tests that a user cannot copy a diary entry from someone they are not friends with.
    """
    from datetime import date
    from models import DailyLog

    test_client, test_user = auth_client_with_user
    stranger_user = create_test_user("stranger_for_copy")

    # Log an entry for the stranger
    stranger_log = DailyLog(
        user_id=stranger_user.id,
        log_date=date.today(),
        meal_name="Breakfast",
        amount_grams=100,
        fdc_id=10001,
    )
    db.session.add(stranger_log)
    db.session.commit()
    stranger_log_id = stranger_log.id

    response = test_client.post(
        f"/user/{stranger_user.username}/copy_log",
        data={
            "log_id": stranger_log_id,
            "target_date": date.today().strftime("%Y-%m-%d"),
            "target_meal_name": "Lunch",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"You are not friends with stranger_for_copy." in response.data

    # Verify no log was created for the current user
    copied_log = DailyLog.query.filter_by(user_id=test_user.id).all()
    assert len(copied_log) == 0
