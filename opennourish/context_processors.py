from flask_login import current_user
from opennourish.time_utils import get_user_today
from constants import ALL_MEAL_TYPES


def inject_global_vars():
    if hasattr(current_user, "is_authenticated") and current_user.is_authenticated:
        user_today_str = get_user_today(current_user.timezone).isoformat()
        standard_meal_names = [
            meal
            for meal in ALL_MEAL_TYPES
            if getattr(
                current_user,
                f"show_{meal.lower().replace(' ', '_').replace('(', '').replace(')', '')}_meal",
                False,
            )
        ]
        if not standard_meal_names:
            standard_meal_names = ["Breakfast", "Lunch", "Dinner"]  # Default
        return dict(
            standard_meal_names=standard_meal_names,
            user_today_str=user_today_str,
            user_timezone=current_user.timezone,
        )
    return dict(
        standard_meal_names=["Breakfast", "Lunch", "Dinner"],
        user_today_str=None,
        user_timezone="UTC",
    )
