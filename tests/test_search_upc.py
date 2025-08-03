from models import db, User, MyFood, Food, Recipe, UnifiedPortion, Friendship


def setup_friendship(app, user1, user2):
    with app.app_context():
        friendship = Friendship(
            requester_id=user1.id, receiver_id=user2.id, status="accepted"
        )
        db.session.add(friendship)
        reciprocal_friendship = Friendship(
            requester_id=user2.id, receiver_id=user1.id, status="accepted"
        )
        db.session.add(reciprocal_friendship)
        db.session.commit()


def test_search_by_upc_myfood_and_usda(auth_client, app_with_db):
    """
    GIVEN a user has a MyFood with a specific UPC, and a USDA food exists with the same UPC,
    WHEN the user searches for that UPC,
    THEN both the MyFood item and the USDA food should be returned.
    """
    upc = "012345678901"
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").first()
        my_food = MyFood(
            user_id=user.id, description="My Custom Soda", upc=upc, calories_per_100g=42
        )
        db.session.add(my_food)
        db.session.commit()
        my_food_portion = UnifiedPortion(
            my_food_id=my_food.id,
            amount=1,
            measure_unit_description="can",
            gram_weight=355,
        )
        db.session.add(my_food_portion)
        usda_food = Food(fdc_id=999999, description="Generic Soda", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(
        f"/search?search_term={upc}&search_usda=true&search_my_foods=true",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"My Custom Soda" in response.data
    assert b"Generic Soda" in response.data


def test_search_by_upc_recipe_and_usda(auth_client, app_with_db):
    """
    GIVEN a user has a Recipe with a specific UPC, and a USDA food exists with the same UPC,
    WHEN the user searches for that UPC,
    THEN both the Recipe item and the USDA food should be returned.
    """
    upc = "098765432109"
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").first()
        recipe = Recipe(user_id=user.id, name="My Special Recipe", upc=upc)
        db.session.add(recipe)
        db.session.commit()
        recipe_portion = UnifiedPortion(
            recipe_id=recipe.id,
            amount=1,
            measure_unit_description="serving",
            gram_weight=250,
        )
        db.session.add(recipe_portion)
        usda_food = Food(fdc_id=999998, description="Generic Meal", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(
        f"/search?search_term={upc}&search_usda=true&search_recipes=true",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"My Special Recipe" in response.data
    assert b"Generic Meal" in response.data


def test_search_by_upc_only_usda(auth_client, app_with_db):
    """
    GIVEN only a USDA food exists for a specific UPC,
    WHEN the user searches for that UPC,
    THEN the USDA food should be returned.
    """
    usda_fdc_id = 999997
    upc = "111112222233"
    with app_with_db.app_context():
        usda_food = Food(fdc_id=usda_fdc_id, description="Just a USDA Food", upc=upc)
        db.session.add(usda_food)
        db.session.commit()

    response = auth_client.get(f"/search?search_term={upc}", follow_redirects=True)

    assert response.status_code == 200
    assert b"Just a USDA Food" in response.data


def test_search_by_upc_not_found(auth_client, app_with_db):
    """
    GIVEN no food item exists for a specific UPC,
    WHEN the user searches for that UPC,
    THEN a 'not_found' status should be returned.
    """
    upc = "000000000000"
    response = auth_client.get(f"/search?search_term={upc}", follow_redirects=True)

    assert response.status_code == 200
    assert b'No results found for "000000000000"' in response.data


def test_search_by_upc_friend_food(auth_client, app_with_db):
    """
    GIVEN a user has a friend who has a MyFood with a specific UPC,
    WHEN the user searches for that UPC,
    THEN the friend's MyFood item should be returned.
    """
    upc = "555666777888"
    with app_with_db.app_context():
        user1 = User.query.filter_by(username="testuser").first()
        user2 = User(username="frienduser", email="frienduser@example.com")
        user2.set_password("password")
        db.session.add(user2)
        db.session.commit()

        setup_friendship(app_with_db, user1, user2)

        friend_food = MyFood(user_id=user2.id, description="Friend's Food", upc=upc)
        db.session.add(friend_food)
        db.session.commit()
        friend_food_portion = UnifiedPortion(
            my_food_id=friend_food.id,
            amount=1,
            measure_unit_description="piece",
            gram_weight=50,
        )
        db.session.add(friend_food_portion)
        db.session.commit()

    response = auth_client.get(
        f"/search?search_term={upc}&search_friends=true", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Friend&#39;s Food" in response.data


def test_search_by_upc_friend_recipe(auth_client_with_friendship):
    """
    GIVEN a user has a friend who has a public Recipe with a specific UPC,
    WHEN the user searches for that UPC,
    THEN the friend's Recipe item should be returned.
    """
    client, test_user, friend_user = auth_client_with_friendship
    upc = "444555666777"
    with client.application.app_context():
        friend_recipe = Recipe(
            user_id=friend_user.id,
            name="Friend's Public Recipe",
            upc=upc,
            is_public=True,
        )
        db.session.add(friend_recipe)
        db.session.commit()

    response = client.get(
        f"/search?search_term={upc}&search_friends=true", follow_redirects=True
    )

    assert response.status_code == 200
    assert b"Friend&#39;s Public Recipe" in response.data


def test_search_with_no_term(auth_client, app_with_db):
    """
    GIVEN a user is logged in,
    WHEN they call the search endpoint without a search term,
    THEN the standard search page with frequently used items is shown.
    """
    response = auth_client.get("/search", follow_redirects=True)

    assert response.status_code == 200
    assert b"Frequently Used Items" in response.data
