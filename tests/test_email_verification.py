import pytest
from flask import url_for, current_app
from flask_login import current_user
from models import db, User, SystemSetting
from opennourish.utils import mail

@pytest.fixture
def enable_email_verification(app_with_db):
    with app_with_db.app_context():
        setting = SystemSetting.query.filter_by(key='ENABLE_EMAIL_VERIFICATION').first()
        if not setting:
            setting = SystemSetting(key='ENABLE_EMAIL_VERIFICATION', value='True')
            db.session.add(setting)
        else:
            setting.value = 'True'
        db.session.commit()
        # Reload app config to reflect the change immediately in tests
        app_with_db.config['ENABLE_EMAIL_VERIFICATION'] = True

@pytest.fixture
def disable_email_verification(app_with_db):
    with app_with_db.app_context():
        setting = SystemSetting.query.filter_by(key='ENABLE_EMAIL_VERIFICATION').first()
        if not setting:
            setting = SystemSetting(key='ENABLE_EMAIL_VERIFICATION', value='False')
            db.session.add(setting)
        else:
            setting.value = 'False'
        db.session.commit()
        # Reload app config to reflect the change immediately in tests
        app_with_db.config['ENABLE_EMAIL_VERIFICATION'] = False

@pytest.fixture
def verified_user_client(app_with_db):
    with app_with_db.app_context():
        user = User(username='verified', email='verified@example.com', is_verified=True, has_completed_onboarding=True)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = user.id
                sess['_fresh'] = True
            yield client, user

@pytest.fixture
def unverified_user_client(app_with_db):
    with app_with_db.app_context():
        user = User(username='unverified', email='unverified@example.com', is_verified=False)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = user.id
                sess['_fresh'] = True
            yield client, user

# --- Part 1: Refactored Token Methods Tests ---

def test_get_token_and_verify_token_password_reset(app_with_db):
    with app_with_db.app_context():
        user = User(username='testuser', email='test@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

        token = user.get_token(purpose='reset-password')
        assert token is not None

        verified_user = User.verify_token(token, purpose='reset-password')
        assert verified_user == user

def test_get_token_and_verify_token_email_verification(app_with_db):
    with app_with_db.app_context():
        user = User(username='testuser2', email='test2@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

        token = user.get_token(purpose='verify-email')
        assert token is not None

        verified_user = User.verify_token(token, purpose='verify-email')
        assert verified_user == user

def test_verify_token_invalid_purpose(app_with_db):
    with app_with_db.app_context():
        user = User(username='testuser3', email='test3@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

        token = user.get_token(purpose='reset-password')
        assert token is not None

        # Try to verify with wrong purpose
        verified_user = User.verify_token(token, purpose='verify-email')
        assert verified_user is None

# --- Part 2: Email Verification Logic & Routes Tests ---

@pytest.mark.usefixtures('enable_email_verification')
def test_send_verification_email_success(unverified_user_client, mocker):
    client, user = unverified_user_client
    mocker.patch('opennourish.utils.mail.send_message', return_value=None)

    response = client.post(url_for('auth.send_verification_email_route'), follow_redirects=True)
    assert response.status_code == 200
    assert b'A new verification email has been sent to your email address.' in response.data
    mail.send_message.assert_called_once()

@pytest.mark.usefixtures('enable_email_verification')
def test_send_verification_email_already_verified(verified_user_client, mocker):
    client, user = verified_user_client
    mocker.patch('opennourish.utils.mail.send_message', return_value=None)

    response = client.post(url_for('auth.send_verification_email_route'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Your email is already verified.' in response.data
    mail.send_message.assert_not_called()

@pytest.mark.usefixtures('disable_email_verification')
def test_send_verification_email_feature_disabled(unverified_user_client, mocker):
    client, user = unverified_user_client
    mocker.patch('opennourish.utils.mail.send_message', return_value=None)

    response = client.post(url_for('auth.send_verification_email_route'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Email verification is not enabled.' in response.data
    mail.send_message.assert_not_called()

def test_send_verification_email_not_logged_in(client, mocker):
    mocker.patch('opennourish.utils.mail.send_message', return_value=None)

    response = client.post(url_for('auth.send_verification_email_route'), follow_redirects=True)
    assert response.status_code == 200
    assert b'Please log in to send a verification email.' in response.data
    mail.send_message.assert_not_called()

@pytest.mark.usefixtures('enable_email_verification')
def test_verify_email_valid_token(app_with_db, client):
    with app_with_db.app_context():
        user = User(username='verify_me', email='verify@example.com', is_verified=False)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        token = user.get_token(purpose='verify-email')

    with app_with_db.test_request_context():
        response = client.get(url_for('auth.verify_email', token=token), follow_redirects=True)
    assert response.status_code == 200
    assert b'Your email address has been verified!' in response.data
    with app_with_db.app_context():
        updated_user = db.session.get(User, user.id)
        assert updated_user.is_verified
    # User should be logged in after verification
    with app_with_db.test_request_context():
        assert current_user.is_authenticated
        assert current_user.id == user.id

@pytest.mark.usefixtures('enable_email_verification')
def test_verify_email_invalid_token(app_with_db, client):
    with app_with_db.test_request_context():
        response = client.get(url_for('auth.verify_email', token='invalid-token'), follow_redirects=True)
    assert response.status_code == 200
    assert b'That is an invalid or expired verification link.' in response.data
    with client.session_transaction() as sess:
        assert '_user_id' not in sess # Should not log in

@pytest.mark.usefixtures('enable_email_verification')
def test_verify_email_expired_token(app_with_db, client):
    with app_with_db.app_context():
        user = User(username='expired_token_user', email='expired@example.com', is_verified=False)
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        # Create an expired token (e.g., expires in -1 seconds)
        expired_token = user.get_token(purpose='verify-email', expires_in=-1)

    response = client.get(url_for('auth.verify_email', token=expired_token), follow_redirects=True)
    assert response.status_code == 200
    assert b'That is an invalid or expired verification link.' in response.data
    with app_with_db.app_context():
        updated_user = db.session.get(User, user.id)
        assert not updated_user.is_verified
    with client.session_transaction() as sess:
        assert '_user_id' not in sess

@pytest.mark.usefixtures('enable_email_verification')
def test_verify_email_already_verified_user(app_with_db, verified_user_client, client):
    client, user = verified_user_client
    # User is already verified by fixture
    token = user.get_token(purpose='verify-email') # Generate a new token for the already verified user

    response = client.get(url_for('auth.verify_email', token=token), follow_redirects=False)
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get('_flashes', [])
        assert len(flashes) > 0
        assert flashes[0][0] == 'info' # Category
        assert flashes[0][1] == 'Your email is already verified.' # Message
    # Optionally, follow the redirect to ensure the page loads
    response = client.get(response.headers['Location'])
    assert response.status_code == 200
    assert b'Dashboard' in response.data
    with app_with_db.app_context():
        updated_user = db.session.get(User, user.id)
        assert updated_user.is_verified # Should remain verified
    with client.session_transaction() as sess:
        assert '_user_id' in sess
