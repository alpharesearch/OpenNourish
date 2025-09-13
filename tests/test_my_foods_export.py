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


def test_export_my_foods_structure_and_data(auth_client):
    """Test export with a single food item for correct structure and data."""
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
            protein_per_100g=5.0,
            carbs_per_100g=20.0,
            fat_per_100g=2.0,
        )
        db.session.add(food)
        db.session.commit()

        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="cup",
            gram_weight=150.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert isinstance(data, list)
    assert len(data) == 1

    food_item = data[0]
    assert food_item["description"] == "Test Food"
    assert food_item["ingredients"] == "Test ingredients"
    assert food_item["category"] == "Test Category"
    assert food_item["upc"] == "123456789012"
    assert food_item["fdc_id"] == 123456

    assert "portions" in food_item
    assert isinstance(food_item["portions"], list)
    assert len(food_item["portions"]) == 1
    portion_item = food_item["portions"][0]
    assert portion_item["amount"] == 1
    assert portion_item["measure_unit_description"] == "cup"
    assert portion_item["gram_weight"] == 150.0

    assert "nutrition_per_100g" in food_item
    nutrition = food_item["nutrition_per_100g"]
    assert nutrition["calories"] == 100.0
    assert nutrition["protein_grams"] == 5.0
    assert nutrition["carbohydrates_grams"] == 20.0
    assert nutrition["fat_grams"] == 2.0


def test_export_my_foods_multiple_portions(auth_client):
    """Test export for a food with multiple portions."""
    with auth_client.application.app_context():
        food = MyFood(user_id=1, description="Multi-portion Food")
        db.session.add(food)
        db.session.commit()

        p1 = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="slice",
            gram_weight=25.0,
            seq_num=1,
        )
        p2 = UnifiedPortion(
            my_food_id=food.id,
            amount=100,
            measure_unit_description="g",
            gram_weight=100.0,
            seq_num=2,
        )
        db.session.add_all([p1, p2])
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1

    food_item = data[0]
    assert len(food_item["portions"]) == 2
    assert food_item["portions"][0]["measure_unit_description"] == "slice"
    assert food_item["portions"][0]["gram_weight"] == 25.0
    assert food_item["portions"][1]["measure_unit_description"] == "g"
    assert food_item["portions"][1]["gram_weight"] == 100.0


def test_export_my_foods_all_nutrients(auth_client):
    """Test export includes all nutrient data correctly in the per_100g block."""
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

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1
    nutrition = data[0]["nutrition_per_100g"]

    assert nutrition["calories"] == 120.0
    assert nutrition["protein_grams"] == 25.0
    assert nutrition["carbohydrates_grams"] == 8.0
    assert nutrition["fat_grams"] == 3.0
    assert nutrition["saturated_fat_grams"] == 1.5
    assert nutrition["trans_fat_grams"] == 0.1
    assert nutrition["cholesterol_milligrams"] == 20.0
    assert nutrition["sodium_milligrams"] == 80.0
    assert nutrition["fiber_grams"] == 0.5
    assert nutrition["total_sugars_grams"] == 4.0
    assert nutrition["added_sugars_grams"] == 2.0
    assert nutrition["vitamin_d_micrograms"] == 0.2
    assert nutrition["calcium_milligrams"] == 150.0
    assert nutrition["iron_milligrams"] == 0.8
    assert nutrition["potassium_milligrams"] == 300.0


def test_export_my_foods_user_isolation(auth_client_two_users):
    """Test that users only see their own exported foods."""
    client, user_one, user_two = auth_client_two_users

    with client.application.app_context():
        user1_food = MyFood(user_id=user_one.id, description="User 1 Food")
        db.session.add(user1_food)

        user2_food = MyFood(user_id=user_two.id, description="User 2 Food")
        db.session.add(user2_food)
        db.session.commit()

    response = client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1
    assert data[0]["description"] == "User 1 Food"


def test_export_my_foods_handles_none_and_zero_values(auth_client):
    """Test export handles None and zero for nutrients correctly."""
    with auth_client.application.app_context():
        food = MyFood(
            user_id=1,
            description="None and Zero Food",
            calories_per_100g=0,
            protein_per_100g=None,  # Should export as 0
        )
        db.session.add(food)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    data = yaml.safe_load(response.data)
    assert len(data) == 1
    nutrition = data[0]["nutrition_per_100g"]

    assert nutrition["calories"] == 0
    assert nutrition["protein_grams"] == 0
    assert nutrition["carbohydrates_grams"] == 0  # Default for None
