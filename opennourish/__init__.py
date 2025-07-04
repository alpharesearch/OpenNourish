from flask import Flask
import os
from models import db, User, UserGoal, MyFood, CheckIn, Recipe, DailyLog, Food, Nutrient, FoodNutrient, Portion, MyPortion, RecipePortion, RecipeIngredient, MyMeal, MyMealItem
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config
import click
from faker import Faker
import random
from datetime import date, timedelta

login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_app(config_class=Config):
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'))
    if isinstance(config_class, dict):
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)

    from opennourish.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from opennourish.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    from opennourish.search import search_bp
    app.register_blueprint(search_bp, url_prefix='/search')

    from opennourish.database import database_bp
    app.register_blueprint(database_bp, url_prefix='/database')

    from opennourish.diary import diary_bp
    app.register_blueprint(diary_bp, url_prefix='/')

    from opennourish.goals import bp as goals_bp
    app.register_blueprint(goals_bp, url_prefix='/goals')

    from opennourish.recipes.routes import recipes_bp
    app.register_blueprint(recipes_bp, url_prefix='/recipes')

    from opennourish.settings import settings_bp
    app.register_blueprint(settings_bp)

    from opennourish.tracking import tracking_bp
    app.register_blueprint(tracking_bp, url_prefix='/tracking')

    from opennourish.exercise import exercise_bp
    app.register_blueprint(exercise_bp, url_prefix='/exercise')

    from opennourish.main.routes import main_bp
    app.register_blueprint(main_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.template_filter('nl2br')
    def nl2br_filter(s):
        return s.replace("\n", "<br>")

    @app.cli.command("init-user-db")
    def init_user_db_command():
        """Clears existing user data and creates new tables."""
        with app.app_context():
            db.create_all()
            db.session.commit()
        print("Initialized the user database.")

    @app.cli.command("seed-dev-data")
    @click.argument('count', default=3, type=int)
    def seed_dev_data_command(count):
        """Populates the user database with realistic test data."""
        with app.app_context():
            print("Clearing existing user data...")
            # Delete in reverse dependency order
            db.session.query(DailyLog).delete()
            db.session.query(CheckIn).delete()
            db.session.query(MyMealItem).delete()
            db.session.query(MyMeal).delete()
            db.session.query(RecipeIngredient).delete()
            db.session.query(RecipePortion).delete()
            db.session.query(Recipe).delete()
            db.session.query(MyPortion).delete()
            db.session.query(MyFood).delete()
            db.session.query(UserGoal).delete()
            db.session.query(User).delete()
            db.session.commit()
            print("Cleared existing user data.")

            print("Creating main test user...")
            test_user = User(username='markus')
            test_user.set_password('1')
            db.session.add(test_user)
            db.session.commit()
            print(f"Created main test user: {test_user.username}")

            fake = Faker()

            users_created = 0
            my_foods_created = 0
            check_ins_created = 0
            recipes_created = 0
            my_meals_created = 0
            my_meal_items_created = 0
            daily_logs_created = 0

            # Fetch some FDC IDs from the USDA database for linking
            # This assumes usda_data.db is already populated
            usda_fdc_ids = [f.fdc_id for f in Food.query.all()]

            for i in range(count):
                user = User(username='user'+f"{i}")
                user.set_password('1')
                db.session.add(user)
                db.session.flush()  # To get user.id
                print(f"Created test user{i}: {user.username}")

                # UserGoal
                goal = UserGoal(
                    user_id=user.id,
                    calories=random.randint(1800, 2500),
                    protein=random.randint(100, 200),
                    carbs=random.randint(200, 350),
                    fat=random.randint(50, 100)
                )
                db.session.add(goal)

                # MyFood
                num_my_foods = random.randint(20, 30)
                user_my_foods = []
                for _ in range(num_my_foods):
                    my_food = MyFood(
                        user_id=user.id,
                        description=fake.word().capitalize() + ' ' + fake.word()+ ' My Foods',
                        calories_per_100g=random.uniform(50, 500),
                        protein_per_100g=random.uniform(1, 50),
                        carbs_per_100g=random.uniform(1, 80),
                        fat_per_100g=random.uniform(1, 50)
                    )
                    db.session.add(my_food)
                    user_my_foods.append(my_food)
                my_foods_created += num_my_foods
                db.session.flush()  # To get my_food.id for portions

                # MyPortions for MyFood
                for mf in user_my_foods:
                    if random.random() < 0.5:  # 50% chance to add a custom portion
                        portion = MyPortion(
                            my_food_id=mf.id,
                            description=random.choice(['cup', 'slice', 'serving', 'piece']),
                            gram_weight=random.uniform(30, 200)
                        )
                        db.session.add(portion)

                # CheckIn
                num_check_ins = random.randint(50, 60)
                for j in range(num_check_ins):
                    checkin_date = date.today() - timedelta(days=j)
                    check_in = CheckIn(
                        user_id=user.id,
                        checkin_date=checkin_date,
                        weight_kg=random.uniform(60, 90),
                        body_fat_percentage=random.uniform(10, 30),
                        waist_cm=random.uniform(70, 100)
                    )
                    db.session.add(check_in)
                check_ins_created += num_check_ins

                # Recipes
                num_recipes = random.randint(2, 5)
                user_recipes = []
                for _ in range(num_recipes):
                    recipe = Recipe(
                        user_id=user.id,
                        name=fake.word().capitalize() + ' ' + fake.word() + ' Recipe',
                        instructions=fake.paragraph(nb_sentences=5),
                        servings=random.randint(1, 6)
                    )
                    db.session.add(recipe)
                    user_recipes.append(recipe)
                recipes_created += num_recipes
                db.session.flush()  # To get recipe.id for ingredients and portions

                # RecipeIngredients and RecipePortions
                for r in user_recipes:
                    # Add some ingredients
                    num_ingredients = random.randint(3, 8)
                    for _ in range(num_ingredients):
                        if random.random() < 0.7 and usda_fdc_ids:  # 70% chance for USDA food
                            fdc_id = random.choice(usda_fdc_ids)
                            ingredient = RecipeIngredient(
                                recipe_id=r.id,
                                fdc_id=fdc_id,
                                amount_grams=random.uniform(10, 300)
                            )
                        else:  # Otherwise, use a MyFood
                            if user_my_foods:
                                my_food = random.choice(user_my_foods)
                                ingredient = RecipeIngredient(
                                    recipe_id=r.id,
                                    my_food_id=my_food.id,
                                    amount_grams=random.uniform(10, 300)
                                )
                            else:
                                continue  # Skip if no MyFoods available
                        db.session.add(ingredient)

                    # Add some recipe portions
                    if random.random() < 0.8:  # 80% chance to add custom recipe portions
                        num_recipe_portions = random.randint(1, 3)
                        for _ in range(num_recipe_portions):
                            portion = RecipePortion(
                                recipe_id=r.id,
                                description=random.choice(['bowl', 'plate', 'cup', 'serving']),
                                gram_weight=random.uniform(100, 500)
                            )
                            db.session.add(portion)

                # MyMeals
                num_my_meals = random.randint(5, 10)
                user_my_meals = []
                for _ in range(num_my_meals):
                    meal = MyMeal(
                        user_id=user.id,
                        name=fake.word().capitalize() + ' My Meal'
                    )
                    db.session.add(meal)
                    user_my_meals.append(meal)
                my_meals_created += num_my_meals
                db.session.flush() # To get meal.id for items

                # MyMealItems
                for m in user_my_meals:
                    num_meal_items = random.randint(2, 5)
                    for _ in range(num_meal_items):
                        choice = random.choice(['usda', 'my_food', 'recipe'])
                        fdc_id = None
                        my_food_id = None
                        recipe_id = None

                        if choice == 'usda' and usda_fdc_ids:
                            fdc_id = random.choice(usda_fdc_ids)
                        elif choice == 'my_food' and user_my_foods:
                            my_food_id = random.choice(user_my_foods).id
                        elif choice == 'recipe' and user_recipes:
                            recipe_id = random.choice(user_recipes).id
                        else:
                            continue # Skip if no suitable item found

                        if fdc_id or my_food_id or recipe_id:
                            item = MyMealItem(
                                my_meal_id=m.id,
                                fdc_id=fdc_id,
                                my_food_id=my_food_id,
                                recipe_id=recipe_id,
                                amount_grams=random.uniform(20, 400)
                            )
                            db.session.add(item)
                            my_meal_items_created += 1

                # DailyLog
                num_daily_logs = random.randint(100, 150)
                for j in range(num_daily_logs):
                    log_date = date.today() - timedelta(days=random.randint(0, 60))  # Last 2 months
                    meal_name = random.choice(['Breakfast', 'Snack (morning)', 'Lunch', 'Snack (afternoon)', 'Dinner', 'Snack (evening)'])
                    amount_grams = random.uniform(50, 500)

                    # Randomly link to USDA, MyFood, Recipe, or MyMeal
                    choice = random.choice(['usda', 'my_food', 'recipe', 'my_meal'])
                    fdc_id = None
                    my_food_id = None
                    recipe_id = None
                    my_meal_log_id = None

                    if choice == 'usda' and usda_fdc_ids:
                        fdc_id = random.choice(usda_fdc_ids)
                    elif choice == 'my_food' and user_my_foods:
                        my_food_id = random.choice(user_my_foods).id
                    elif choice == 'recipe' and user_recipes:
                        recipe_id = random.choice(user_recipes).id
                    elif choice == 'my_meal' and user_my_meals:
                        selected_meal = random.choice(user_my_meals)
                        for item in selected_meal.items:
                            log_entry = DailyLog(
                                user_id=user.id,
                                log_date=log_date,
                                meal_name=meal_name,
                                amount_grams=item.amount_grams,
                                fdc_id=item.fdc_id,
                                my_food_id=item.my_food_id,
                                recipe_id=item.recipe_id
                            )
                            db.session.add(log_entry)
                            daily_logs_created += 1
                        continue # Skip the rest of the loop for this iteration
                    else:  # Fallback if no suitable item found
                        if usda_fdc_ids:
                            fdc_id = random.choice(usda_fdc_ids)
                        elif user_my_foods:
                            my_food_id = random.choice(user_my_foods).id
                        elif user_recipes:
                            recipe_id = random.choice(user_recipes).id
                        else:
                            continue  # Skip if no food items can be linked

                    # Only create a single log_entry if not a my_meal type that was expanded
                    if choice != 'my_meal' or not user_my_meals:
                        log_entry = DailyLog(
                            user_id=user.id,
                            log_date=log_date,
                            meal_name=meal_name,
                            amount_grams=amount_grams,
                            fdc_id=fdc_id,
                            my_food_id=my_food_id,
                            recipe_id=recipe_id
                        )
                        db.session.add(log_entry)
                        daily_logs_created += 1

                users_created += 1

            db.session.commit()
            print(f"Database seeded with {users_created} users, {my_foods_created} MyFoods, {check_ins_created} CheckIns, {recipes_created} Recipes, {my_meals_created} MyMeals, {my_meal_items_created} MyMealItems, and {daily_logs_created} Daily Logs.")

    return app
