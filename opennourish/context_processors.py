from flask_login import current_user
from opennourish.time_utils import get_user_today
from opennourish.utils import get_standard_meal_names_for_user


def utility_processor():
    def get_standard_meal_names():
        return get_standard_meal_names_for_user(current_user)

    def get_current_log_date_str():
        if (
            not hasattr(current_user, "is_authenticated")
            or not current_user.is_authenticated
        ):
            return None
        return get_user_today(current_user.timezone).isoformat()

    return {
        "standard_meal_names": get_standard_meal_names(),
        "current_log_date_str": get_current_log_date_str(),
    }
