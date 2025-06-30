# tests/test_models.py

import pytest
from app import app, db, init_db
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

def test_food_upc_storage(setup_database):
    """
    GIVEN a database
    WHEN a Food item with a UPC is added
    THEN the UPC is correctly stored and retrieved
    """
    with app.app_context():
        new_food = Food(fdc_id=3, description='Test Food with UPC', upc='123456789012')
        db.session.add(new_food)
        db.session.commit()

        retrieved_food = Food.query.filter_by(upc='123456789012').first()
        assert retrieved_food is not None
        assert retrieved_food.description == 'Test Food with UPC'
        assert retrieved_food.upc == '123456789012'

def test_food_upc_uniqueness(setup_database):
    """
    GIVEN a database with a food item that has a UPC
    WHEN attempting to add another food item with the same UPC
    THEN an IntegrityError is raised
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        # Add the first food with a UPC
        food1 = Food(fdc_id=4, description='Food One', upc='987654321098')
        db.session.add(food1)
        db.session.commit()

        # Attempt to add a second food with the same UPC
        food2 = Food(fdc_id=5, description='Food Two', upc='987654321098')
        db.session.add(food2)

        # Expect an IntegrityError
        with pytest.raises(IntegrityError):
            db.session.commit()
        
        # Rollback the session to clean up the failed transaction
        db.session.rollback()

def test_food_search_returns_none_for_missing_item(setup_database):
    """
    GIVEN a database with a known food item
    WHEN the Food model is queried for an item that does not exist
    THEN the result is None
    """
    food = Food.query.filter_by(description='A food that is not in the DB').first()

    assert food is None