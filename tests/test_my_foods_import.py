import io
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


def test_import_my_foods_happy_path(auth_client):
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


def test_import_category_handling(auth_client):
    with auth_client.application.app_context():
        # Existing global category
        global_cat = FoodCategory(description="Global Category", user_id=None)
        db.session.add(global_cat)
        # Existing private category
        private_cat = FoodCategory(description="Private Category", user_id=1)
        db.session.add(private_cat)
        db.session.commit()

    yaml_content = """
- description: "Food with Global Category"
  category: "Global Category"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
- description: "Food with Private Category"
  category: "Private Category"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
- description: "Food with New Category"
  category: "New Category"
  serving: {gram_weight: 100}
  nutrition_facts: {calories: 100}
"""
    data = {"file": (io.BytesIO(yaml_content.encode("utf-8")), "import.yaml")}
    auth_client.post(url_for("my_foods.import_foods"), data=data, follow_redirects=True)

    with auth_client.application.app_context():
        food1 = MyFood.query.filter_by(description="Food with Global Category").first()
        assert food1.food_category.description == "Global Category"

        food2 = MyFood.query.filter_by(description="Food with Private Category").first()
        assert food2.food_category.description == "Private Category"

        food3 = MyFood.query.filter_by(description="Food with New Category").first()
        assert food3.food_category.description == "New Category"
        assert food3.food_category.user_id == 1


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

    # Zero gram weight
    yaml_content = """
- description: "Zero Gram Weight"
  serving: {gram_weight: 0}
  nutrition_facts: {calories: 100}
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
    assert b"YAML file must contain a list of food items" in response.data


def test_import_real_world_example(auth_client):
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
        assert food.calories_per_100g == 700
        assert food.protein_per_100g == 30
        assert food.carbs_per_100g == 62
        assert food.fat_per_100g == 48
        assert food.saturated_fat_per_100g == 18
        assert food.trans_fat_per_100g == 0
        assert food.cholesterol_mg_per_100g == 425
        assert food.sodium_mg_per_100g == 1630
        assert food.fiber_per_100g == 7
        assert food.sugars_per_100g == 4
        assert food.added_sugars_per_100g == 0

        portions = UnifiedPortion.query.filter_by(my_food_id=food.id).all()
        assert len(portions) == 1
        assert portions[0].gram_weight == 0
        assert portions[0].measure_unit_description == "bowl"
