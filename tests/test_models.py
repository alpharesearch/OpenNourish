import pytest
from app import app
from models import db, Food

@pytest.fixture(scope='module')
def setup_database():
    with app.app_context():
        db.create_all()
        # Assuming import_usda_data.py has been run to populate the database
        # For testing, you might want to insert a known food item here
        # For now, we'll rely on the pre-populated database
        yield db
        db.session.remove()
        db.drop_all()

def test_food_search_returns_result(setup_database):
    with app.app_context():
        food = Food.query.filter_by(description='Butter, salted').first()
        assert food is not None
        assert food.description == 'Butter, salted'
