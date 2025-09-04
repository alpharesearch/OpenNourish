import io
import pytest
from flask import url_for
from models import db, MyFood, FoodCategory, UnifiedPortion


def test_import_my_foods_get_unauthenticated(client):
    response = client.get(url_for("my_foods.import_foods"))
    assert response.status_code == 302
    assert "/login" in response.location


def test_import_my_foods_get_authenticated(auth_client):
    response = auth_client.get(url_for("my_foods.import_foods"))
    assert response.status_code == 200
    assert b"Import Custom Foods" in response.data


def test_import_my_foods_happy_path_file(auth_client):
    yaml_content = """
- description: "Test Apple"
  category: "Fruits"
  serving:
    amount: 1
    unit: "medium"
    gram_weight: 182
  nutrition_facts:
    calories: 95
    protein_grams: 0.5
    carbohydrates_grams: 25
    fat_grams: 0.3
- description: "Test Almonds"
  category: "Nuts"
  serving:
    amount: 1
    unit: "oz"
    gram_weight: 28
  nutrition_facts:
    calories: 164
    protein_grams: 6
    carbohydrates_grams: 6
    fat_grams: 14
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Import complete. Successfully added 2 new foods." in response.data

    with auth_client.application.app_context():
        foods = MyFood.query.filter(MyFood.user_id == 1).all()
        assert len(foods) == 2

        apple = MyFood.query.filter_by(description="Test Apple").first()
        assert apple is not None
        assert apple.calories_per_100g == (95 / 182) * 100
        assert apple.protein_per_100g == (0.5 / 182) * 100

        apple_portions = UnifiedPortion.query.filter_by(my_food_id=apple.id).all()
        assert len(apple_portions) == 2
        assert any(p.gram_weight == 182 for p in apple_portions)
        assert any(p.gram_weight == 1 for p in apple_portions)


def test_import_my_foods_happy_path_textarea(auth_client):
    yaml_content = """
- description: "Test Banana"
  category: "Fruits"
  serving:
    amount: 1
    unit: "large"
    gram_weight: 136
  nutrition_facts:
    calories: 121
    protein_grams: 1.5
    carbohydrates_grams: 31
    fat_grams: 0.4
"""
    data = {"yaml_text": yaml_content}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Import complete. Successfully added 1 new foods." in response.data

    with auth_client.application.app_context():
        food = MyFood.query.filter_by(description="Test Banana").first()
        assert food is not None
        assert food.calories_per_100g == pytest.approx((121 / 136) * 100)


def test_import_category_handling(auth_client):
    with auth_client.application.app_context():
        # Existing global category
        global_cat = FoodCategory(description="Breakfast", user_id=None)
        db.session.add(global_cat)
        # Existing private category
        private_cat = FoodCategory(description="User Snacks", user_id=1)
        db.session.add(private_cat)
        db.session.commit()
        global_cat_id = global_cat.id
        private_cat_id = private_cat.id

    yaml_content = """
- description: "Food with Global Category"
  category: "Breakfast"
  serving: {gram_weight: 100, unit: "g"}
  nutrition_facts: {calories: 100}
- description: "Food with Private Category"
  category: "User Snacks"
  serving: {gram_weight: 100, unit: "g"}
  nutrition_facts: {calories: 100}
- description: "Food with New General Category"
  category: "Soups"
  serving: {gram_weight: 100, unit: "g"}
  nutrition_facts: {calories: 100}
- description: "My Test Bar"
  category: "My Test Bar"
  serving: {gram_weight: 100, unit: "g"}
  nutrition_facts: {calories: 100}
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    auth_client.post(url_for("my_foods.import_foods"), data=data, follow_redirects=True)

    with auth_client.application.app_context():
        # Assert correct linking for existing categories
        food1 = MyFood.query.filter_by(description="Food with Global Category").first()
        assert food1.food_category_id == global_cat_id

        food2 = MyFood.query.filter_by(description="Food with Private Category").first()
        assert food2.food_category_id == private_cat_id

        # Assert new category creation
        food3 = MyFood.query.filter_by(
            description="Food with New General Category"
        ).first()
        assert food3.food_category.description == "Soups"
        assert food3.food_category.user_id == 1

        # Assert bad category was not created
        food4 = MyFood.query.filter_by(description="My Test Bar").first()
        assert food4.food_category_id is None

        # Assert total number of new categories
        new_categories = FoodCategory.query.filter(
            FoodCategory.id > private_cat_id
        ).all()
        assert len(new_categories) == 1
        assert new_categories[0].description == "Soups"


def test_import_duplicate_handling(auth_client):
    with auth_client.application.app_context():
        existing_food = MyFood(
            description="Existing Food", user_id=1, calories_per_100g=100
        )
        db.session.add(existing_food)
        db.session.commit()

    yaml_content = """
- description: "Existing Food"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
- description: "Intra-file Dup"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
- description: "Intra-file Dup"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )

    assert b"2 items were skipped." in response.data
    assert (
        b"Skipped items: Existing Food (Already exists), Intra-file Dup (Duplicate in file)"
        in response.data
    )


def test_import_error_handling(auth_client):
    # Invalid file extension
    data = {"file": (io.BytesIO(b"content"), "test.txt")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"Invalid file type" in response.data

    # Malformed YAML
    yaml_content = "key: value: another_value"
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"Error parsing YAML file" in response.data

    # Missing required field
    yaml_content = """
- description: "Missing Gram Weight"
  serving: {}
  nutrition_facts: {calories: 100}
- description: "Valid Food"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"Successfully added 1 new foods" in response.data
    assert b"1 items were skipped" in response.data

    # Zero gram weight with zero calories
    yaml_content = """
- description: "Zero Gram Weight"
  serving: {gram_weight: 0}
  nutrition_facts: {calories: 0}
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"Successfully added 1 new foods" in response.data

    # Empty file
    data = {"file": (io.BytesIO(b""), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"No food items found in the YAML content." in response.data

    # Empty text area
    data = {"yaml_text": " "}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert b"No file selected or text provided." in response.data


def test_import_real_world_example_calculated_weight(auth_client):
    yaml_content = """
- description: "Bacon Egg & Cheese Hashbrown Bowl"
  ingredients: ""
  category: "Breakfast"
  serving:
    amount: 1
    unit: "bowl"
    gram_weight: 0
  nutrition_facts:
    calories: 700
    protein_grams: 30
    carbohydrates_grams: 62
    fat_grams: 48
    saturated_fat_grams: 18
    trans_fat_grams: 0
    cholesterol_milligrams: 425
    sodium_milligrams: 1630
    fiber_grams: 7
    total_sugars_grams: 4
    added_sugars_grams: 0
    vitamin_d_micrograms: 0
    calcium_milligrams: 0
    iron_milligrams: 0
    potassium_milligrams: 0
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    response = auth_client.post(
        url_for("my_foods.import_foods"), data=data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Import complete. Successfully added 1 new foods." in response.data

    with auth_client.application.app_context():
        food = MyFood.query.filter_by(
            description="Bacon Egg & Cheese Hashbrown Bowl"
        ).first()
        assert food is not None
        calculated_gram_weight = 30 + 62 + 48
        assert food.calories_per_100g == pytest.approx(
            (700 / calculated_gram_weight) * 100
        )

        portions = UnifiedPortion.query.filter_by(my_food_id=food.id).all()
        assert len(portions) == 2
        assert any(p.gram_weight == calculated_gram_weight for p in portions)
        assert any(p.gram_weight == 1 for p in portions)
