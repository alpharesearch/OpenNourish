import pytest
from models import db, User, FastingSession, UserGoal
from datetime import datetime, timedelta
import pytz

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
    assert b'Fast Started' not in response.data
    

    # Start a fast
    auth_client_onboarded.post('/fasting/start', follow_redirects=True)

    # Active fast
    response = auth_client_onboarded.get('/dashboard/', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fasting Status' in response.data
    assert b'Fast Started' in response.data
    
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

def test_delete_fast(auth_client):
    """
    Tests deleting a completed fast entry.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(hours=24),
            end_time=datetime.utcnow() - timedelta(hours=8),
            status='completed',
            planned_duration_hours=16
        )
        db.session.add(fast)
        db.session.commit()
        fast_id = fast.id

    response = auth_client.post(f'/fasting/delete_fast/{fast_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fast entry deleted.' in response.data

    with auth_client.application.app_context():
        deleted_fast = db.session.get(FastingSession, fast_id)
        assert deleted_fast is None

def test_update_completed_fast(auth_client):
    """
    Tests updating the start and end times of a completed fast.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.timezone = 'America/New_York'  # Set a non-UTC timezone
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(days=2),
            end_time=datetime.utcnow() - timedelta(days=1),
            status='completed',
            planned_duration_hours=24
        )
        db.session.add(fast)
        db.session.commit()
        fast_id = fast.id

    # New naive times to be submitted, representing America/New_York time
    new_start_time_naive = datetime(2023, 10, 26, 10, 0)
    new_end_time_naive = datetime(2023, 10, 27, 6, 0)

    response = auth_client.post(f'/fasting/update_fast/{fast_id}', data={
        'start_time': new_start_time_naive.strftime('%Y-%m-%dT%H:%M'),
        'end_time': new_end_time_naive.strftime('%Y-%m-%dT%H:%M')
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Fast updated successfully.' in response.data

    with auth_client.application.app_context():
        updated_fast = db.session.get(FastingSession, fast_id)
        
        # Convert naive form times to expected UTC for comparison
        user_tz = pytz.timezone('America/New_York')
        expected_start_utc = user_tz.localize(new_start_time_naive).astimezone(pytz.utc).replace(tzinfo=None)
        expected_end_utc = user_tz.localize(new_end_time_naive).astimezone(pytz.utc).replace(tzinfo=None)

        assert updated_fast.start_time == expected_start_utc
        assert updated_fast.end_time == expected_end_utc