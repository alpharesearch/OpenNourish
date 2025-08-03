import pytest
from models import (
    db,
    Food,
    Nutrient,
    FoodNutrient,
    User,
    SystemSetting,
    MyFood,
    Recipe,
    RecipeIngredient,
    DailyLog,
)
from opennourish import utils
from datetime import date

# --- Unit Conversion Tests ---


@pytest.mark.parametrize(
    "cm, expected_ft, expected_in",
    [(180, 5, 10.9), (165, 5, 5.0), (0, 0, 0), (None, None, None)],
)
def test_cm_to_ft_in(cm, expected_ft, expected_in):
    ft, inches = utils.cm_to_ft_in(cm)
    assert ft == expected_ft
    assert inches == expected_in


@pytest.mark.parametrize(
    "ft, inches, expected_cm",
    [(5, 11, 180.34), (5, 5, 165.1), (0, 0, 0), (None, 5, None), (5, None, None)],
)
def test_ft_in_to_cm(ft, inches, expected_cm):
    cm = utils.ft_in_to_cm(ft, inches)
    if cm is not None:
        assert round(cm, 2) == expected_cm
    else:
        assert cm is None


# --- BMR Calculation Tests ---


def test_calculate_bmr_katch_mcardle():
    # weight_kg, height_cm, age, gender, body_fat_percentage
    bmr, formula = utils.calculate_bmr(80, 180, 30, "Male", 15)
    assert formula == "Katch-McArdle"
    assert round(bmr) == 1839


def test_calculate_bmr_mifflin_st_jeor_male():
    bmr, formula = utils.calculate_bmr(80, 180, 30, "Male")
    assert formula == "Mifflin-St Jeor"
    assert round(bmr) == 1780


def test_calculate_bmr_mifflin_st_jeor_female():
    bmr, formula = utils.calculate_bmr(65, 165, 30, "Female")
    assert formula == "Mifflin-St Jeor"
    assert round(bmr) == 1370


# --- Registration Status Test ---


def test_get_allow_registration_status(app_with_db):
    with app_with_db.app_context():
        # Test default (True)
        assert utils.get_allow_registration_status() is True

        # Test when setting is 'false'
        setting = SystemSetting(key="allow_registration", value="false")
        db.session.add(setting)
        db.session.commit()
        assert utils.get_allow_registration_status() is False

        # Test when setting is 'true'
        setting.value = "true"
        db.session.commit()
        assert utils.get_allow_registration_status() is True


@pytest.fixture
def auth_client_utils(client):
    with client.application.app_context():
        user = User(username="testuser_utils", email="testuser_utils@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True

    yield client, user_id


@pytest.fixture
def client_with_usda_food(auth_client_utils):
    client, _ = auth_client_utils
    with client.application.app_context():
        usda_food = Food(fdc_id=167588, description="Sample Food for Label Test")
        db.session.add(usda_food)

        nutrients_to_add = [
            (1008, "Energy", "kcal", 100.0),
            (1004, "Total lipid (fat)", "g", 5.0),
            (1258, "Fatty acids, total saturated", "g", 2.0),
            (1257, "Fatty acids, total trans", "g", 0.1),
            (1253, "Cholesterol", "mg", 10.0),
            (1093, "Sodium, Na", "mg", 200.0),
            (1005, "Carbohydrate, by difference", "g", 15.0),
            (1079, "Fiber, total dietary", "g", 3.0),
            (2000, "Total Sugars", "g", 10.0),
            (1235, "Sugars, added", "g", 5.0),
            (1003, "Protein", "g", 8.0),
            (1110, "Vitamin D (D2 + D3)", "mcg", 2.0),
            (1087, "Calcium, Ca", "mg", 260.0),
            (1089, "Iron, Fe", "mg", 8.0),
            (1092, "Potassium, K", "mg", 240.0),
        ]

        for nutrient_id, name, unit, amount in nutrients_to_add:
            if not db.session.get(Nutrient, nutrient_id):
                db.session.add(Nutrient(id=nutrient_id, name=name, unit_name=unit))
            db.session.add(
                FoodNutrient(
                    fdc_id=usda_food.fdc_id, nutrient_id=nutrient_id, amount=amount
                )
            )

        db.session.commit()
    return client


def test_generate_nutrition_label_pdf(client_with_usda_food):
    response = client_with_usda_food.get("/generate_nutrition_label/167588")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


def test_generate_nutrition_label_svg(client_with_usda_food):
    response = client_with_usda_food.get("/nutrition_label_svg/167588")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"


@pytest.fixture
def client_with_my_food(auth_client_utils):
    client, user_id = auth_client_utils
    with client.application.app_context():
        my_food = MyFood(
            user_id=user_id,
            description="Test MyFood",
            calories_per_100g=150,
            protein_per_100g=10,
            carbs_per_100g=20,
            fat_per_100g=5,
        )
        db.session.add(my_food)
        db.session.commit()
        my_food_id = my_food.id
    return client, my_food_id


def test_generate_myfood_label_pdf_label_only(client_with_my_food):
    client, my_food_id = client_with_my_food
    response = client.get(f"/my_foods/{my_food_id}/generate_pdf_label")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


def test_generate_myfood_label_pdf_details(client_with_my_food):
    client, my_food_id = client_with_my_food
    response = client.get(f"/my_foods/{my_food_id}/generate_pdf_details")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


@pytest.fixture
def client_with_recipe(auth_client_utils):
    client, user_id = auth_client_utils
    with client.application.app_context():
        my_food_for_recipe = MyFood(user_id=user_id, description="Ingredient Food")
        db.session.add(my_food_for_recipe)
        db.session.commit()

        recipe = Recipe(user_id=user_id, name="Test Recipe")
        db.session.add(recipe)
        db.session.flush()

        ingredient = RecipeIngredient(
            recipe_id=recipe.id, amount_grams=100, my_food_id=my_food_for_recipe.id
        )
        db.session.add(ingredient)
        db.session.commit()
        recipe_id = recipe.id
    return client, recipe_id


def test_generate_recipe_label_pdf_label_only(client_with_recipe):
    client, recipe_id = client_with_recipe
    response = client.get(f"/recipes/{recipe_id}/generate_label_pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


def test_generate_recipe_label_pdf_details(client_with_recipe):
    client, recipe_id = client_with_recipe
    response = client.get(f"/recipes/{recipe_id}/generate_pdf_details")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


def test_calculate_goals_from_preset_invalid(app_with_db):
    with app_with_db.app_context():
        result = utils.calculate_goals_from_preset(2000, "invalid_preset")
        assert result is None


def test_calculate_goals_from_preset_valid(app_with_db):
    with app_with_db.app_context():
        # Using 'Paleo' as a valid preset from constants.py
        result = utils.calculate_goals_from_preset(2000, "Paleo")
        assert result is not None
        assert "calories" in result
        assert "protein" in result
        assert "carbs" in result
        assert "fat" in result
        assert result["calories"] == 2000
        assert result["protein"] == 150  # (2000 * 0.30) / 4
        assert result["carbs"] == 150  # (2000 * 0.30) / 4
        assert result["fat"] == 89  # (2000 * 0.40) / 9 (approx)


@pytest.fixture
def user_for_utils(auth_client_utils):
    client, user_id = auth_client_utils
    return client, user_id


def test_calculate_weekly_nutrition_summary_no_logs():
    summary = utils.calculate_weekly_nutrition_summary([])
    assert summary.avg_calories == 0
    assert summary.avg_protein == 0
    assert summary.avg_carbs == 0
    assert summary.avg_fat == 0


def test_calculate_weekly_nutrition_summary_with_logs(user_for_utils):
    client, user_id = user_for_utils
    with client.application.app_context():
        # Create a MyFood item with known nutritional values
        my_food = MyFood(
            user_id=user_id,
            description="Test Log Food",
            calories_per_100g=100,
            protein_per_100g=10,
            carbs_per_100g=20,
            fat_per_100g=5,
        )
        db.session.add(my_food)
        db.session.commit()

        # Create logs for 3 different days
        log1 = DailyLog(
            user_id=user_id,
            log_date=date(2025, 1, 1),
            my_food_id=my_food.id,
            amount_grams=100,
        )  # 100 kcal
        log2 = DailyLog(
            user_id=user_id,
            log_date=date(2025, 1, 1),
            my_food_id=my_food.id,
            amount_grams=50,
        )  # 50 kcal
        log3 = DailyLog(
            user_id=user_id,
            log_date=date(2025, 1, 2),
            my_food_id=my_food.id,
            amount_grams=200,
        )  # 200 kcal
        log4 = DailyLog(
            user_id=user_id,
            log_date=date(2025, 1, 3),
            my_food_id=my_food.id,
            amount_grams=100,
        )  # 100 kcal

        weekly_log_data = [log1, log2, log3, log4]
        db.session.add_all(weekly_log_data)
        db.session.commit()

        summary = utils.calculate_weekly_nutrition_summary(weekly_log_data)
        # Day 1: 150 kcal, 15p, 30c, 7.5f
        # Day 2: 200 kcal, 20p, 40c, 10f
        # Day 3: 100 kcal, 10p, 20c, 5f
        # Total Cals: 450 / 3 days = 150 avg
        # Total Prot: 45 / 3 days = 15 avg
        # Total Carb: 90 / 3 days = 30 avg
        # Total Fat: 22.5 / 3 days = 7.5 avg
        assert summary.avg_calories == pytest.approx(150.0)
        assert summary.avg_protein == pytest.approx(15.0)
        assert summary.avg_carbs == pytest.approx(30.0)
        assert summary.avg_fat == pytest.approx(7.5)
