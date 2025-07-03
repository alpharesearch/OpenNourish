import pytest
import os
import sys

# Add project root to path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from opennourish import create_app
from models import db, User

@pytest.fixture(scope='function')
def app_with_db():
    """
    Creates a new app instance for each test, configured for testing.
    Includes a safeguard to prevent running against a real database.
    """
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_BINDS': {'usda': 'sqlite:///:memory:'},
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'SECRET_KEY': 'test_secret_key',
        'WTF_CSRF_ENABLED': False, # Disable CSRF for testing forms
    }

    # --- SAFEGUARD ---
    # Ensure that we are not running against a file-based database
    if 'memory' not in test_config['SQLALCHEMY_DATABASE_URI']:
        pytest.fail("Aborting test: SQLALCHEMY_DATABASE_URI is not set to in-memory.")
    if 'memory' not in test_config['SQLALCHEMY_BINDS']['usda']:
        pytest.fail("Aborting test: SQLALCHEMY_BINDS['usda'] is not set to in-memory.")

    app = create_app(test_config)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def client(app_with_db):
    """A test client for the app."""
    return app_with_db.test_client()

@pytest.fixture(scope='function')
def auth_client(app_with_db):
    """A test client that is authenticated."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='testuser')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client

@pytest.fixture(scope='function')
def auth_client_with_user(app_with_db):
    """A test client that is authenticated, and provides the user object."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='testuser2')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client, user