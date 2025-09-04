import pytest
from models import db, Recipe, RecipeIngredient, User, MyFood, UnifiedPortion


@pytest.fixture
def client_with_recipe_ingredient(client):
    with client.application.app_context():
        user = User(username="testuser", email="test@example.com")
        user.set_password("password")
        other_user = User(username="otheruser", email="other@example.com")
        other_user.set_password("password")
        db.session.add_all([user, other_user])
        db.session.commit()

        my_food = MyFood(user_id=user.id, description="Test Food")
        db.session.add(my_food)
        db.session.commit()

        recipe = Recipe(
            user_id=user.id,
            name="Test Recipe",
            is_public=True,
            final_weight_grams=500.0,
        )
        db.session.add(recipe)
        db.session.commit()

        recipe_portion = UnifiedPortion(
            recipe_id=recipe.id,
            gram_weight=100,
            portion_description="serving",
            seq_num=1,
        )
        db.session.add(recipe_portion)
        db.session.commit()

        ingredient_portion = UnifiedPortion(
            my_food_id=my_food.id, gram_weight=50, portion_description="slice"
        )
        db.session.add(ingredient_portion)
        db.session.commit()

        ingredient = RecipeIngredient(
            recipe_id=recipe.id,
            my_food_id=my_food.id,
            amount_grams=100,
            seq_num=1,
            portion_id_fk=ingredient_portion.id,
            serving_type="slice",
        )
        db.session.add(ingredient)
        db.session.commit()

        # Log in user
        with client.session_transaction() as sess:
            sess["_user_id"] = user.id
            sess["_fresh"] = True

        yield client, recipe.id, ingredient.id, other_user.id


def test_delete_ingredient_success(client_with_recipe_ingredient):
    client, recipe_id, ingredient_id, _ = client_with_recipe_ingredient

    response = client.post(
        f"/recipes/ingredients/{ingredient_id}/delete", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Ingredient deleted." in response.data
    assert b"Undo" in response.data
    assert db.session.get(RecipeIngredient, ingredient_id) is None


def test_delete_ingredient_unauthorized(client_with_recipe_ingredient):
    client, _, ingredient_id, other_user_id = client_with_recipe_ingredient

    # Log in as other_user
    with client.session_transaction() as sess:
        sess["_user_id"] = other_user_id

    response = client.post(
        f"/recipes/ingredients/{ingredient_id}/delete", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"You are not authorized to modify this recipe." in response.data
    assert db.session.get(RecipeIngredient, ingredient_id) is not None


def test_update_ingredient_success(client_with_recipe_ingredient):
    client, recipe_id, ingredient_id, _ = client_with_recipe_ingredient
    from models import UnifiedPortion

    with client.application.app_context():
        portion = UnifiedPortion(
            recipe_id=recipe_id, gram_weight=50, portion_description="test"
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/update",
        data={"amount": "2", "portion_id": portion_id},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Ingredient updated successfully." in response.data
    ingredient = db.session.get(RecipeIngredient, ingredient_id)
    assert ingredient.amount_grams == 100


def test_update_ingredient_invalid_amount(client_with_recipe_ingredient):
    client, _, ingredient_id, _ = client_with_recipe_ingredient
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/update",
        data={"amount": "-1", "portion_id": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Amount must be a positive number." in response.data


def test_update_ingredient_no_portion(client_with_recipe_ingredient):
    client, recipe_id, ingredient_id, _ = client_with_recipe_ingredient
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/update",
        data={"amount": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion is required." in response.data


def test_update_ingredient_portion_not_found(client_with_recipe_ingredient):
    client, recipe_id, ingredient_id, _ = client_with_recipe_ingredient
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/update",
        data={"amount": "1", "portion_id": "999"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Selected portion not found." in response.data


def test_move_ingredient_up_down(client_with_recipe_ingredient):
    client, recipe_id, ingredient_id, _ = client_with_recipe_ingredient
    with client.application.app_context():
        # Add a second ingredient to the recipe
        my_food2 = MyFood(user_id=1, description="Test Food 2")
        db.session.add(my_food2)
        db.session.commit()
        ingredient2 = RecipeIngredient(
            recipe_id=recipe_id, my_food_id=my_food2.id, amount_grams=50, seq_num=2
        )
        db.session.add(ingredient2)
        # Set seq_num for the first ingredient
        ingredient1 = db.session.get(RecipeIngredient, ingredient_id)
        ingredient1.seq_num = 1
        db.session.commit()
        ingredient2_id = ingredient2.id

    # Move down
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/move_down", follow_redirects=False
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Ingredient moved down."

    client.get(f"/recipes/{recipe_id}/edit")

    # Move up
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/move_up", follow_redirects=False
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Ingredient moved up."

    client.get(f"/recipes/{recipe_id}/edit")

    # Move up again (already at top)
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient_id}/move_up", follow_redirects=False
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Ingredient is already at the top."

    client.get(f"/recipes/{recipe_id}/edit")

    # Move down again (already at bottom)
    response = client.post(
        f"/recipes/recipe/ingredient/{ingredient2_id}/move_down", follow_redirects=False
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][1] == "Ingredient is already at the bottom."


def test_delete_recipe_success(client_with_recipe_ingredient):
    client, recipe_id, _, _ = client_with_recipe_ingredient
    response = client.post(f"/recipes/{recipe_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Recipe deleted." in response.data
    assert b"Undo" in response.data
    assert db.session.get(Recipe, recipe_id).user_id is None


def test_delete_recipe_unauthorized(client_with_recipe_ingredient):
    client, recipe_id, _, other_user_id = client_with_recipe_ingredient
    with client.session_transaction() as sess:
        sess["_user_id"] = other_user_id
    response = client.post(f"/recipes/{recipe_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"You are not authorized to delete this recipe." in response.data
    assert db.session.get(Recipe, recipe_id).user_id is not None


def test_copy_recipe(client_with_recipe_ingredient):
    client, recipe_id, _, other_user_id = client_with_recipe_ingredient
    with client.session_transaction() as sess:
        sess["_user_id"] = other_user_id
    response = client.post(f"/recipes/{recipe_id}/copy", follow_redirects=False)
    assert response.status_code == 302
    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert "Successfully copied" in flashes[0][1]

    response = client.get(response.headers["Location"], follow_redirects=True)
    assert response.status_code == 200

    with client.application.app_context():
        original_recipe = db.session.get(Recipe, recipe_id)
        copied_recipe = Recipe.query.filter(Recipe.user_id == other_user_id).first()
        assert copied_recipe is not None
        assert copied_recipe.name == "Test Recipe (Copy)"
        assert len(copied_recipe.ingredients) == 1
        assert copied_recipe.final_weight_grams == original_recipe.final_weight_grams
        assert len(copied_recipe.portions) == 1
        assert copied_recipe.portions[0].seq_num == original_recipe.portions[0].seq_num

        original_ingredient = original_recipe.ingredients[0]
        copied_ingredient = copied_recipe.ingredients[0]
        assert copied_ingredient.portion_id_fk == original_ingredient.portion_id_fk
        assert copied_ingredient.serving_type == original_ingredient.serving_type
