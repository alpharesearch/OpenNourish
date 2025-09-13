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
    """Test export with no custom foods returns empty YAML."""
    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200
    # Should return an empty list in YAML format
    assert response.data.decode("utf-8").strip() == "[]"


def test_export_my_foods_with_data(auth_client):
    """Test export with actual custom foods data."""
    with auth_client.application.app_context():
        # Create a test food item
        food = MyFood(
            user_id=1,
            description="Test Food",
            ingredients="Test ingredients",
            calories_per_100g=100.0,
            protein_per_100g=5.0,
            carbs_per_100g=20.0,
            fat_per_100g=2.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="cup",
            gram_weight=150.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

        # Create a category for the food
        category = FoodCategory(description="Test Category", user_id=1)
        db.session.add(category)
        db.session.commit()

        # Assign category to food
        food.food_category_id = category.id
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that the response contains valid YAML content
    yaml_content = response.data.decode("utf-8")
    assert "Test Food" in yaml_content
    assert "Test Category" in yaml_content
    assert "cup" in yaml_content
    assert "150.0" in yaml_content


def test_export_my_foods_multiple_foods(auth_client):
    """Test export with multiple custom foods."""
    with auth_client.application.app_context():
        # Create first food item
        food1 = MyFood(
            user_id=1,
            description="Apple",
            ingredients="Fresh apple",
            calories_per_100g=52.0,
            protein_per_100g=0.3,
            carbs_per_100g=13.8,
            fat_per_100g=0.2,
        )
        db.session.add(food1)

        # Create second food item
        food2 = MyFood(
            user_id=1,
            description="Banana",
            ingredients="Fresh banana",
            calories_per_100g=89.0,
            protein_per_100g=1.1,
            carbs_per_100g=22.8,
            fat_per_100g=0.3,
        )
        db.session.add(food2)
        db.session.commit()

        # Create portions for both foods
        portion1 = UnifiedPortion(
            my_food_id=food1.id,
            amount=1,
            measure_unit_description="medium",
            gram_weight=182.0,
            seq_num=1,
        )
        db.session.add(portion1)

        portion2 = UnifiedPortion(
            my_food_id=food2.id,
            amount=1,
            measure_unit_description="large",
            gram_weight=118.0,
            seq_num=1,
        )
        db.session.add(portion2)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that both foods are in the export
    yaml_content = response.data.decode("utf-8")
    assert "Apple" in yaml_content
    assert "Banana" in yaml_content
    assert "medium" in yaml_content
    assert "large" in yaml_content


def test_export_my_foods_with_nutrient_data(auth_client):
    """Test export includes all nutrient data correctly scaled for the portion."""
    with auth_client.application.app_context():
        # Create a food item with comprehensive nutrition data
        food = MyFood(
            user_id=1,
            description="Protein Shake",
            ingredients="Whey protein powder, milk, banana",
            calories_per_100g=120.0,
            protein_per_100g=25.0,
            carbs_per_100g=8.0,
            fat_per_100g=3.0,
            saturated_fat_per_100g=1.5,
            trans_fat_per_100g=0.0,
            cholesterol_mg_per_100g=20.0,
            sodium_mg_per_100g=80.0,
            fiber_per_100g=0.5,
            sugars_per_100g=4.0,
            added_sugars_per_100g=2.0,
            vitamin_d_mcg_per_100g=0.0,
            calcium_mg_per_100g=150.0,
            iron_mg_per_100g=0.8,
            potassium_mg_per_100g=300.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=250.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that all nutrient data is present and correctly scaled in the export
    # Original values are per 100g, portion is 250g, so scaling factor is 2.5
    yaml_content = response.data.decode("utf-8")
    assert "Protein Shake" in yaml_content
    assert "serving" in yaml_content
    assert "gram_weight: 250.0" in yaml_content
    assert "calories: 300" in yaml_content  # 120 * 2.5
    assert "protein_grams: 62.5" in yaml_content  # 25 * 2.5
    assert "carbohydrates_grams: 20.0" in yaml_content  # 8 * 2.5
    assert "fat_grams: 7.5" in yaml_content  # 3 * 2.5
    assert "saturated_fat_grams: 3.75" in yaml_content  # 1.5 * 2.5
    assert "cholesterol_milligrams: 50.0" in yaml_content  # 20 * 2.5
    assert "sodium_milligrams: 200.0" in yaml_content  # 80 * 2.5
    assert "fiber_grams: 1.25" in yaml_content  # 0.5 * 2.5
    assert "total_sugars_grams: 10.0" in yaml_content  # 4 * 2.5
    assert "added_sugars_grams: 5.0" in yaml_content  # 2 * 2.5
    assert "calcium_milligrams: 375.0" in yaml_content  # 150 * 2.5
    assert "iron_milligrams: 2.0" in yaml_content  # 0.8 * 2.5
    assert "potassium_milligrams: 750.0" in yaml_content  # 300 * 2.5


def test_export_my_foods_user_isolation(auth_client):
    """Test that users only see their own exported foods."""
    with auth_client.application.app_context():
        # Create a food item for the authenticated user (user_id=1)
        food = MyFood(
            user_id=1,
            description="User Food",
            calories_per_100g=100.0,
            protein_per_100g=5.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a food item for another user (user_id=2)
        other_food = MyFood(
            user_id=2,
            description="Other User Food",
            calories_per_100g=150.0,
            protein_per_100g=7.0,
        )
        db.session.add(other_food)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that only the authenticated user's food is exported
    yaml_content = response.data.decode("utf-8")
    assert "User Food" in yaml_content
    assert "Other User Food" not in yaml_content


def test_export_my_foods_no_category(auth_client):
    """Test export when a food has no category."""
    with auth_client.application.app_context():
        # Create a food item without a category
        food = MyFood(
            user_id=1,
            description="No Category Food",
            calories_per_100g=100.0,
            protein_per_100g=5.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="piece",
            gram_weight=50.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that the food is exported without category issues
    yaml_content = response.data.decode("utf-8")
    assert "No Category Food" in yaml_content
    assert "piece" in yaml_content


def test_export_my_foods_with_ingredients(auth_client):
    """Test export includes ingredients field."""
    with auth_client.application.app_context():
        # Create a food item with ingredients
        food = MyFood(
            user_id=1,
            description="Food With Ingredients",
            ingredients="Ingredient 1, Ingredient 2, Ingredient 3",
            calories_per_100g=100.0,
            protein_per_100g=5.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=100.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that ingredients are included in the export
    yaml_content = response.data.decode("utf-8")
    assert "Food With Ingredients" in yaml_content
    assert "Ingredient 1, Ingredient 2, Ingredient 3" in yaml_content


def test_export_my_foods_with_zero_values(auth_client):
    """Test export handles zero values and invalid portions by falling back to a 100g serving."""
    with auth_client.application.app_context():
        # Create a food item with zero values
        food = MyFood(
            user_id=1,
            description="Zero Nutrition Food",
            calories_per_100g=0.0,
            protein_per_100g=0.0,
            carbs_per_100g=0.0,
            fat_per_100g=0.0,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food with an invalid gram_weight
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="unit",
            gram_weight=0.0,
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that the fallback to a 100g serving was used
    yaml_content = response.data.decode("utf-8")
    assert "Zero Nutrition Food" in yaml_content
    assert "gram_weight: 100.0" in yaml_content
    assert "unit: g" in yaml_content
    assert "amount: 100" in yaml_content
    # Check that nutrient values are still zero
    assert "calories: 0" in yaml_content
    assert "protein_grams: 0" in yaml_content


def test_export_my_foods_with_none_values(auth_client):
    """Test export handles None values correctly."""
    with auth_client.application.app_context():
        # Create a food item with None values (should be converted to 0)
        food = MyFood(
            user_id=1,
            description="None Nutrition Food",
            calories_per_100g=None,
            protein_per_100g=None,
            carbs_per_100g=None,
            fat_per_100g=None,
        )
        db.session.add(food)
        db.session.commit()

        # Create a portion for the food with valid gram_weight (not None) to avoid DB constraint
        portion = UnifiedPortion(
            my_food_id=food.id,
            amount=1,
            measure_unit_description="unit",
            gram_weight=0.0,  # Changed from None to 0.0 to satisfy DB constraints
            seq_num=1,
        )
        db.session.add(portion)
        db.session.commit()

    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that None values are exported as 0
    yaml_content = response.data.decode("utf-8")
    assert "None Nutrition Food" in yaml_content
    assert "0.0" in yaml_content


def test_export_my_foods_filename_format(auth_client):
    """Test that the exported filename has correct format."""
    response = auth_client.get(url_for("my_foods.export_my_foods"))
    assert response.status_code == 200

    # Check that filename contains expected pattern
    content_disposition = response.headers["Content-Disposition"]
    assert "attachment; filename=" in content_disposition
    assert ".yaml" in content_disposition
