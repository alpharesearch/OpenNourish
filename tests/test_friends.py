import pytest
from models import db, User, Friendship
from flask_login import login_user, logout_user

# Helper function to create users
def create_test_user(username, password='password'):
    user = User(username=username, email='testuser_friendship@example.com')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def test_send_friend_request(auth_client_with_user):
    """Test sending a friend request to another user."""
    test_client, test_user = auth_client_with_user
    # The user that the logged-in user will send a request to
    user2 = create_test_user('friend')

    # test_client is already logged in as test_user
    response = test_client.post('/friends/add', data={'username': 'friend'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Friend request sent to friend.' in response.data

    friendship = Friendship.query.filter_by(requester_id=test_user.id, receiver_id=user2.id).first()
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
