import pytest
from models import db, FoodCategory, MyFood
from flask import url_for
import re


@pytest.fixture
def category_fixture(auth_client_with_user):
    client, user = auth_client_with_user
    with client.application.app_context():
        category = FoodCategory(description="Test Category", user_id=user.id)
        db.session.add(category)
        db.session.commit()
        yield client, user, category


def test_manage_categories_get(auth_client_with_user):
    client, user = auth_client_with_user
    response = client.get(url_for("my_foods.manage_categories"))
    assert response.status_code == 200
    assert b"Manage Categories" in response.data


def test_add_category_post(auth_client_with_user):
    client, user = auth_client_with_user
    response = client.post(
        url_for("my_foods.manage_categories"),
        data={"description": "New Category"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Category added successfully." in response.data
    with client.application.app_context():
        category = FoodCategory.query.filter_by(description="New Category").first()
        assert category is not None


def test_add_existing_category_post(category_fixture):
    client, user, category = category_fixture
    response = client.post(
        url_for("my_foods.manage_categories"),
        data={"description": "Test Category"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"A category with this name already exists." in response.data


def test_edit_category_post(category_fixture):
    client, user, category = category_fixture
    response = client.post(
        url_for("my_foods.edit_category", category_id=category.id),
        data={"description": "Updated Category"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Category updated successfully." in response.data
    with client.application.app_context():
        updated_category = db.session.get(FoodCategory, category.id)
        assert updated_category.description == "Updated Category"


def test_delete_category_post(category_fixture):
    client, user, category = category_fixture
    response = client.post(
        url_for("my_foods.delete_category", category_id=category.id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Category deleted successfully!" in response.data
    with client.application.app_context():
        deleted_category = db.session.get(FoodCategory, category.id)
        assert deleted_category is None


def test_delete_category_with_undo(category_fixture):
    client, user, category = category_fixture

    # Create a food with the category to check if it gets set to null
    with client.application.app_context():
        food = MyFood(
            description="Test Food", user_id=user.id, food_category_id=category.id
        )
        db.session.add(food)
        db.session.commit()
        food_id = food.id

    response = client.post(
        url_for("my_foods.delete_category", category_id=category.id),
        follow_redirects=False,  # Don't follow redirect to check flash message
    )
    assert response.status_code == 302

    with client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        flash_message = flashes[0][1]
        undo_url_match = re.search(r"href='([^']+)'", flash_message)
        assert undo_url_match is not None
        undo_url = undo_url_match.group(1)

    # Follow the undo link
    response = client.get(undo_url, follow_redirects=True)
    assert response.status_code == 200
    assert b"Item restored." in response.data

    with client.application.app_context():
        restored_category = db.session.get(FoodCategory, category.id)
        assert restored_category is not None
        # Check that the food that had the category is now null
        food = db.session.get(MyFood, food_id)
        assert food.food_category_id is None
