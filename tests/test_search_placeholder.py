from models import db, MyFood, User


def test_placeholder_my_food_not_in_search_results(client, auth_client):
    """
    GIVEN a user with a normal MyFood and a placeholder MyFood,
    WHEN the user searches for foods,
    THEN only the normal MyFood should be in the results.
    """
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()

        # Create a normal food
        normal_food = MyFood(
            user_id=user.id, description="Visible Food", is_placeholder=False
        )
        db.session.add(normal_food)

        # Create a placeholder food
        placeholder_food = MyFood(
            user_id=user.id, description="Hidden Placeholder Food", is_placeholder=True
        )
        db.session.add(placeholder_food)
        db.session.commit()

    # Search for "Food" - should find the normal one
    response = auth_client.get(
        "/search/?search_term=Food&search_my_foods=true", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Visible Food" in response.data
    assert b"Hidden Placeholder Food" not in response.data

    # Also test with wildcard search
    response = auth_client.get(
        "/search/?search_term=*&search_my_foods=true", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Visible Food" in response.data
    assert b"Hidden Placeholder Food" not in response.data

    # Also test with no search term (frequent items)
    response = auth_client.get("/search/?search_my_foods=true", follow_redirects=True)
    assert response.status_code == 200
    # This part of the test is tricky because frequent items are based on DailyLog.
    # Since we haven't logged these foods, they won't appear in the "frequent" list.
    # The main goal is to test the search term queries, which we have done.
    # We can add a more complex test for frequent items if needed, but this covers the main logic.
