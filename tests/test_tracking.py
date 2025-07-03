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
    response = auth_client.get(f'/tracking/check-in/{created_check_in_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Your check-in has been deleted.' in response.data

    with auth_client.application.app_context():
        check_in = db.session.get(CheckIn, created_check_in_id)
        assert check_in is None
