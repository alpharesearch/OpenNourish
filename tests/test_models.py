import pytest
from app import app
from models import db, Food, Nutrient, FoodNutrient, MeasureUnit, Portion, User

@pytest.fixture(scope='function')
def app_context_for_models():
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()

def test_food_creation(app_context_for_models):
    food = Food(fdc_id=100, description='Test Food')
    db.session.add(food)
    db.session.commit()
    assert db.session.execute(db.select(Food)).scalar_one() is not None
    assert db.session.execute(db.select(Food)).scalar_one().description == 'Test Food'

def test_nutrient_creation(app_context_for_models):
    nutrient = Nutrient(id=200, name='Test Nutrient', unit_name='g')
    db.session.add(nutrient)
    db.session.commit()
    assert db.session.execute(db.select(Nutrient)).scalar_one() is not None

def test_food_nutrient_association(app_context_for_models):
    food = Food(fdc_id=101, description='Food with Nutrient')
    nutrient = Nutrient(id=201, name='Associated Nutrient', unit_name='mg')
    food_nutrient = FoodNutrient(fdc_id=101, nutrient_id=201, amount=10.5)

    db.session.add_all([food, nutrient, food_nutrient])
    db.session.commit()

    retrieved_food = db.session.get(Food, 101)
    assert len(retrieved_food.nutrients) == 1
    assert retrieved_food.nutrients[0].amount == 10.5

def test_measure_unit_creation(app_context_for_models):
    unit = MeasureUnit(id=300, name='Test Unit')
    db.session.add(unit)
    db.session.commit()
    assert db.session.execute(db.select(MeasureUnit)).scalar_one() is not None

def test_portion_creation(app_context_for_models):
    food = Food(fdc_id=102, description='Food for Portion')
    unit = MeasureUnit(id=301, name='Portion Unit')
    portion = Portion(fdc_id=102, seq_num=1, amount=1.0, measure_unit_id=301, gram_weight=100.0)

    db.session.add_all([food, unit, portion])
    db.session.commit()

    retrieved_portion = db.session.get(Portion, portion.id)
    assert retrieved_portion.gram_weight == 100.0

def test_food_search_returns_result(app_context_for_models):
    food = Food(fdc_id=1, description='Butter, salted')
    db.session.add(food)
    db.session.commit()
    found_food = db.session.execute(db.select(Food).filter_by(description='Butter, salted')).scalar_one()
    assert found_food is not None
    assert found_food.fdc_id == 1

def test_food_search_returns_none_for_missing_item(app_context_for_models):
    found_food = db.session.execute(db.select(Food).filter_by(description='NonExistentFood')).scalar_one_or_none()
    assert found_food is None

def test_food_upc_storage(app_context_for_models):
    food = Food(fdc_id=2, description='Milk, whole', upc='012345678905')
    db.session.add(food)
    db.session.commit()
    found_food = db.session.execute(db.select(Food).filter_by(upc='012345678905')).scalar_one()
    assert found_food is not None
    assert found_food.description == 'Milk, whole'

def test_food_upc_uniqueness(app_context_for_models):
    food1 = Food(fdc_id=3, description='Bread', upc='111222333444')
    food2 = Food(fdc_id=4, description='Roll', upc='111222333444') # Same UPC
    db.session.add(food1)
    db.session.commit()

    with pytest.raises(Exception): # Expect an IntegrityError or similar
        db.session.add(food2)
        db.session.commit()