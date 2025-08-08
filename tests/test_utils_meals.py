from opennourish.utils import get_standard_meal_names_for_user
from models import User


def test_get_standard_meal_names_for_user():
    # Test case for a user with 3 meals per day
    user_3_meals = User(meals_per_day=3)
    assert get_standard_meal_names_for_user(user_3_meals) == [
        "Breakfast",
        "Lunch",
        "Dinner",
    ]

    # Test case for a user with 4 meals per day
    user_4_meals = User(meals_per_day=4)
    assert get_standard_meal_names_for_user(user_4_meals) == [
        "Water",
        "Breakfast",
        "Lunch",
        "Dinner",
    ]

    # Test case for a user with 6 meals per day
    user_6_meals = User(meals_per_day=6)
    assert get_standard_meal_names_for_user(user_6_meals) == [
        "Breakfast",
        "Snack (morning)",
        "Lunch",
        "Snack (afternoon)",
        "Dinner",
        "Snack (evening)",
    ]

    # Test case for a user with 7 meals per day
    user_7_meals = User(meals_per_day=7)
    assert get_standard_meal_names_for_user(user_7_meals) == [
        "Water",
        "Breakfast",
        "Snack (morning)",
        "Lunch",
        "Snack (afternoon)",
        "Dinner",
        "Snack (evening)",
    ]

    # Test case for an anonymous user (or user with no preference)
    anonymous_user = User()
    assert get_standard_meal_names_for_user(anonymous_user) == [
        "Breakfast",
        "Snack (morning)",
        "Lunch",
        "Snack (afternoon)",
        "Dinner",
        "Snack (evening)",
    ]
