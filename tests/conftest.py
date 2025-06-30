import pytest
import os
import sys

# Add project root to path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import db

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