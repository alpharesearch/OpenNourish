import yaml
from flask import url_for
from models import db, Recipe, MyFood, RecipeIngredient, User
from sqlalchemy import func


def test_export_recipes(auth_client):
    # Setup: Create a MyFood dependency
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(
            user_id=user.id,
            description="Test Flour",
            calories_per_100g=364,
            protein_per_100g=10,
            carbs_per_100g=76,
            fat_per_100g=1,
        )
        db.session.add(my_food)
        db.session.flush()

        # Setup: Create a nested recipe
        nested_recipe = Recipe(user_id=user.id, name="Simple Syrup")
        db.session.add(nested_recipe)
        db.session.flush()

        # Setup: Create the main recipe
        main_recipe = Recipe(user_id=user.id, name="Test Pancakes")
        db.session.add(main_recipe)
        db.session.flush()

        # Add ingredients to the main recipe
        ing1 = RecipeIngredient(
            recipe_id=main_recipe.id, my_food_id=my_food.id, amount_grams=120
        )
        ing2 = RecipeIngredient(
            recipe_id=main_recipe.id, fdc_id=1123, amount_grams=50
        )  # Egg
        ing3 = RecipeIngredient(
            recipe_id=main_recipe.id, recipe_id_link=nested_recipe.id, amount_grams=20
        )
        db.session.add_all([ing1, ing2, ing3])
        db.session.commit()

    # Action: Call the export route
    response = auth_client.get(url_for("recipes.export_recipes"))
    assert response.status_code == 200
    assert response.mimetype == "application/x-yaml"

    # Verification
    data = yaml.safe_load(response.data)
    assert "format_version" in data
    assert "dependent_my_foods" in data
    assert "recipes" in data

    # Verify dependent food
    assert len(data["dependent_my_foods"]) == 1
    assert data["dependent_my_foods"][0]["description"] == "Test Flour"

    # Verify recipes (should include main and nested)
    assert len(data["recipes"]) == 2
    recipe_names = {r["name"] for r in data["recipes"]}
    assert "Test Pancakes" in recipe_names
    assert "Simple Syrup" in recipe_names

    # Verify ingredients of the main recipe
    pancakes_data = next(r for r in data["recipes"] if r["name"] == "Test Pancakes")
    assert len(pancakes_data["ingredients"]) == 3

    ing_identifiers = {i["identifier"] for i in pancakes_data["ingredients"]}
    assert "Test Flour" in ing_identifiers
    assert 1123 in ing_identifiers
    assert "Simple Syrup" in ing_identifiers


def test_import_recipes(auth_client):
    # Setup: Prepare YAML data for import
    yaml_content = """
format_version: 1.0
dependent_my_foods:
  - description: "Imported Flour"
    category: "Baking"
    portions:
      - amount: 1
        measure_unit_description: "cup"
        gram_weight: 120
    nutrition_facts:
      calories: 400
      protein_grams: 11
      carbohydrates_grams: 80
      fat_grams: 2
recipes:
  - name: "Imported Cake"
    servings: 8
    ingredients:
      - type: "my_food"
        identifier: "Imported Flour"
        amount_grams: 240
      - type: "usda"
        identifier: 1123 # Egg
        amount_grams: 100
"""

    # Action: Post the YAML content to the import route
    response = auth_client.post(
        url_for("recipes.import_recipes"), data={"yaml_text": yaml_content}
    )
    assert response.status_code == 302  # Check for redirect

    # Check flash message
    with auth_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert "Added 1 new recipes" in flashes[0][1]
        assert "and 1 new foods" in flashes[0][1]

    # Verification
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()

        # Verify MyFood was created
        imported_food = MyFood.query.filter(
            func.lower(MyFood.description) == "imported flour",
            MyFood.user_id == user.id,
        ).first()
        assert imported_food is not None
        assert imported_food.calories_per_100g > 0

        # Verify Recipe was created
        imported_recipe = Recipe.query.filter(
            func.lower(Recipe.name) == "imported cake", Recipe.user_id == user.id
        ).first()
        assert imported_recipe is not None
        assert imported_recipe.servings == 8

        # Verify ingredients were linked correctly
        assert len(imported_recipe.ingredients) == 2

        flour_ingredient = next(
            (ing for ing in imported_recipe.ingredients if ing.my_food_id is not None),
            None,
        )
        assert flour_ingredient is not None
        assert flour_ingredient.my_food_id == imported_food.id
        assert flour_ingredient.amount_grams == 240

        usda_ingredient = next(
            (ing for ing in imported_recipe.ingredients if ing.fdc_id is not None), None
        )
        assert usda_ingredient is not None
        assert usda_ingredient.fdc_id == 1123
        assert usda_ingredient.amount_grams == 100

        # Verify nutrition was calculated
        assert imported_recipe.calories_per_100g > 0


def test_import_duplicate_recipe_is_skipped(auth_client):
    # Setup: Create an existing recipe
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        existing_recipe = Recipe(user_id=user.id, name="Existing Recipe")
        db.session.add(existing_recipe)
        db.session.commit()

    yaml_content = """
recipes:
  - name: "Existing Recipe"
    servings: 1
    ingredients: []
  - name: "A New Recipe"
    servings: 1
    ingredients: []
"""

    # Action
    response = auth_client.post(
        url_for("recipes.import_recipes"), data={"yaml_text": yaml_content}
    )
    assert response.status_code == 302

    # Check flash message
    with auth_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert "Added 1 new recipes" in flashes[0][1]

    # Verification
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        recipes = Recipe.query.filter_by(user_id=user.id).all()
        assert len(recipes) == 2  # The original one + the new one
        recipe_names = {r.name for r in recipes}
        assert "Existing Recipe" in recipe_names
        assert "A New Recipe" in recipe_names


def test_import_recipe_with_existing_my_food(auth_client):
    # Setup: Create an existing MyFood
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        existing_food = MyFood(user_id=user.id, description="Existing Flour")
        db.session.add(existing_food)
        db.session.commit()
        existing_food_id = existing_food.id

    yaml_content = """
recipes:
  - name: "New Cake"
    ingredients:
      - type: "my_food"
        identifier: "Existing Flour"
        amount_grams: 150
"""

    # Action
    response = auth_client.post(
        url_for("recipes.import_recipes"), data={"yaml_text": yaml_content}
    )
    assert response.status_code == 302

    # Check flash message
    with auth_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert "Added 1 new recipes" in flashes[0][1]
        assert "and 0 new foods" in flashes[0][1]

    # Verification
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # Ensure no new MyFood was created
        food_count = MyFood.query.filter_by(user_id=user.id).count()
        assert food_count == 1

        # Verify recipe was created and linked to the existing food
        recipe = Recipe.query.filter_by(name="New Cake", user_id=user.id).first()
        assert recipe is not None
        assert len(recipe.ingredients) == 1
        assert recipe.ingredients[0].my_food_id == existing_food_id


def test_import_with_nested_recipe(auth_client):
    yaml_content = """
recipes:
  - name: "Imported Frosting"
    servings: 1
    ingredients:
      - type: "usda"
        identifier: 19206 # Butter
        amount_grams: 113

  - name: "Main Imported Cake"
    servings: 12
    ingredients:
      - type: "recipe"
        identifier: "Imported Frosting"
        amount_grams: 200
"""

    # Action
    response = auth_client.post(
        url_for("recipes.import_recipes"), data={"yaml_text": yaml_content}
    )
    assert response.status_code == 302

    # Check flash message
    with auth_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert "Added 2 new recipes" in flashes[0][1]

    # Verification
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        frosting = Recipe.query.filter_by(
            name="Imported Frosting", user_id=user.id
        ).first()
        cake = Recipe.query.filter_by(
            name="Main Imported Cake", user_id=user.id
        ).first()

        assert frosting is not None
        assert cake is not None

        # Verify the cake links to the frosting
        assert len(cake.ingredients) == 1
        assert cake.ingredients[0].recipe_id_link == frosting.id
