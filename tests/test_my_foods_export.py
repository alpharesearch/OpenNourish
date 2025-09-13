import yaml
from flask import url_for
from models import db, MyFood, FoodCategory, UnifiedPortion


def test_export_my_foods_get_unauthenticated(client):
    """Test that unauthenticated access to export route redirects to login."""
    response = client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 302
    assert "/login" in response.location


def test_export_my_foods_get_authenticated(auth_client):
    """Test that authenticated access to export route returns a YAML file."""
    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    assert response.mimetype == "application/x-yaml"
    assert "attachment; filename=" in response.headers["Content-Disposition"]


def test_export_my_foods_empty_data(auth_client):
    """Test export with no custom foods returns empty YAML list."""
    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    assert response.data.decode("utf-8").strip() == "[]"


def test_export_my_foods_with_data_and_scaling(auth_client):
    """Test export with data and that nutrition is scaled to the first portion."""
    with auth_client.application.app_context():
        category = FoodCategory(description="Test Category", user_id=1)
        db.session.add(category)
        db.session.commit()

        food = MyFood(
            user_id=1,
            description="Test Food",
            ingredients="Test ingredients",
            upc="123456789012",
            fdc_id=123456,
            food_category_id=category.id,
            calories_per_100g=100.0,
            protein_per_100g=10.0,
        )
        db.session.add(food)
        db.session.commit()

        # This is the first portion, so nutrition should be scaled to its weight (150g)
        portion = UnifiedPortion(my_food_id=food.id, gram_weight=150.0, seq_num=1)
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1
    food_item = data[0]

    assert food_item["description"] == "Test Food"
    assert food_item["upc"] == "123456789012"
    assert "portions" in food_item
    assert len(food_item["portions"]) == 1

    # Check that nutrition is scaled to the 150g portion
    assert "nutrition_facts" in food_item
    nutrition = food_item["nutrition_facts"]
    assert nutrition["calories"] == 150  # 100kcal/100g * 1.5
    assert nutrition["protein_grams"] == 15.0  # 10g/100g * 1.5


def test_export_my_foods_multiple_foods(auth_client):
    """Test export with multiple custom foods."""
    with auth_client.application.app_context():
        food1 = MyFood(user_id=1, description="Apple", calories_per_100g=52.0)
        food2 = MyFood(user_id=1, description="Banana", calories_per_100g=89.0)
        db.session.add_all([food1, food2])
        db.session.commit()

        p1 = UnifiedPortion(my_food_id=food1.id, gram_weight=182.0, seq_num=1)
        p2 = UnifiedPortion(my_food_id=food2.id, gram_weight=118.0, seq_num=1)
        db.session.add_all([p1, p2])
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 2
    apple_data = next(item for item in data if item["description"] == "Apple")
    banana_data = next(item for item in data if item["description"] == "Banana")

    # 52kcal/100g * 1.82 = 94.64
    assert apple_data["nutrition_facts"]["calories"] == 95
    # 89kcal/100g * 1.18 = 105.02
    assert banana_data["nutrition_facts"]["calories"] == 105


def test_export_my_foods_all_nutrients(auth_client):
    """Test export includes all nutrient data correctly, scaled to the first portion."""
    with auth_client.application.app_context():
        food = MyFood(
            user_id=1,
            description="Full Nutrition Food",
            calories_per_100g=120.0,
            protein_per_100g=25.0,
            carbs_per_100g=8.0,
            fat_per_100g=3.0,
            saturated_fat_per_100g=1.5,
            trans_fat_per_100g=0.1,
            cholesterol_mg_per_100g=20.0,
            sodium_mg_per_100g=80.0,
            fiber_per_100g=0.5,
            sugars_per_100g=4.0,
            added_sugars_per_100g=2.0,
            vitamin_d_mcg_per_100g=0.2,
            calcium_mg_per_100g=150.0,
            iron_mg_per_100g=0.8,
            potassium_mg_per_100g=300.0,
        )
        db.session.add(food)
        db.session.commit()
        # Scale to a 50g portion
        p1 = UnifiedPortion(my_food_id=food.id, gram_weight=50.0, seq_num=1)
        db.session.add(p1)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1
    nutrition = data[0]["nutrition_facts"]

    assert nutrition["calories"] == 60  # 120 * 0.5
    assert nutrition["protein_grams"] == 12.5  # 25 * 0.5
    assert nutrition["carbohydrates_grams"] == 4.0  # 8 * 0.5
    assert nutrition["fat_grams"] == 1.5  # 3 * 0.5
    assert nutrition["saturated_fat_grams"] == 0.75  # 1.5 * 0.5


def test_export_my_foods_user_isolation(auth_client_two_users):
    """Test that users only see their own exported foods."""
    client, user_one, user_two = auth_client_two_users
    with client.application.app_context():
        food1 = MyFood(user_id=user_one.id, description="User One Food")
        food2 = MyFood(user_id=user_two.id, description="User Two Food")
        db.session.add_all([food1, food2])
        db.session.commit()

    response = client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    data = yaml.safe_load(response.data)
    assert len(data) == 1
    assert data[0]["description"] == "User One Food"


def test_export_my_foods_no_category(auth_client):
    """Test export when a food has no category."""
    with auth_client.application.app_context():
        food = MyFood(user_id=1, description="No Category Food")
        db.session.add(food)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    data = yaml.safe_load(response.data)
    assert len(data) == 1
    assert data[0]["description"] == "No Category Food"
    assert data[0]["category"] == ""


def test_export_my_foods_with_ingredients(auth_client):
    """Test export includes ingredients field."""
    with auth_client.application.app_context():
        food = MyFood(
            user_id=1, description="Food With Ingredients", ingredients="A, B, C"
        )
        db.session.add(food)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    data = yaml.safe_load(response.data)
    assert len(data) == 1
    assert data[0]["ingredients"] == "A, B, C"


def test_export_my_foods_with_none_values(auth_client):
    """Test export handles None values for nutrients correctly (scales to 0)."""
    with auth_client.application.app_context():
        food = MyFood(user_id=1, description="None Nutrition", protein_per_100g=None)
        db.session.add(food)
        db.session.commit()
        p1 = UnifiedPortion(my_food_id=food.id, gram_weight=100.0, seq_num=1)
        db.session.add(p1)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    data = yaml.safe_load(response.data)
    assert data[0]["nutrition_facts"]["protein_grams"] == 0


def test_export_my_foods_filename_format(auth_client):
    """Test that the exported filename has correct format."""
    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    content_disposition = response.headers["Content-Disposition"]
    assert "attachment; filename=" in content_disposition
    assert ".yaml" in content_disposition
