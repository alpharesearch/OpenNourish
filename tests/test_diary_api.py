from models import db, User, UserGoal, DailyLog, MyFood
from datetime import date
from flask import url_for


def test_get_remaining_calories(auth_client):
    with auth_client.application.app_context():
        user = User.query.filter_by(username="testuser").first()
        user_goal = UserGoal(user_id=user.id, calories=2000)
        db.session.add(user_goal)

        food1 = MyFood(user_id=user.id, description="Apple", calories_per_100g=52)
        db.session.add(food1)
        db.session.commit()

        log_date = date(2025, 8, 31)
        log1 = DailyLog(
            user_id=user.id,
            my_food_id=food1.id,
            amount_grams=100,
            log_date=log_date,
            meal_name="Breakfast",
        )  # 52 kcal
        db.session.add(log1)
        db.session.commit()

        url = url_for("diary.get_remaining_calories", log_date_str=log_date.isoformat())
        response = auth_client.get(url)

        assert response.status_code == 200
        data = response.get_json()
        assert data["remaining_calories"] == 1948
        assert data["goal_calories"] == 2000
        assert data["calories_consumed"] == 52
        assert data["calories_burned"] == 0
