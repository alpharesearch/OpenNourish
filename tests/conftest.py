import pytest
import os
import sys
import tempfile
import shutil

# Add project root to path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from opennourish import create_app
from models import db, User
from config import Config

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
        'ALLOW_REGISTRATION': True,
        'SERVER_NAME': 'localhost.localdomain:5000' # Required for url_for(_external=True) in tests
    }

    # --- SAFEGUARD ---
    # Ensure that we are not running against a file-based database
    if 'memory' not in test_config['SQLALCHEMY_DATABASE_URI']:
        pytest.fail("Aborting test: SQLALCHEMY_DATABASE_URI is not set to in-memory.")
    if 'memory' not in test_config['SQLALCHEMY_BINDS']['usda']:
        pytest.fail("Aborting test: SQLALCHEMY_BINDS['usda'] is not set to in-memory.")

    app = create_app(test_config)

    # Create a temporary instance folder for each test
    instance_path = tempfile.mkdtemp()
    app.instance_path = instance_path

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    # Clean up the temporary instance folder
    shutil.rmtree(instance_path)

@pytest.fixture(scope='function')
def client(app_with_db):
    """A test client for the app."""
    return app_with_db.test_client()

@pytest.fixture(scope='function')
def auth_client(app_with_db):
    """A test client that is authenticated."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='testuser', email='testuser@example.com')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client

@pytest.fixture(scope='function')
def admin_client(app_with_db):
    """A test client that is authenticated as an admin user."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='adminuser', email='adminuser@example.com', is_admin=True)
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        yield client, user, app_with_db

@pytest.fixture(scope='function')
def auth_client_with_user(app_with_db):
    """A test client that is authenticated, and provides the user object."""
    with app_with_db.test_client() as client:
        with app_with_db.app_context():
            user = User(username='testuser2', email='testuser2@example.com')
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_user_id'] = user_id
            sess['_fresh'] = True
        return client, user

@pytest.fixture
def auth_client_two_users(app_with_db):
    """Fixture for providing two authenticated users."""
    with app_with_db.app_context():
        user_one = User(username='user_one', email='userone@example.com')
        user_one.set_password('password_one')
        db.session.add(user_one)

        user_two = User(username='user_two', email='usertwo@example.com')
        user_two.set_password('password_two')
        db.session.add(user_two)
        db.session.commit()

        # It's often better to return the objects themselves
        # and let the test function handle logging in.
        # However, to keep it simple, we'll log in as user_one by default.
        with app_with_db.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = user_one.id
                sess['_fresh'] = True
            yield client, user_one, user_two

@pytest.fixture(scope='function')
def auth_client_with_friendship(app_with_db):
    """A test client authenticated as test_user, with an accepted friendship to friend_user."""
    with app_with_db.app_context():
        test_user = User(username='testuser_friendship', email='testuser_friendship@example.com')
        test_user.set_password('password')
        db.session.add(test_user)

        friend_user = User(username='frienduser_friendship', email='frienduser_friendship@example.com')
        friend_user.set_password('password')
        db.session.add(friend_user)
        db.session.commit()

        # Establish accepted friendship
        from models import Friendship # Import here to avoid circular dependency
        friendship = Friendship(requester_id=test_user.id, receiver_id=friend_user.id, status='accepted')
        db.session.add(friendship)
        db.session.commit()

        # Re-fetch users to ensure relationships are loaded
        db.session.refresh(test_user)
        db.session.refresh(friend_user)

    with app_with_db.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = test_user.id
            sess['_fresh'] = True
        yield client, test_user, friend_user
