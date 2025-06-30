# tests/conftest.py

import pytest
import os
import sys

# Add project root to path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, init_db
from models import Food # Or whatever your models are named

@pytest.fixture(scope='module')
def client():
    """
    A fixture for the Flask app tests. It configures the app to use an
    in-memory SQLite database, creates all tables, adds sample data,
    and then yields a test client.
    """
    # --- CRITICAL CONFIGURATION CHANGE ---
    # Force the app to use a temporary, in-memory database for these tests
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    # Initialize the database with the new configuration
    init_db(app)

    # Establish an application context to work with the app
    with app.app_context():
        # Create all database tables in the in-memory database
        db.create_all()

        # Add some consistent, predictable test data for your app tests
        test_food_1 = Food(fdc_id=1, description='Test Apple')
        test_food_2 = Food(fdc_id=2, description='Test Butter')
        db.session.add(test_food_1)
        db.session.add(test_food_2)
        db.session.commit()

        # Yield the test client for the tests to use
        # This 'with' is for the test_client context, not the app_context
        with app.test_client() as client:
            yield client

        # Teardown is automatic for in-memory databases, but dropping is good practice
        db.drop_all()