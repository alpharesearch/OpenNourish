import pytest
from flask import url_for
from models import db, User, MyFood, Recipe, UnifiedPortion, DailyLog
from datetime import date


@pytest.fixture
def user_a_id(app_with_db):
    with app_with_db.app_context():
        user = User(username="usera", email="usera@example.com")
        user.set_password("passwordA")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def user_b_id(app_with_db):
    with app_with_db.app_context():
        user = User(username="userb", email="userb@example.com")
        user.set_password("passwordB")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def client_a(client, app_with_db, user_a_id):
    """Provides a client logged in as user_a."""
    with app_with_db.app_context():
        user_a = db.session.get(User, user_a_id)
        client.post(
            url_for("auth.login"),
            data={"username_or_email": user_a.username, "password": "passwordA"},
            follow_redirects=True,
        )
        yield client


def test_get_portions_api_endpoint(client_a, user_a_id):
    """
    Test Case 1: API Endpoint for Portions
    """
    with client_a.application.app_context():
        my_food = MyFood(user_id=user_a_id, description="Test Food")
        db.session.add(my_food)
        db.session.commit()

        portions = [
            UnifiedPortion(
                my_food_id=my_food.id, portion_description="slice", gram_weight=25.0
            ),
            UnifiedPortion(
                my_food_id=my_food.id, portion_description="cup", gram_weight=200.0
            ),
            UnifiedPortion(
                my_food_id=my_food.id, portion_description="serving", gram_weight=100.0
            ),
        ]
        db.session.add_all(portions)
        db.session.commit()

        response = client_a.get(
            url_for("search.get_portions", food_type="my_food", food_id=my_food.id)
        )

        assert response.status_code == 200
        assert response.content_type == "application/json"

        json_data = response.get_json()
        assert len(json_data) == 3

        for portion in json_data:
            assert "id" in portion
            assert "description" in portion
            assert "gram_weight" in portion


def test_get_portions_api_authorization(client, app_with_db, user_a_id, user_b_id):
    """
    Test Case 2: Authorization of the API Endpoint
    """
    with app_with_db.app_context():
        user_b = db.session.get(User, user_b_id)
        my_food_a = MyFood(user_id=user_a_id, description="User A's Food")
        db.session.add(my_food_a)
        db.session.commit()

        # Log in as User B
        client.post(
            url_for("auth.login"),
            data={"username_or_email": user_b.username, "password": "passwordB"},
            follow_redirects=True,
        )

        response = client.get(
            url_for("search.get_portions", food_type="my_food", food_id=my_food_a.id)
        )

        assert response.status_code == 404


def test_add_to_diary_button_is_present_on_list_pages(client_a, user_a_id):
    """
    Test Case 3: UI - Presence of the "Add" Button
    """
    with client_a.application.app_context():
        my_food = MyFood(user_id=user_a_id, description="My Test Food")
        recipe = Recipe(user_id=user_a_id, name="My Test Recipe", servings=4)
        db.session.add_all([my_food, recipe])
        db.session.commit()

        # Test My Foods page
        response_my_foods = client_a.get(url_for("my_foods.my_foods"))
        assert response_my_foods.status_code == 200
        assert 'data-food-type="my_food"' in response_my_foods.data.decode("utf-8")
        assert f'data-food-id="{my_food.id}"' in response_my_foods.data.decode("utf-8")

        # Test Recipes page
        response_recipes = client_a.get(url_for("recipes.recipes"))
        assert response_recipes.status_code == 200
        assert 'data-food-type="recipe"' in response_recipes.data.decode("utf-8")
        assert f'data-food-id="{recipe.id}"' in response_recipes.data.decode("utf-8")


def test_end_to_end_add_via_modal_workflow(client_a, user_a_id):
    """
    Test Case 4: End-to-End Success Scenario
    """
    with client_a.application.app_context():
        recipe = Recipe(user_id=user_a_id, name="Test Recipe", servings=1)
        db.session.add(recipe)
        db.session.commit()

        portion = UnifiedPortion(
            recipe_id=recipe.id, portion_description="serving", gram_weight=150.0
        )
        db.session.add(portion)
        db.session.commit()

        today = date.today().isoformat()

        response = client_a.post(
            url_for("search.add_item"),
            data={
                "target": "diary",
                "food_type": "recipe",
                "food_id": recipe.id,
                "log_date": today,
                "meal_name": "Lunch",
                "amount": 2,
                "portion_id": portion.id,
            },
        )

        assert response.status_code == 302  # Should redirect

        with client_a.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
            assert len(flashes) > 0
            assert flashes[0][0] == "success"
            assert "added to your diary" in flashes[0][1]

        log_entry = DailyLog.query.filter_by(
            user_id=user_a_id, log_date=date.fromisoformat(today)
        ).first()
        assert log_entry is not None
        assert log_entry.recipe_id == recipe.id
        assert log_entry.amount_grams == 300.0
