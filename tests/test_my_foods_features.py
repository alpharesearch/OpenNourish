from models import db, User, MyFood, Food, FoodNutrient, Nutrient, UnifiedPortion


def test_create_my_food(auth_client):
    """
    Tests creating a new custom food based on a user-defined portion.
    The user provides nutrition for a serving, and it's scaled to 100g.
    """
    # User provides nutrition facts for a 50g serving
    food_data = {
        "description": "Homemade Granola",
        # Nutrition for a 50g serving
        "calories_per_100g": 225.0,  # In the form, this field is now just 'Calories'
        "protein_per_100g": 5.0,  # 'Protein (g)'
        "carbs_per_100g": 30.0,  # 'Carbohydrates (g)'
        "fat_per_100g": 10.0,  # 'Fat (g)'
        # Portion form data
        "amount": 1,
        "measure_unit_description": "cup",
        "portion_description": "",
        "modifier": "",
        "gram_weight": 50.0,  # The gram weight of the '1 cup' serving
    }
    response = auth_client.post("/my_foods/new", data=food_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"Custom food added successfully!" in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood.query.filter_by(
            user_id=user.id, description="Homemade Granola"
        ).first()
        assert my_food is not None
        # Verify that the values have been correctly scaled to 100g (doubled in this case)
        assert my_food.calories_per_100g == 450.0
        assert my_food.protein_per_100g == 10.0
        assert my_food.carbs_per_100g == 60.0
        assert my_food.fat_per_100g == 20.0

        # Verify the user-defined portion was created
        user_portion = UnifiedPortion.query.filter_by(
            my_food_id=my_food.id, gram_weight=50.0
        ).first()
        assert user_portion is not None
        assert user_portion.measure_unit_description == "cup"

        # Verify the automatic 1g portion was also created
        gram_portion = UnifiedPortion.query.filter_by(
            my_food_id=my_food.id, gram_weight=1.0
        ).first()
        assert gram_portion is not None


def test_copy_usda_food_from_search(auth_client):
    """
    Tests copying a USDA food to My Foods from the search/add_item endpoint.
    """
    with auth_client.application.app_context():
        # Create a sample USDA Food and Nutrients
        test_food = Food(fdc_id=12345, description="USDA Test Apple")
        db.session.add(test_food)

        # Nutrient IDs: calories=1008, protein=1003, carbs=1005, fat=1004
        db.session.add(Nutrient(id=1008, name="Energy", unit_name="kcal"))
        db.session.add(Nutrient(id=1003, name="Protein", unit_name="g"))
        db.session.add(
            Nutrient(id=1005, name="Carbohydrate, by difference", unit_name="g")
        )
        db.session.add(Nutrient(id=1004, name="Total lipid (fat)", unit_name="g"))

        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1008, amount=52.0))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1003, amount=0.3))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1005, amount=13.8))
        db.session.add(FoodNutrient(fdc_id=12345, nutrient_id=1004, amount=0.2))

        # Add the mandatory 1-gram portion for the test
        gram_portion = UnifiedPortion(
            fdc_id=12345, portion_description="gram", gram_weight=1.0
        )
        db.session.add(gram_portion)
        db.session.commit()
        fdc_id = test_food.fdc_id
        gram_portion_id = gram_portion.id

    response = auth_client.post(
        "/search/add_item",
        data={
            "food_id": fdc_id,
            "food_type": "usda",
            "target": "my_foods",
            "amount": 100,  # Amount is required by the form
            "portion_id": gram_portion_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Using response.data to check for flash messages is more reliable in tests
    assert b"USDA Test Apple has been added to your foods." in response.data

    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood.query.filter_by(
            user_id=user.id, description="USDA Test Apple"
        ).first()
        assert my_food is not None
        assert my_food.calories_per_100g == 52.0
        assert my_food.protein_per_100g == 0.3
        assert my_food.carbs_per_100g == 13.8
        assert my_food.fat_per_100g == 0.2


def test_copy_usda_food_direct(auth_client):
    """
    Tests copying a USDA food to My Foods using the dedicated copy route.
    """
    with auth_client.application.app_context():
        # Setup USDA food with nutrients and portions
        usda_food = Food(fdc_id=54321, description="USDA Direct Copy")
        db.session.add(usda_food)
        db.session.add(Nutrient(id=1008, name="Energy", unit_name="kcal"))
        db.session.add(FoodNutrient(fdc_id=54321, nutrient_id=1008, amount=150.0))
        db.session.add(
            UnifiedPortion(fdc_id=54321, portion_description="slice", gram_weight=30.0)
        )
        db.session.commit()

    response = auth_client.post("/my_foods/copy_usda", data={"fdc_id": 54321})
    assert response.status_code == 302  # Redirect

    with auth_client.session_transaction() as session:
        flashes = session.get("_flashes", [])
        assert len(flashes) > 0
        assert flashes[0][0] == "success"
        assert (
            flashes[0][1] == "Successfully created 'USDA Direct Copy' from USDA data."
        )

    with auth_client.application.app_context():
        my_food = MyFood.query.filter_by(description="USDA Direct Copy").first()
        assert my_food is not None
        assert my_food.calories_per_100g == 150.0
        assert len(my_food.portions) == 1
        assert my_food.portions[0].portion_description == "slice"


def test_update_my_food_portion(auth_client):
    """
    Tests updating an existing portion on a MyFood item.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(user_id=user.id, description="Food with Portions")
        db.session.add(my_food)
        db.session.commit()
        portion = UnifiedPortion(
            my_food_id=my_food.id, portion_description="piece", gram_weight=25.0
        )
        db.session.add(portion)
        db.session.commit()
        portion_id = portion.id

    update_data = {
        "portion_description": "large piece",
        "gram_weight": 40.0,
        "amount": 1.0,
        "measure_unit_description": "unit",
    }
    response = auth_client.post(
        f"/my_foods/portion/{portion_id}/update",
        data=update_data,
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Portion updated successfully!" in response.data

    with auth_client.application.app_context():
        updated_portion = db.session.get(UnifiedPortion, portion_id)
        assert updated_portion.portion_description == "large piece"
        assert updated_portion.gram_weight == 40.0


def test_add_my_food_portion(auth_client):
    """
    Tests adding a new portion to an existing MyFood item.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(user_id=user.id, description="Food for Portions")
        db.session.add(my_food)
        db.session.commit()
        food_id = my_food.id

    portion_data = {
        "portion_description": "new portion",
        "amount": 0.5,
        "measure_unit_description": "cup",
        "modifier": "chopped",
        "gram_weight": 75.0,
    }
    response = auth_client.post(
        f"/my_foods/{food_id}/add_portion", data=portion_data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Portion added successfully!" in response.data

    with auth_client.application.app_context():
        added_portion = UnifiedPortion.query.filter_by(
            my_food_id=food_id, portion_description="new portion"
        ).first()
        assert added_portion is not None
        assert added_portion.gram_weight == 75.0


def test_delete_my_food_portion(auth_client):
    """
    Tests deleting a portion from a MyFood item.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(user_id=user.id, description="Food to Delete Portion From")
        db.session.add(my_food)
        db.session.commit()
        portion_to_delete = UnifiedPortion(
            my_food_id=my_food.id,
            portion_description="portion to delete",
            gram_weight=10.0,
        )
        db.session.add(portion_to_delete)
        db.session.commit()
        portion_id = portion_to_delete.id

    response = auth_client.post(
        f"/my_foods/portion/{portion_id}/delete", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Portion deleted." in response.data

    with auth_client.application.app_context():
        deleted_portion = db.session.get(UnifiedPortion, portion_id)
        assert deleted_portion is None


def test_edit_my_food(auth_client):
    """
    Tests editing an existing custom food.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        initial_food = MyFood(
            user_id=user.id,
            description="Old Food",
            calories_per_100g=100.0,
            protein_per_100g=1.0,
            carbs_per_100g=10.0,
            fat_per_100g=5.0,
        )
        db.session.add(initial_food)
        db.session.commit()  # Commit to get the food ID

        # Add a default portion, as would happen in the real app
        default_portion = UnifiedPortion(
            my_food_id=initial_food.id,
            gram_weight=1.0,
            portion_description="g",
            seq_num=1,
        )
        db.session.add(default_portion)
        db.session.commit()
        food_id = initial_food.id
        portion_id = default_portion.id

    updated_food_data = {
        "description": "Updated Food",
        "calories_per_100g": 150.0,
        "protein_per_100g": 2.0,
        "carbs_per_100g": 15.0,
        "fat_per_100g": 7.0,
        "selected_portion_id": portion_id,  # Add portion to submission
    }
    response = auth_client.post(
        f"/my_foods/{food_id}/edit", data=updated_food_data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Custom food updated successfully." in response.data

    with auth_client.application.app_context():
        updated_food = db.session.get(MyFood, food_id)
        assert updated_food is not None
        assert updated_food.description == "Updated Food"
        assert updated_food.calories_per_100g == 150.0


def test_edit_my_food_with_portion_scaling(auth_client):
    """
    Tests that editing nutrients based on a specific portion correctly
    scales the values back to the 100g standard for storage.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        # 1. Create a food with known 100g values
        my_food = MyFood(
            user_id=user.id,
            description="Test Scaling Food",
            calories_per_100g=400.0,
            protein_per_100g=20.0,
        )
        db.session.add(my_food)
        db.session.commit()

        # 2. Create a 1g portion and a 50g portion
        portion_1g = UnifiedPortion(
            my_food_id=my_food.id, gram_weight=1.0, portion_description="g", seq_num=1
        )
        portion_50g = UnifiedPortion(
            my_food_id=my_food.id,
            gram_weight=50.0,
            portion_description="serving",
            seq_num=2,
        )
        db.session.add_all([portion_1g, portion_50g])
        db.session.commit()
        food_id = my_food.id
        portion_50g_id = portion_50g.id

    # 3. The user sees values for the 50g portion (200 kcal, 10g protein)
    #    and decides to change them to 250 kcal and 12.5g protein for that same 50g portion.
    edit_data = {
        "description": "Updated Scaling Food",
        "calories_per_100g": 250.0,  # User is submitting 250 for the 50g portion
        "protein_per_100g": 12.5,  # User is submitting 12.5 for the 50g portion
        "selected_portion_id": portion_50g_id,  # Crucially, this is the portion context
    }

    # 4. Post the changes
    response = auth_client.post(
        f"/my_foods/{food_id}/edit", data=edit_data, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Custom food updated successfully." in response.data

    # 5. Verify the data was scaled back to 100g correctly in the database
    with auth_client.application.app_context():
        updated_food = db.session.get(MyFood, food_id)
        assert updated_food is not None
        # The 250 kcal for 50g should be 500 kcal per 100g
        assert updated_food.calories_per_100g == 500.0
        # The 12.5g protein for 50g should be 25g protein per 100g
        assert updated_food.protein_per_100g == 25.0


def test_delete_my_food(auth_client):
    """
    Tests deleting a custom food.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        food_to_delete = MyFood(
            user_id=user.id,
            description="Food to Delete",
            calories_per_100g=200.0,
            protein_per_100g=5.0,
            carbs_per_100g=20.0,
            fat_per_100g=10.0,
        )
        db.session.add(food_to_delete)
        db.session.commit()
        food_id = food_to_delete.id

    response = auth_client.post(f"/my_foods/{food_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Food deleted successfully!" in response.data

    with auth_client.application.app_context():
        deleted_food = db.session.get(MyFood, food_id)
        assert deleted_food.user_id is None


def test_user_cannot_delete_another_users_food(client):
    """
    Tests that a user cannot delete a food item belonging to another user.
    """
    with client.application.app_context():
        # Create two users
        user_a = User(username="user_a", email="a@a.com")
        user_a.set_password("password_a")
        user_b = User(username="user_b", email="b@b.com")
        user_b.set_password("password_b")
        db.session.add_all([user_a, user_b])
        db.session.commit()

        # User A creates a food item
        food_a = MyFood(user_id=user_a.id, description="Food A", calories_per_100g=100)
        db.session.add(food_a)
        db.session.commit()
        food_a_id = food_a.id

    # Log in as User B
    login_response = client.post(
        "/auth/login",
        data={"username_or_email": "user_b", "password": "password_b"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert b"Dashboard" in login_response.data  # Confirm login success

    # User B attempts to delete User A's food
    response = client.post(
        f"/my_foods/{food_a_id}/delete", follow_redirects=False
    )  # Test the direct response

    # Assert that the action is not found
    assert response.status_code == 404

    # Assert that the food item still exists in the database
    with client.application.app_context():
        food_still_exists = db.session.get(MyFood, food_a_id)
        assert food_still_exists is not None


def test_edit_my_food_with_invalid_data_type(auth_client):
    """
    Tests that submitting a non-numeric value to a numeric field during
    an edit fails validation gracefully.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        initial_food = MyFood(
            user_id=user.id, description="Test Food", calories_per_100g=100.0
        )
        db.session.add(initial_food)
        db.session.commit()
        food_id = initial_food.id

    # Attempt to update with a non-numeric value for calories
    invalid_data = {
        "description": "Updated Food Name",
        "calories_per_100g": "not-a-number",
    }
    response = auth_client.post(
        f"/my_foods/{food_id}/edit", data=invalid_data, follow_redirects=True
    )

    # The form should fail validation and re-render the page
    assert response.status_code == 200
    # Check for the standard WTForms error message for an invalid float
    assert b"Not a valid float value." in response.data
    # Check that the success message is NOT present
    assert b"Food updated successfully!" not in response.data

    # Verify that the original food data was not changed in the database
    with auth_client.application.app_context():
        food_in_db = db.session.get(MyFood, food_id)
        assert food_in_db.description == "Test Food"
        assert food_in_db.calories_per_100g == 100.0


def test_reorder_my_food_portions(auth_client):
    """
    Tests reordering portions for a MyFood item.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(user_id=user.id, description="Food for Reordering")
        db.session.add(my_food)
        db.session.commit()

        p1 = UnifiedPortion(
            my_food_id=my_food.id, portion_description="A", gram_weight=10.0, seq_num=1
        )
        p2 = UnifiedPortion(
            my_food_id=my_food.id, portion_description="B", gram_weight=20.0, seq_num=2
        )
        p3 = UnifiedPortion(
            my_food_id=my_food.id, portion_description="C", gram_weight=30.0, seq_num=3
        )
        db.session.add_all([p1, p2, p3])
        db.session.commit()
        p1_id, p2_id, _ = p1.id, p2.id, p3.id

    # Move p2 up
    auth_client.post(f"/my_foods/portion/{p2_id}/move_up")
    with auth_client.application.app_context():
        p1_new = db.session.get(UnifiedPortion, p1_id)
        p2_new = db.session.get(UnifiedPortion, p2_id)
        assert p1_new.seq_num == 2
        assert p2_new.seq_num == 1

    # Move p2 down (back to original position)
    auth_client.post(f"/my_foods/portion/{p2_id}/move_down")
    with auth_client.application.app_context():
        p1_new = db.session.get(UnifiedPortion, p1_id)
        p2_new = db.session.get(UnifiedPortion, p2_id)
        assert p1_new.seq_num == 1
        assert p2_new.seq_num == 2
