import pytest
from models import db, User, FastingSession, UserGoal
from datetime import datetime, timedelta

def test_fasting_index_no_active_fast(auth_client):
    """
    Tests that the fasting index page loads correctly when there is no active fast.
    """
    response = auth_client.get('/fasting/')
    assert response.status_code == 200
    assert b'Start a New Fast' in response.data
    assert b'Active Fast' not in response.data

def test_start_and_end_fast(auth_client):
    """
    Tests that a user can start and end a fast.
    """
    # Start a fast
    response = auth_client.post('/fasting/start', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fasting period started!' in response.data
    assert b'Active Fast' in response.data
    assert b'End Fast Now' in response.data

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None

    # End the fast
    response = auth_client.post('/fasting/end', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fasting period completed!' in response.data
    assert b'Start a New Fast' in response.data

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is None
        completed_fast = FastingSession.query.filter_by(status='completed').first()
        assert completed_fast is not None

def test_edit_fast_start_time(auth_client):
    """
    Tests that a user can edit the start time of an active fast.
    """
    # Start a fast first
    auth_client.post('/fasting/start', follow_redirects=True)

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None
        original_start_time = fast.start_time

    # Edit the start time to be 1 hour earlier
    new_start_time = datetime.utcnow() - timedelta(hours=1)
    response = auth_client.post('/fasting/edit_start_time', data={
        'start_time': new_start_time.strftime('%Y-%m-%dT%H:%M')
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Fast start time updated successfully.' in response.data

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None
        # The start_time from the form will not have seconds, so we compare against a truncated version
        expected_start_time = new_start_time.replace(second=0, microsecond=0)
        assert fast.start_time == expected_start_time

def test_edit_fast_start_time_future_fail(auth_client):
    """
    Tests that a user cannot set the start time of an active fast to a future time.
    """
    auth_client.post('/fasting/start', follow_redirects=True)

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None
        original_start_time = fast.start_time

    # Try to set start time to 1 hour in the future
    future_start_time = datetime.utcnow() + timedelta(hours=1)
    response = auth_client.post('/fasting/edit_start_time', data={
        'start_time': future_start_time.strftime('%Y-%m-%dT%H:%M')
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Start time cannot be in the future.' in response.data

    with auth_client.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None
        # Check that the start time has not changed
        assert abs(fast.start_time - original_start_time).total_seconds() < 5

def test_fasting_lifecycle(auth_client_onboarded):
    """
    Tests the full lifecycle of a fast.
    """
    # 1. No active fast
    response = auth_client_onboarded.get('/fasting/')
    assert b'Start a New Fast' in response.data
    assert b'Active Fast' not in response.data

    # 2. Start a fast
    response = auth_client_onboarded.post('/fasting/start', follow_redirects=True)
    assert response.status_code == 200
    assert b'Active Fast' in response.data
    assert b'End Fast Now' in response.data
    with auth_client_onboarded.application.app_context():
        fast = FastingSession.query.filter_by(status='active').first()
        assert fast is not None
        assert fast.end_time is None

    # 3. End the fast
    response = auth_client_onboarded.post('/fasting/end', follow_redirects=True)
    assert response.status_code == 200
    with auth_client_onboarded.application.app_context():
        fast = FastingSession.query.filter_by(status='completed').first()
        assert fast is not None
        assert fast.end_time is not None

    # 4. Back to no active fast, check history
    response = auth_client_onboarded.get('/fasting/')
    assert b'Start a New Fast' in response.data
    assert b'Active Fast' not in response.data
    assert fast.start_time.strftime('%Y-%m-%d').encode() in response.data



def test_dashboard_displays_fasting_status(auth_client_onboarded):
    """
    Tests that the dashboard correctly reflects the active fast status.
    """
    # No active fast
    response = auth_client_onboarded.get('/dashboard/', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fasting Status' in response.data
    assert b'progress-bar' not in response.data
    assert b'Start a New Fast' in response.data

    # Start a fast
    auth_client_onboarded.post('/fasting/start', follow_redirects=True)

    # Active fast
    response = auth_client_onboarded.get('/dashboard/', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fasting Status' in response.data
    assert b'progress-bar' in response.data
    assert b'Start a New Fast' not in response.data


def test_user_can_set_default_fasting_duration(auth_client_onboarded):
    """
    Tests that a user can set a default fasting duration in their goals.
    """
    with auth_client_onboarded.application.app_context():
        user = User.query.filter_by(username='onboardeduser').first()
        user_id = user.id
        user_goal = UserGoal.query.filter_by(user_id=user_id).first()
        user_goal.default_fasting_hours = 20
        db.session.commit()

    response = auth_client_onboarded.get('/fasting/')
    assert response.status_code == 200
    assert b'value="20"' in response.data

    # Simulate POST request to goals page
    response = auth_client_onboarded.post('/goals/', data={
        'calories': 2000,
        'protein': 150,
        'carbs': 300,
        'fat': 60,
        'default_fasting_hours': 18,
        'submit': 'Save Goals'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Goals updated!' in response.data

    with auth_client_onboarded.application.app_context():
        user_goal = UserGoal.query.filter_by(user_id=user_id).first()
        assert user_goal.default_fasting_hours == 18

    response = auth_client_onboarded.get('/fasting/')
    assert response.status_code == 200
    assert b'value="18"' in response.data
