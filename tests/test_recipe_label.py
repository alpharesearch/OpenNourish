import pytest
from models import (
    db,
    Recipe,
    RecipeIngredient,
    MyFood,
    User,
)


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


def test_generate_recipe_label_svg(client_with_recipe):
    client, recipe_id = client_with_recipe
    response = client.get(f"/recipes/{recipe_id}/nutrition-label.svg")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
