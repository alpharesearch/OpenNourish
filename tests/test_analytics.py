"""Tests for the advanced analytics features."""

from datetime import date, timedelta
from models import (
    db,
    User,
    UserGoal,
    DailyLog,
    ExerciseLog,
    CheckIn,
    MyFood,
    FoodCategory,
)
from opennourish.tracking.analytics import (
    get_daily_nutrition_data,
    get_macro_distribution_by_meal,
    get_weekly_trends,
    get_food_category_breakdown,
    get_exercise_vs_diet_balance,
    get_nutrient_intake_vs_goals,
    get_body_composition_trends,
)


def test_analytics_route(auth_client):
    """Test that the analytics route loads successfully."""
    response = auth_client.get("/tracking/analytics", follow_redirects=True)
    assert response.status_code == 200


def test_get_daily_nutrition_data(app_with_db):
    """Test retrieving daily nutrition data."""
    with app_with_db.app_context():
        user = User(username="testuser_daily", email="testdaily@example.com")
        db.session.add(user)
        db.session.commit()

        # Add a food to log
        my_food = MyFood(
            user_id=user.id,
            description="Test Food",
            calories_per_100g=100,
            protein_per_100g=10,
            carbs_per_100g=10,
            fat_per_100g=2,
        )
        db.session.add(my_food)
        db.session.commit()

        # Log for today and yesterday
        today = date.today()
        yesterday = today - timedelta(days=1)

        log1 = DailyLog(
            user_id=user.id, log_date=today, my_food_id=my_food.id, amount_grams=200
        )
        log2 = DailyLog(
            user_id=user.id, log_date=yesterday, my_food_id=my_food.id, amount_grams=100
        )
        db.session.add_all([log1, log2])
        db.session.commit()

        data = get_daily_nutrition_data(user.id, days=7)

        assert len(data) >= 2
        # Check today's totals (200g * 100cal/100g = 200cal)
        today_data = next(d for d in data if d["date"] == today)
        assert today_data["calories"] == 200.0
        assert today_data["protein"] == 20.0

        # Check yesterday's totals (100g * 100cal/100g = 100cal)
        yesterday_data = next(d for d in data if d["date"] == yesterday)
        assert yesterday_data["calories"] == 100.0


def test_get_macro_distribution_by_meal(app_with_db):
    """Test macro distribution by meal."""
    with app_with_db.app_context():
        user = User(username="testuser_meals", email="testmeals@example.com")
        db.session.add(user)
        db.session.commit()

        my_food = MyFood(
            user_id=user.id,
            description="Macro Food",
            calories_per_100g=400,  # 10g P, 40g C, 22.2g F roughly
            protein_per_100g=25,  # 100 cal
            carbs_per_100g=50,  # 200 cal
            fat_per_100g=11.1,  # ~100 cal
        )
        db.session.add(my_food)
        db.session.commit()

        today = date.today()
        log = DailyLog(
            user_id=user.id,
            log_date=today,
            meal_name="Breakfast",
            my_food_id=my_food.id,
            amount_grams=100,
        )
        db.session.add(log)
        db.session.commit()

        data = get_macro_distribution_by_meal(user.id)

        assert "Breakfast" in data
        # 100 cal protein / 400 cal total = 25%
        assert data["Breakfast"]["protein"] == 25.0
        assert data["Breakfast"]["carbs"] == 50.0
        # 11.1 * 9 = 99.9. 99.9 / 400 = 24.975 -> 25.0
        assert data["Breakfast"]["fat"] >= 24.0


def test_get_weekly_trends(app_with_db):
    """Test weekly trends calculation."""
    with app_with_db.app_context():
        user = User(username="testuser_weekly", email="testweekly@example.com")
        db.session.add(user)
        db.session.commit()

        my_food = MyFood(user_id=user.id, description="Food", calories_per_100g=100)
        db.session.add(my_food)
        db.session.commit()

        today = date.today()
        # Log something today
        db.session.add(
            DailyLog(
                user_id=user.id, log_date=today, my_food_id=my_food.id, amount_grams=100
            )
        )
        # Log something 8 days ago (likely a different week)
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=today - timedelta(days=8),
                my_food_id=my_food.id,
                amount_grams=200,
            )
        )
        db.session.commit()

        trends = get_weekly_trends(user.id)
        assert len(trends) >= 1


def test_get_food_category_breakdown(app_with_db):
    """Test breakdown of calories by food category."""
    with app_with_db.app_context():
        user = User(username="testuser_cat", email="testcat@example.com")
        db.session.add(user)

        cat1 = FoodCategory(description="Fruits")
        cat2 = FoodCategory(description="Vegetables")
        db.session.add_all([cat1, cat2])
        db.session.commit()

        food1 = MyFood(
            user_id=user.id,
            description="Apple",
            calories_per_100g=50,
            food_category_id=cat1.id,
        )
        food2 = MyFood(
            user_id=user.id,
            description="Carrot",
            calories_per_100g=40,
            food_category_id=cat2.id,
        )
        db.session.add_all([food1, food2])
        db.session.commit()

        today = date.today()
        db.session.add(
            DailyLog(
                user_id=user.id, log_date=today, my_food_id=food1.id, amount_grams=100
            )
        )
        db.session.add(
            DailyLog(
                user_id=user.id, log_date=today, my_food_id=food2.id, amount_grams=100
            )
        )
        db.session.commit()

        breakdown = get_food_category_breakdown(user.id)

        assert any(b["category"] == "Fruits" for b in breakdown)
        assert any(b["category"] == "Vegetables" for b in breakdown)

        fruits = next(b for b in breakdown if b["category"] == "Fruits")
        next(b for b in breakdown if b["category"] == "Vegetables")

        # Apple: 50 cal, Carrot: 40 cal. Total: 90.
        # Apple pct: 50/90 = 55.6%
        assert fruits["percentage"] == round(50 / 90 * 100, 1)


def test_get_exercise_vs_diet_balance(app_with_db):
    """Test net calorie balance between diet and exercise."""
    with app_with_db.app_context():
        user = User(username="testuser_balance", email="testbalance@example.com")
        db.session.add(user)
        db.session.commit()

        my_food = MyFood(user_id=user.id, description="Food", calories_per_100g=500)
        db.session.add(my_food)
        db.session.commit()  # Commit to get ID

        today = date.today()
        # Intake: 500 cal
        db.session.add(
            DailyLog(
                user_id=user.id, log_date=today, my_food_id=my_food.id, amount_grams=100
            )
        )
        # Burned: 300 cal
        db.session.add(
            ExerciseLog(
                user_id=user.id,
                log_date=today,
                duration_minutes=30,
                calories_burned=300,
            )
        )
        db.session.commit()

        balance = get_exercise_vs_diet_balance(user.id)

        today_balance = next(b for b in balance if b["date"] == today)
        assert today_balance["calories_in"] == 500.0
        assert today_balance["calories_out"] == 300
        assert today_balance["net"] == 200.0


def test_get_nutrient_intake_vs_goals(app_with_db):
    """Test intake vs goals comparison."""
    with app_with_db.app_context():
        user = User(username="testuser_goals", email="testgoals@example.com")
        db.session.add(user)
        db.session.commit()

        goal = UserGoal(user_id=user.id, calories=2000, protein=100, carbs=200, fat=60)
        db.session.add(goal)

        my_food = MyFood(
            user_id=user.id,
            description="Food",
            calories_per_100g=100,
            protein_per_100g=10,
            carbs_per_100g=10,
            fat_per_100g=2,
        )
        db.session.add(my_food)
        db.session.commit()  # Commit to get ID

        today = date.today()
        db.session.add(
            DailyLog(
                user_id=user.id, log_date=today, my_food_id=my_food.id, amount_grams=500
            )
        )
        db.session.commit()

        data = get_nutrient_intake_vs_goals(user.id)

        assert data["calories"]["intake"] == 500.0
        assert data["calories"]["goal"] == 2000
        assert "deviation" in data["calories"]


def test_get_body_composition_trends(app_with_db):
    """Test body composition trends."""
    with app_with_db.app_context():
        user = User(username="testuser_body", email="testbody@example.com")
        db.session.add(user)
        db.session.commit()

        today = date.today()
        db.session.add(
            CheckIn(
                user_id=user.id, checkin_date=today - timedelta(days=7), weight_kg=80.0
            )
        )
        db.session.add(CheckIn(user_id=user.id, checkin_date=today, weight_kg=79.0))
        db.session.commit()

        trends = get_body_composition_trends(user.id)

        assert len(trends) == 2
        assert trends[0]["weight_kg"] == 80.0
        assert trends[1]["weight_kg"] == 79.0


def test_analytics_features_on_dashboard(client, app_with_db):
    """Test that the analytics page renders data points correctly."""
    with app_with_db.app_context():
        user = User(username="renderuser", email="render@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        # Setup goals
        goal = UserGoal(user_id=user_id, calories=2000, protein=100, carbs=200, fat=60)
        db.session.add(goal)

        # Setup categorized food
        cat = FoodCategory(description="Superfoods")
        db.session.add(cat)
        db.session.commit()

        food = MyFood(
            user_id=user.id,
            description="Blueberries",
            calories_per_100g=57,
            food_category_id=cat.id,
        )
        db.session.add(food)
        db.session.commit()

        # Setup logs
        today = date.today()
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=today,
                meal_name="Breakfast",
                my_food_id=food.id,
                amount_grams=100,
            )
        )
        db.session.add(
            ExerciseLog(
                user_id=user.id,
                log_date=today,
                duration_minutes=30,
                calories_burned=200,
            )
        )
        db.session.add(
            CheckIn(
                user_id=user.id,
                checkin_date=today,
                weight_kg=75.0,
                waist_cm=85.0,
                body_fat_percentage=20.0,
            )
        )
        db.session.commit()

    # Log in
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id
        sess["_fresh"] = True

    # Use explicit date to avoid timezone mismatches between test environment and app logic
    response = client.get(f'/{today.isoformat()}', follow_redirects=True)
    assert response.status_code == 200
    
    # Check for specific rendered content
    assert b"Superfoods" in response.data  # Category breakdown table/chart
    assert b"Breakfast" in response.data  # Macro distribution

    # Check if chart canvases are present
    assert b"dailyNutritionChart" in response.data
    assert b"macroDistributionChart" in response.data
    assert b"weeklyTrendsChart" in response.data
    assert b"categoryBreakdownChart" in response.data
    assert b"exerciseBalanceChart" in response.data
    assert b"bodyCompositionChart" in response.data


def test_dashboard_analytics_empty(client, auth_client):
    """Test that the analytics page renders correctly with no data."""
    response = auth_client.get("/", follow_redirects=True)
    assert response.status_code == 200
    # Dashboard has default content, but check for empty state messages for analytics
    assert b"No nutrition data available" in response.data
    assert b"No meal data available" in response.data
    assert b"No weekly data available" in response.data
    assert b"No category data available" in response.data
    assert b"No balance data available" in response.data
