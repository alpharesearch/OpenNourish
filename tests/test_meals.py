from datetime import date
from models import db, DailyLog, MyMeal, MyMealItem, Food, MyFood, UnifiedPortion


def test_save_meal_from_diary_and_edit(auth_client_with_user):
    """
    Test saving a meal from the diary and redirecting to the edit page.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a DailyLog entry
        daily_log_entry = DailyLog(
            user_id=user.id,
            log_date=date.today(),
            meal_name="Breakfast",
            fdc_id=12345,  # Example FDC ID
            amount_grams=100,
        )
        db.session.add(daily_log_entry)
        db.session.commit()

        # POST to save the meal and edit
        response = client.post(
            "/diary/save_meal_and_edit",
            data={
                "log_date": date.today().isoformat(),
                "meal_name": "Breakfast",
            },
            follow_redirects=False,  # We want to check the redirect
        )
        assert response.status_code == 302  # Check for redirect

        # Assert that new MyMeal and MyMealItem objects are created
        temp_meal_name = (
            f"New Meal from Breakfast - {date.today().strftime('%Y-%m-%d')}"
        )
        saved_meal = MyMeal.query.filter_by(
            user_id=user.id, name=temp_meal_name
        ).first()
        assert saved_meal is not None
        assert len(saved_meal.items) == 1
        assert saved_meal.items[0].fdc_id == 12345
        assert saved_meal.items[0].amount_grams == 100

        # Check redirect location
        assert response.location == f"/my_meals/edit/{saved_meal.id}"

        # Follow redirect
        redirect_response = client.get(response.location)
        assert redirect_response.status_code == 200
        assert bytes(temp_meal_name, "utf-8") in redirect_response.data


def test_my_meals_list_view(auth_client_with_user):
    """
    Test the My Meals list view.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a MyMeal object
        meal = MyMeal(user_id=user.id, name="My Test Meal")
        db.session.add(meal)
        db.session.commit()

        # Perform GET request to /my_meals
        response = client.get("/my_meals")
        assert response.status_code == 200
        assert b"My Test Meal" in response.data


def test_delete_my_meal(auth_client_with_user):
    """
    Test deleting a MyMeal object.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a MyMeal object with an item
        meal = MyMeal(user_id=user.id, name="Meal to Delete")
        db.session.add(meal)
        db.session.commit()  # Commit to get meal.id

        meal_item = MyMealItem(my_meal_id=meal.id, fdc_id=54321, amount_grams=50)
        db.session.add(meal_item)
        db.session.commit()

        meal_id = meal.id
        item_id = meal_item.id

        # POST to delete the meal
        response = client.post(f"/my_meals/{meal_id}/delete", follow_redirects=True)
        assert response.status_code == 200

        # Assert that the meal is anonymized, not deleted
        anonymized_meal = db.session.get(MyMeal, meal_id)
        assert anonymized_meal is not None
        assert anonymized_meal.user_id is None

        # Assert that the meal item still exists
        item = db.session.get(MyMealItem, item_id)
        assert item is not None


def test_delete_meal_item(auth_client_with_user):
    """
    Test deleting an item from a meal.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        meal = MyMeal(user_id=user.id, name="Meal for item deletion")
        db.session.add(meal)
        db.session.commit()

        item = MyMealItem(my_meal_id=meal.id, fdc_id=123, amount_grams=100)
        db.session.add(item)
        db.session.commit()
        meal_id = meal.id
        item_id = item.id

    response = client.post(
        f"/my_meals/{meal_id}/delete_item/{item_id}", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Meal item deleted." in response.data
    assert b"Undo" in response.data

    with client.application.app_context():
        deleted_item = db.session.get(MyMealItem, item_id)
        assert deleted_item is None


def test_update_meal_item_portion(auth_client_with_user):
    """
    Test updating a meal item's quantity and portion.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        my_food = MyFood(
            user_id=user.id, description="Food for meal item", calories_per_100g=100
        )
        db.session.add(my_food)
        db.session.commit()

        portion1 = UnifiedPortion(
            my_food_id=my_food.id, portion_description="g", gram_weight=1.0
        )
        portion2 = UnifiedPortion(
            my_food_id=my_food.id, portion_description="cup", gram_weight=150.0
        )
        db.session.add_all([portion1, portion2])
        db.session.commit()

        meal = MyMeal(user_id=user.id, name="Meal for item update")
        db.session.add(meal)
        db.session.commit()

        item = MyMealItem(
            my_meal_id=meal.id,
            my_food_id=my_food.id,
            amount_grams=100,  # 100g
            portion_id_fk=portion1.id,
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        meal_id = meal.id
        portion2_id = portion2.id

    # Update to 0.5 cups
    response = client.post(
        f"/my_meals/update_item/{item_id}",
        data={"quantity": 0.5, "portion_id": portion2_id},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Meal item updated." in response.data
    assert response.request.path == f"/my_meals/edit/{meal_id}"

    with client.application.app_context():
        updated_item = db.session.get(MyMealItem, item_id)
        assert updated_item.amount_grams == 75.0  # 0.5 * 150.0
        assert updated_item.portion_id_fk == portion2_id


def test_edit_meal_page_shows_item_data(auth_client_with_user):
    """Test that the edit meal page correctly displays data for an item."""
    client, user = auth_client_with_user
    with client.application.app_context():
        # A USDA food item for the meal
        food = Food(fdc_id=12345, description="Test USDA Food")
        db.session.add(food)
        db.session.commit()

        # A portion for that food
        portion = UnifiedPortion(
            fdc_id=food.fdc_id,
            measure_unit_description="g",
            gram_weight=1.0,
            amount=1.0,
        )
        db.session.add(portion)
        db.session.commit()

        meal = MyMeal(user_id=user.id, name="Meal for item edit GET")
        db.session.add(meal)
        db.session.commit()

        item = MyMealItem(
            my_meal_id=meal.id,
            fdc_id=food.fdc_id,
            amount_grams=150.555,
            portion_id_fk=portion.id,
        )
        db.session.add(item)
        db.session.commit()
        meal_id = meal.id

    response = client.get(f"/my_meals/edit/{meal_id}")
    assert response.status_code == 200
    assert b"Edit Meal: Meal for item edit GET" in response.data
    assert b"Test USDA Food" in response.data
    # display_amount = 150.555 / 1.0 = 150.555. The template rounds this to 2 decimal places.
    assert b'value="150.56"' in response.data


def test_create_new_meal(auth_client_with_user):
    """
    Test creating a new meal, which should create a meal and redirect to the edit page.
    """
    client, user = auth_client_with_user

    # GET request to create a new meal
    response = client.get("/my_meals/new")

    # Assert that a new meal was created and we are redirected
    assert response.status_code == 302

    with client.application.app_context():
        # Find the newly created meal
        new_meal = MyMeal.query.filter_by(user_id=user.id, name="New Meal").first()
        assert new_meal is not None

        # Check if the redirect is to the correct edit page
        assert response.location == f"/my_meals/edit/{new_meal.id}"

        # Follow the redirect
        redirect_response = client.get(response.location)
        assert redirect_response.status_code == 200
        assert b"Edit Meal: New Meal" in redirect_response.data


def test_undo_anonymize_my_meal(auth_client_with_user):
    """
    Test that undoing an 'anonymize' action on a MyMeal restores the user_id.
    """
    client, user = auth_client_with_user
    with client.application.app_context():
        # Create a MyMeal object
        meal = MyMeal(user_id=user.id, name="Meal to Anonymize and Undo")
        db.session.add(meal)
        db.session.commit()
        meal_id = meal.id

        # POST to delete (anonymize) the meal
        response = client.post(f"/my_meals/{meal_id}/delete")
        assert response.status_code == 302  # Redirect

        # Check that it's anonymized
        anonymized_meal = db.session.get(MyMeal, meal_id)
        assert anonymized_meal is not None
        assert anonymized_meal.user_id is None

        # Now, call the undo endpoint
        undo_response = client.get("/undo", follow_redirects=True)
        assert undo_response.status_code == 200
        assert b"Item restored." in undo_response.data

        # Check that the meal's user_id is restored
        restored_meal = db.session.get(MyMeal, meal_id)
        assert restored_meal is not None
        assert restored_meal.user_id == user.id
