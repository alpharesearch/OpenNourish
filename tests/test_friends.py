import pytest
from models import db, User, Friendship, SystemSetting
from flask_login import login_user, logout_user
from flask import url_for

# Helper function to create users
def create_test_user(username, password='password', is_verified=True):
    user = User(username=username, email=f'{username}@example.com', is_verified=is_verified)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

@pytest.fixture
def enable_email_verification_for_friends(app_with_db):
    with app_with_db.app_context():
        setting = SystemSetting.query.filter_by(key='ENABLE_EMAIL_VERIFICATION').first()
        if not setting:
            setting = SystemSetting(key='ENABLE_EMAIL_VERIFICATION', value='True')
            db.session.add(setting)
        else:
            setting.value = 'True'
        db.session.commit()
        app_with_db.config['ENABLE_EMAIL_VERIFICATION'] = True

def test_send_friend_request(auth_client_with_user):
    """Test sending a friend request to another user."""
    test_client, test_user = auth_client_with_user
    # The user that the logged-in user will send a request to
    user2 = create_test_user('friend', is_verified=True)

    # test_client is already logged in as test_user
    response = test_client.post('/friends/add', data={'username': 'friend'}, follow_redirects=False)
    assert response.status_code == 302
    with test_client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'success'
        assert flashes[0][1] == 'Friend request sent to friend.'

    friendship = Friendship.query.filter_by(requester_id=test_user.id, receiver_id=user2.id).first()
    assert friendship is not None
    assert friendship.status == 'pending'

@pytest.mark.usefixtures('enable_email_verification_for_friends')
def test_send_friend_request_unverified_user(client):
    """Test that an unverified user cannot send friend requests when feature is enabled."""
    # Create an unverified user and log them in
    unverified_user = create_test_user('unverified_sender', is_verified=False)
    with client.session_transaction() as sess:
        sess['_user_id'] = unverified_user.id
        sess['_fresh'] = True

    # Create a recipient user
    recipient_user = create_test_user('recipient')

    with client.application.test_request_context():
        response = client.post(url_for('friends.add_friend'), data={'username': 'recipient'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Please verify your email address to send friend requests.' in response.data

    # Verify no friendship was created
    friendship = Friendship.query.filter_by(requester_id=unverified_user.id, receiver_id=recipient_user.id).first()
    assert friendship is None

@pytest.mark.usefixtures('enable_email_verification_for_friends')
def test_send_friend_request_verified_user(client):
    """Test that a verified user can send friend requests when feature is enabled."""
    # Create a verified user and log them in
    verified_user = create_test_user('verified_sender', is_verified=True)
    with client.session_transaction() as sess:
        sess['_user_id'] = verified_user.id
        sess['_fresh'] = True

    # Create a recipient user
    recipient_user = create_test_user('recipient_verified')

    with client.application.test_request_context():
        response = client.post(url_for('friends.add_friend'), data={'username': 'recipient_verified'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Friend request sent to recipient_verified.' in response.data

    # Verify friendship was created
    friendship = Friendship.query.filter_by(requester_id=verified_user.id, receiver_id=recipient_user.id).first()
    assert friendship is not None
    assert friendship.status == 'pending'

def test_accept_friend_request(auth_client_with_user):
    """Test accepting a friend request."""
    test_client, test_user = auth_client_with_user
    # The user who sent the request
    user2 = create_test_user('requester')

    # Manually create a friend request for the current user (test_user) to accept
    friend_request = Friendship(requester_id=user2.id, receiver_id=test_user.id, status='pending')
    db.session.add(friend_request)
    db.session.commit()

    # test_client (as test_user) accepts the request
    response = test_client.post(f'/friends/request/{friend_request.id}/accept', follow_redirects=True)
    assert response.status_code == 200
    assert b'Friend request accepted.' in response.data

    friendship = db.session.get(Friendship, friend_request.id)
    assert friendship.status == 'accepted'

def test_decline_friend_request(auth_client_with_user):
    """Test declining a friend request."""
    test_client, test_user = auth_client_with_user
    # The user who sent the request
    user2 = create_test_user('requester')

    # Manually create a friend request for the current user (test_user) to decline
    friend_request = Friendship(requester_id=user2.id, receiver_id=test_user.id, status='pending')
    db.session.add(friend_request)
    db.session.commit()

    # test_client (as test_user) declines the request
    response = test_client.post(f'/friends/request/{friend_request.id}/decline', follow_redirects=True)
    assert response.status_code == 200
    assert b'Friend request declined.' in response.data

    friendship = db.session.get(Friendship, friend_request.id)
    assert friendship is None

def test_remove_friend(auth_client_with_user):
    """Test removing a friend."""
    test_client, test_user = auth_client_with_user
    # The user who is already a friend
    user2 = create_test_user('friend_to_remove')

    # Manually create an accepted friendship
    friendship = Friendship(requester_id=test_user.id, receiver_id=user2.id, status='accepted')
    db.session.add(friendship)
    db.session.commit()

    # test_client (as test_user) removes the friend
    response = test_client.post(f'/friends/friendship/{user2.id}/remove', follow_redirects=True)
    assert response.status_code == 200
    assert b'Friend removed.' in response.data

    # Check that the friendship is deleted
    friendship = Friendship.query.filter_by(requester_id=test_user.id, receiver_id=user2.id).first()
    assert friendship is None
