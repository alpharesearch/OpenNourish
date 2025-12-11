import pytest
from flask import url_for
from models import db, User, MyFood
from datetime import date, timedelta
import re


@pytest.fixture
def test_user_id(app_with_db):
    with app_with_db.app_context():
        user = User(username="testuser", email="test@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def logged_in_client(client, test_user_id):
    client.post(
        url_for("auth.login"),
        data={"username_or_email": "testuser", "password": "password"},
        follow_redirects=True,
    )
    yield client
    client.get(url_for("auth.logout"))


def test_search_page_buttons_have_correct_log_date(logged_in_client, test_user_id):
    """
    GIVEN a user is logged in
    WHEN they access the search page with a specific log_date
    THEN the 'Add' buttons on the search results should have that same log_date
    in their data-log-date attribute.
    """
    with logged_in_client.application.app_context():
        # Create a food item to search for
        food = MyFood(user_id=test_user_id, description="Test Apple")
        db.session.add(food)
        db.session.commit()
        food_id = food.id

    # A date that is not today
    yesterday = date.today() - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()

    # Access the search page with a search term and the specific log_date
    response = logged_in_client.get(
        url_for(
            "search.search",
            search_term="Test Apple",
            search_my_foods="true",
            target="diary",
            log_date=yesterday_iso,
            meal_name="Lunch",
        )
    )

    assert response.status_code == 200
    response_data = response.data.decode("utf-8")

    # Construct a regex to find the button with all expected data attributes
    # The order of data attributes might vary, so check for each one individually
    # within a general button tag.
    # Escape special characters in food.id for regex
    food_id_escaped = re.escape(str(food_id))

    pattern = (
        r"<button[^>]*"  # Match opening button tag and any attributes
        r'data-food-id=["\']' + food_id_escaped + r'["\'][^>]*'
        r'data-food-type=["\']my_food["\'][^>]*'
        r'data-food-name=["\']Test Apple["\'][^>]*'
        r'data-target=["\']diary["\'][^>]*'
        r'data-log-date=["\']' + re.escape(yesterday_iso) + r'["\'][^>]*'
        r'data-meal-name=["\']Lunch["\'][^>]*'
        r".*?"  # Non-greedy match for anything in between
        r">"  # Closing bracket of the button tag
    )

    match = re.search(
        pattern, response_data, re.DOTALL
    )  # re.DOTALL to match across newlines

    assert (
        match is not None
    ), f"Could not find button with expected attributes. Response: {response_data}"

    # Optional: Further verification of specific attributes from the matched string
    matched_button_html = match.group(0)
    assert f'data-log-date="{yesterday_iso}"' in matched_button_html
    assert 'data-target="diary"' in matched_button_html
    assert 'data-meal-name="Lunch"' in matched_button_html
