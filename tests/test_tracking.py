import pytest
from models import db, CheckIn, User
from datetime import date

def test_check_in_crud_lifecycle(auth_client):
    """
    Tests the full CRUD lifecycle for the Check-In feature.
    """
    # 1. Create
    checkin_data = {
        'checkin_date': date.today().strftime('%Y-%m-%d'),
        'weight_kg': 75.5,
        'body_fat_percentage': 15.0,
        'waist_cm': 80.0
    }
    response = auth_client.post('/tracking/check-in/new', data=checkin_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Your check-in has been recorded.' in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        check_in = CheckIn.query.filter_by(user_id=user.id, checkin_date=date.today()).first()
        assert check_in is not None
        assert check_in.weight_kg == 75.5
        assert check_in.body_fat_percentage == 15.0
        assert check_in.waist_cm == 80.0
        created_check_in_id = check_in.id

    # 2. Read
    response = auth_client.get('/tracking/progress')
    assert response.status_code == 200
    assert b'75.5' in response.data # Check if weight is displayed

    # 3. Update
    updated_checkin_data = {
        'checkin_date': date.today().strftime('%Y-%m-%d'),
        'weight_kg': 76.0,
        'body_fat_percentage': 15.5,
        'waist_cm': 81.0
    }
    response = auth_client.post(f'/tracking/check-in/{created_check_in_id}/edit', data=updated_checkin_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Your check-in has been updated.' in response.data

    with auth_client.application.app_context():
        check_in = db.session.get(CheckIn, created_check_in_id)
        assert check_in is not None
        assert check_in.weight_kg == 76.0
        assert check_in.body_fat_percentage == 15.5
        assert check_in.waist_cm == 81.0

    # 4. Delete
    response = auth_client.post(f'/tracking/check-in/{created_check_in_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Your check-in has been deleted.' in response.data

    with auth_client.application.app_context():
        check_in = db.session.get(CheckIn, created_check_in_id)
        assert check_in is None

@pytest.fixture
def two_users(app_with_db):
    with app_with_db.app_context():
        user_one = User(username='user_one')
        user_one.set_password('password')
        db.session.add(user_one)

        user_two = User(username='user_two')
        user_two.set_password('password')
        db.session.add(user_two)
        db.session.commit()
        # Return user IDs instead of user objects
        return user_one.id, user_two.id

@pytest.fixture
def auth_client_user_two(app_with_db, two_users):
    user_one_id, user_two_id = two_users
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user_one_in_context = db.session.get(User, user_one_id)
            user_two_in_context = db.session.get(User, user_two_id)
            user_id = user_two_in_context.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client, user_one_in_context, user_two_in_context

def test_user_cannot_edit_other_users_check_in(auth_client_user_two):
    """
    Tests that a user cannot edit another user's check-in.
    """
    client, user_one_from_fixture, user_two_from_fixture = auth_client_user_two

    with client.application.app_context():
        # Re-fetch user_one within the current app context
        user_one = db.session.get(User, user_one_from_fixture.id)
        # Create a check-in belonging to user_one
        check_in_user_one = CheckIn(user_id=user_one.id, checkin_date=date.today(), weight_kg=70.0)
        db.session.add(check_in_user_one)
        db.session.commit()
        check_in_id = check_in_user_one.id

    # Attempt to make a GET request to the 'edit_check_in' page for user_one's check-in as user_two
    response = client.get(f'/tracking/check-in/{check_in_id}/edit')
    assert response.status_code == 302 # Redirects to /tracking/progress

    # Follow the redirect to check the final status code and flash message
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'Entry not found or you do not have permission to edit it.' in response.data
