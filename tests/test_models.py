# tests/test_models.py

import pytest
from app import app, db
from models import Food # Make sure to import your models

# This fixture sets up a clean, temporary database FOR EACH test function
# scope='function' is safer for DB tests to ensure total isolation.
@pytest.fixture(scope='function')
def setup_database():
    """
    Creates a new database for a test and populates it with a
    single known food item.
    """
    with app.app_context():
        db.create_all()

        # --- THIS IS THE CRUCIAL ADDITION ---
        # Create a test food object and add it to the database
        test_food = Food(fdc_id=1, description='Butter, salted')
        db.session.add(test_food)
        db.session.commit()
        # --- END OF ADDITION ---

        # 'yield' passes control to the test function
        yield db

        # This code runs after the test is finished
        db.session.remove()
        db.drop_all()

# The test function now uses the pre-configured database from the fixture
def test_food_search_returns_result(setup_database):
    """
    GIVEN a database with a known food item
    WHEN the Food model is queried for that item
    THEN the correct item is returned
    """
    # The fixture already provides the app context, so we don't need it here.
    food = Food.query.filter_by(description='Butter, salted').first()

    assert food is not None
    assert food.description == 'Butter, salted'
    assert food.fdc_id == 1

def test_food_search_returns_none_for_missing_item(setup_database):
    """
    GIVEN a database with a known food item
    WHEN the Food model is queried for an item that does not exist
    THEN the result is None
    """
    food = Food.query.filter_by(description='A food that is not in the DB').first()

    assert food is None