from flask import url_for
from models import db, Recipe, MyFood, RecipeIngredient, User, UnifiedPortion


def test_import_recipe_from_simple_text(auth_client):
    """Tests importing a recipe from a simple YAML/text format."""
    yaml_content = """
name: "LLM-Generated Pancakes"
servings: 4
instructions: |
  1. Mix flour and sugar.
  2. Add egg and milk.
  3. Cook on griddle.
ingredients:
  - "1 1/2 cups all-purpose flour"
  - "2 tbsp sugar"
  - "1 large egg"
"""
    response = auth_client.post(
        url_for("recipes.import_recipes"),
        data={"yaml_text": yaml_content},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert (
        b"Recipe imported! Please match the ingredients to real foods." in response.data
    )

    with auth_client.application.app_context():
        recipe = Recipe.query.filter_by(name="LLM-Generated Pancakes").first()
        assert recipe is not None
        assert recipe.servings == 4
        assert "Cook on griddle" in recipe.instructions
        assert len(recipe.ingredients) == 3

        # Verify that placeholder MyFood items were created
        for ingredient in recipe.ingredients:
            assert ingredient.my_food is not None
            assert ingredient.my_food.is_placeholder is True
            assert ingredient.my_food.description in [
                "1 1/2 cups all-purpose flour",
                "2 tbsp sugar",
                "1 large egg",
            ]


def test_rematch_ingredient_flow(auth_client):
    """Tests the full workflow of rematching a placeholder ingredient."""
    # 1. Setup: Create a recipe with a placeholder ingredient and a real food to match
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()

        # The placeholder
        placeholder_food = MyFood(
            user_id=user.id, description="1 cup flour", is_placeholder=True
        )
        db.session.add(placeholder_food)
        db.session.flush()

        # The recipe using the placeholder
        recipe = Recipe(user_id=user.id, name="Placeholder Recipe")
        db.session.add(recipe)
        db.session.flush()

        ingredient_to_rematch = RecipeIngredient(
            recipe_id=recipe.id, my_food_id=placeholder_food.id, amount_grams=100
        )
        db.session.add(ingredient_to_rematch)
        db.session.flush()

        # The real food that we will match to
        real_food = MyFood(
            user_id=user.id, description="Real All-Purpose Flour", calories_per_100g=364
        )
        db.session.add(real_food)
        db.session.flush()  # Flush to get real_food.id

        # Add a portion to the real food
        real_food_portion = UnifiedPortion(
            my_food_id=real_food.id,
            gram_weight=120,
            measure_unit_description="cup",
            amount=1,
        )
        db.session.add(real_food_portion)
        db.session.commit()

        recipe_id = recipe.id
        ingredient_id_to_replace = ingredient_to_rematch.id
        placeholder_food_id = placeholder_food.id
        real_food_id = real_food.id
        real_food_portion_id = real_food_portion.id

    # 2. Verify the Edit Page UI shows the 'Match Food' button
    response = auth_client.get(url_for("recipes.edit_recipe", recipe_id=recipe_id))
    assert response.status_code == 200
    assert b"1 cup flour" in response.data
    rematch_url = url_for(
        "search.search",
        target="rematch_ingredient",
        ingredient_id_to_replace=ingredient_id_to_replace,
        recipe_id=recipe_id,
        search_term="1 cup flour",
    )
    assert bytes(rematch_url.replace("&", "&amp;"), "utf-8") in response.data
    assert b"Match Food" in response.data

    # 3. Test the add_item Rematch Logic
    rematch_post_data = {
        "target": "rematch_ingredient",
        "ingredient_id_to_replace": ingredient_id_to_replace,
        "food_id": real_food_id,
        "food_type": "my_food",
        "amount": 1,
        "portion_id": real_food_portion_id,
    }
    response = auth_client.post(
        url_for("search.add_item"), data=rematch_post_data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Ingredient matched successfully" in response.data

    # 4. Assert the Results
    with auth_client.application.app_context():
        # Verify the ingredient was updated
        updated_ingredient = db.session.get(RecipeIngredient, ingredient_id_to_replace)
        assert updated_ingredient is not None
        assert updated_ingredient.my_food_id == real_food_id
        assert updated_ingredient.fdc_id is None
        assert updated_ingredient.recipe_id_link is None

        # Verify the placeholder food was deleted
        deleted_placeholder = db.session.get(MyFood, placeholder_food_id)
        assert deleted_placeholder is None

        # Verify recipe nutrition was updated
        recipe = db.session.get(Recipe, recipe_id)
        assert recipe.calories_per_100g > 0


def test_rematch_does_not_delete_used_placeholder(auth_client):
    """Ensures a placeholder MyFood is not deleted if another recipe still uses it."""
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        placeholder = MyFood(
            user_id=user.id, description="Shared Placeholder", is_placeholder=True
        )
        recipe1 = Recipe(user_id=user.id, name="Recipe One")
        recipe2 = Recipe(user_id=user.id, name="Recipe Two")
        real_food = MyFood(user_id=user.id, description="Real Food")
        db.session.add_all([placeholder, recipe1, recipe2, real_food])
        db.session.flush()

        # Both recipes use the same placeholder
        ing1 = RecipeIngredient(
            recipe_id=recipe1.id, my_food_id=placeholder.id, amount_grams=10
        )
        ing2 = RecipeIngredient(
            recipe_id=recipe2.id, my_food_id=placeholder.id, amount_grams=20
        )
        portion = UnifiedPortion(my_food_id=real_food.id, gram_weight=1)
        db.session.add_all([ing1, ing2, portion])
        db.session.commit()

        ingredient_id_to_replace = ing1.id
        placeholder_id = placeholder.id
        real_food_id = real_food.id
        portion_id = portion.id

    # Rematch the ingredient in the first recipe
    rematch_post_data = {
        "target": "rematch_ingredient",
        "ingredient_id_to_replace": ingredient_id_to_replace,
        "food_id": real_food_id,
        "food_type": "my_food",
        "amount": 1,
        "portion_id": portion_id,
    }
    auth_client.post(url_for("search.add_item"), data=rematch_post_data)

    with auth_client.application.app_context():
        # Verify the placeholder was NOT deleted
        still_exists = db.session.get(MyFood, placeholder_id)
        assert still_exists is not None

        # Verify the second recipe still points to it
        recipe2 = Recipe.query.filter_by(name="Recipe Two").first()
        assert recipe2.ingredients[0].my_food_id == placeholder_id


def test_rematch_to_placeholder_is_prevented(auth_client):
    """Tests that a user cannot match a placeholder to another placeholder."""
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        recipe = Recipe(user_id=user.id, name="Test Recipe")
        placeholder1 = MyFood(
            user_id=user.id, description="Placeholder 1", is_placeholder=True
        )
        placeholder2 = MyFood(
            user_id=user.id, description="Placeholder 2", is_placeholder=True
        )
        db.session.add_all([recipe, placeholder1, placeholder2])
        db.session.flush()

        ingredient = RecipeIngredient(
            recipe_id=recipe.id, my_food_id=placeholder1.id, amount_grams=100
        )
        portion = UnifiedPortion(my_food_id=placeholder2.id, gram_weight=1)
        db.session.add_all([ingredient, portion])
        db.session.commit()

        ingredient_id = ingredient.id
        placeholder2_id = placeholder2.id
        portion_id = portion.id
        placeholder1_id = placeholder1.id

    # Attempt to rematch placeholder1 to placeholder2
    rematch_post_data = {
        "target": "rematch_ingredient",
        "ingredient_id_to_replace": ingredient_id,
        "food_id": placeholder2_id,
        "food_type": "my_food",
        "amount": 1,
        "portion_id": portion_id,
    }
    response = auth_client.post(
        url_for("search.add_item"), data=rematch_post_data, follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Cannot match an ingredient to another placeholder." in response.data

    # Verify no change was made
    with auth_client.application.app_context():
        ingredient = db.session.get(RecipeIngredient, ingredient_id)
        assert ingredient.my_food_id == placeholder1_id
