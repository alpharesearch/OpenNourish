import pytest
from models import db, Food, Nutrient, FoodNutrient, User, SystemSetting
from opennourish import utils

# --- Unit Conversion Tests ---

@pytest.mark.parametrize("cm, expected_ft, expected_in", [
    (180, 5, 10.9),
    (165, 5, 5.0),
    (0, 0, 0),
    (None, None, None)
])
def test_cm_to_ft_in(cm, expected_ft, expected_in):
    ft, inches = utils.cm_to_ft_in(cm)
    assert ft == expected_ft
    assert inches == expected_in

@pytest.mark.parametrize("ft, inches, expected_cm", [
    (5, 11, 180.34),
    (5, 5, 165.1),
    (0, 0, 0),
    (None, 5, None),
    (5, None, None)
])
def test_ft_in_to_cm(ft, inches, expected_cm):
    cm = utils.ft_in_to_cm(ft, inches)
    if cm is not None:
        assert round(cm, 2) == expected_cm
    else:
        assert cm is None

# --- BMR Calculation Tests ---

def test_calculate_bmr_katch_mcardle():
    # weight_kg, height_cm, age, gender, body_fat_percentage
    bmr, formula = utils.calculate_bmr(80, 180, 30, 'Male', 15)
    assert formula == "Katch-McArdle"
    assert round(bmr) == 1839

def test_calculate_bmr_mifflin_st_jeor_male():
    bmr, formula = utils.calculate_bmr(80, 180, 30, 'Male')
    assert formula == "Mifflin-St Jeor"
    assert round(bmr) == 1780

def test_calculate_bmr_mifflin_st_jeor_female():
    bmr, formula = utils.calculate_bmr(65, 165, 30, 'Female')
    assert formula == "Mifflin-St Jeor"
    assert round(bmr) == 1370

# --- Registration Status Test ---

def test_get_allow_registration_status(app_with_db):
    with app_with_db.app_context():
        # Test default (True)
        assert utils.get_allow_registration_status() is True

        # Test when setting is 'false'
        setting = SystemSetting(key='allow_registration', value='false')
        db.session.add(setting)
        db.session.commit()
        assert utils.get_allow_registration_status() is False

        # Test when setting is 'true'
        setting.value = 'true'
        db.session.commit()
        assert utils.get_allow_registration_status() is True

@pytest.fixture
def client_with_usda_food(client):
    with client.application.app_context():
        # Create a dummy user for login_required routes
        user = User(username='testuser_utils', email='testuser@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

        # Log in the user
        client.post('/auth/login', data={'username': 'testuser_utils', 'password': 'password'})

        # Create a sample USDA Food item
        usda_food = Food(fdc_id=167588, description='Sample Food for Label Test')
        db.session.add(usda_food)

        # Create necessary nutrients and food_nutrients for the label
        nutrients_to_add = [
            (1008, 'Energy', 'kcal', 100.0),
            (1004, 'Total lipid (fat)', 'g', 5.0),
            (1258, 'Fatty acids, total saturated', 'g', 2.0),
            (1257, 'Fatty acids, total trans', 'g', 0.1),
            (1253, 'Cholesterol', 'mg', 10.0),
            (1093, 'Sodium, Na', 'mg', 200.0),
            (1005, 'Carbohydrate, by difference', 'g', 15.0),
            (1079, 'Fiber, total dietary', 'g', 3.0),
            (2000, 'Total Sugars', 'g', 10.0),
            (1235, 'Sugars, added', 'g', 5.0),
            (1003, 'Protein', 'g', 8.0),
            (1110, 'Vitamin D (D2 + D3)', 'mcg', 2.0),
            (1087, 'Calcium, Ca', 'mg', 260.0),
            (1089, 'Iron, Fe', 'mg', 8.0),
            (1092, 'Potassium, K', 'mg', 240.0),
        ]

        for nutrient_id, name, unit, amount in nutrients_to_add:
            nutrient = Nutrient(id=nutrient_id, name=name, unit_name=unit)
            db.session.add(nutrient)
            food_nutrient = FoodNutrient(fdc_id=usda_food.fdc_id, nutrient_id=nutrient_id, amount=amount)
            db.session.add(food_nutrient)
        
        db.session.commit()
    return client

def test_generate_nutrition_label_pdf(client_with_usda_food):
    client = client_with_usda_food
    fdc_id = 167588
    response = client.get(f'/generate_nutrition_label/{fdc_id}')
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'

def test_generate_nutrition_label_svg(client_with_usda_food):
    client = client_with_usda_food
    fdc_id = 167588
    response = client.get(f'/nutrition_label_svg/{fdc_id}')
    assert response.status_code == 200
    assert response.mimetype == 'image/svg+xml'
