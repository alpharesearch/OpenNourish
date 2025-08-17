from flask import Flask, current_app
from sqlalchemy import text
import os
from models import (
    db,
    User,
    UserGoal,
    MyFood,
    CheckIn,
    Recipe,
    DailyLog,
    Food,
    Nutrient,
    FoodNutrient,
    UnifiedPortion,
    RecipeIngredient,
    MyMeal,
    MyMealItem,
    ExerciseActivity,
    ExerciseLog,
    Friendship,
    FoodCategory,
)
from sqlalchemy.orm import joinedload
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mailing import Mail
from config import Config
import click
from faker import Faker
import random
from datetime import date, timedelta
import csv
from werkzeug.middleware.proxy_fix import ProxyFix
from opennourish.time_utils import register_template_filters
from constants import MEAL_CONFIG, DEFAULT_MEAL_NAMES

login_manager = LoginManager()
login_manager.login_view = "auth.login"
mail = Mail()


def create_app(config_class=Config):
    app = Flask(
        __name__,
        instance_path=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "instance"
        ),
        instance_relative_config=True,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
    )
    if isinstance(config_class, dict):
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    # Force MAIL_SUPPRESS_SEND to True if in testing mode
    if app.testing:
        app.config["MAIL_SUPPRESS_SEND"] = True

    # Apply ProxyFix middleware to handle headers from the reverse proxy
    # This is crucial for generating correct external URLs (e.g., in emails)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)

    # Load email settings from DB after app and db are initialized
    with app.app_context():
        from config import get_setting_from_db

        mail_config_source = get_setting_from_db(
            app, "MAIL_CONFIG_SOURCE", default="environment"
        )
        app.config["MAIL_CONFIG_SOURCE"] = mail_config_source

        if mail_config_source == "database":
            # Load all settings from the database, with safe defaults
            app.config["MAIL_SERVER"] = get_setting_from_db(
                app, "MAIL_SERVER", default=""
            )
            mail_port_from_db = get_setting_from_db(app, "MAIL_PORT", default=587)
            app.config["MAIL_PORT"] = (
                int(mail_port_from_db) if mail_port_from_db else 587
            )
            app.config["MAIL_USE_TLS"] = (
                get_setting_from_db(app, "MAIL_USE_TLS", default="False").lower()
                == "true"
            )
            app.config["MAIL_USE_SSL"] = (
                get_setting_from_db(app, "MAIL_USE_SSL", default="False").lower()
                == "true"
            )
            app.config["MAIL_USERNAME"] = get_setting_from_db(
                app, "MAIL_USERNAME", default=""
            )
            app.config["MAIL_PASSWORD"] = get_setting_from_db(
                app, "MAIL_PASSWORD", decrypt=True, default=""
            )
            app.config["MAIL_FROM"] = (
                get_setting_from_db(app, "MAIL_FROM", default="no-reply@example.com")
                or "no-reply@example.com"
            )
            app.config["MAIL_SUPPRESS_SEND"] = (
                get_setting_from_db(app, "MAIL_SUPPRESS_SEND", default="True").lower()
                == "true"
            )
            app.config["ENABLE_PASSWORD_RESET"] = (
                get_setting_from_db(
                    app, "ENABLE_PASSWORD_RESET", default="False"
                ).lower()
                == "true"
            )
            app.config["ENABLE_EMAIL_VERIFICATION"] = (
                get_setting_from_db(
                    app, "ENABLE_EMAIL_VERIFICATION", default="False"
                ).lower()
                == "true"
            )
        else:  # Default to environment variables
            app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "")
            app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
            app.config["MAIL_USE_TLS"] = (
                os.getenv("MAIL_USE_TLS", "False").lower() == "true"
            )
            app.config["MAIL_USE_SSL"] = (
                os.getenv("MAIL_USE_SSL", "False").lower() == "true"
            )
            app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
            app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
            app.config["MAIL_FROM"] = (
                os.getenv("MAIL_FROM", "no-reply@example.com") or "no-reply@example.com"
            )
            app.config["MAIL_SUPPRESS_SEND"] = (
                os.getenv("MAIL_SUPPRESS_SEND", "True").lower() == "true"
            )
            app.config["ENABLE_PASSWORD_RESET"] = (
                os.getenv("ENABLE_PASSWORD_RESET", "False").lower() == "true"
            )
            app.config["ENABLE_EMAIL_VERIFICATION"] = (
                os.getenv("ENABLE_EMAIL_VERIFICATION", "False").lower() == "true"
            )

        # Set USE_CREDENTIALS based on whether username and password are provided
        if app.config.get("MAIL_USERNAME") and app.config.get("MAIL_PASSWORD"):
            app.config["USE_CREDENTIALS"] = True
        else:
            app.config["USE_CREDENTIALS"] = False

        # Initialize Flask-Mailing here, after config is loaded
        mail.init_app(app)

    # Enable the Jinja2 'do' extension
    app.jinja_env.add_extension("jinja2.ext.do")

    from opennourish.context_processors import utility_processor

    app.context_processor(utility_processor)

    from opennourish.auth import auth_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")

    from opennourish.onboarding import onboarding_bp

    app.register_blueprint(onboarding_bp, url_prefix="/onboarding")

    from opennourish.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from opennourish.my_foods.routes import my_foods_bp

    app.register_blueprint(my_foods_bp, url_prefix="/my_foods")

    from opennourish.diary import diary_bp

    app.register_blueprint(diary_bp, url_prefix="/")

    from opennourish.goals import bp as goals_bp

    app.register_blueprint(goals_bp, url_prefix="/goals")

    from opennourish.recipes.routes import recipes_bp

    app.register_blueprint(recipes_bp, url_prefix="/recipes")

    from opennourish.settings import settings_bp

    app.register_blueprint(settings_bp)

    from opennourish.tracking import tracking_bp

    app.register_blueprint(tracking_bp, url_prefix="/tracking")

    from opennourish.exercise import exercise_bp

    app.register_blueprint(exercise_bp, url_prefix="/exercise")

    from opennourish.main.routes import main_bp

    app.register_blueprint(main_bp)

    from opennourish.search import search_bp

    app.register_blueprint(search_bp, url_prefix="/search")

    from opennourish.friends import friends_bp

    app.register_blueprint(friends_bp, url_prefix="/friends")

    from opennourish.profile import profile_bp

    app.register_blueprint(profile_bp, url_prefix="/user")

    from opennourish.admin import admin_bp

    app.register_blueprint(admin_bp)

    from opennourish.usda_admin import usda_admin_bp

    app.register_blueprint(usda_admin_bp)

    from opennourish.fasting import fasting_bp

    app.register_blueprint(fasting_bp, url_prefix="/fasting")

    from opennourish.undo import undo_bp

    app.register_blueprint(undo_bp)

    @app.context_processor
    def inject_user_settings():
        from flask_login import current_user

        if hasattr(current_user, "is_authenticated") and current_user.is_authenticated:
            # Get the user's meal setting, default to 6 if not set
            user_meals_per_day = current_user.meals_per_day or 6
            # Get the corresponding meal names, fall back to default if the key is invalid
            standard_meal_names = MEAL_CONFIG.get(
                user_meals_per_day, DEFAULT_MEAL_NAMES
            )
            return {
                "meals_per_day": user_meals_per_day,
                "standard_meal_names": standard_meal_names,
            }
        return {
            "meals_per_day": 6,  # Default for anonymous users
            "standard_meal_names": DEFAULT_MEAL_NAMES,
        }

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user:
            db.session.refresh(user)  # Ensure the user object is fresh
        return user

    @app.template_filter("nl2br")
    def nl2br_filter(s):
        return s.replace("\n", "<br>")

    register_template_filters(app)

    @app.cli.command("init-user-db")
    def init_user_db_command():
        """Clears existing user data and creates new tables."""
        with app.app_context():
            db.create_all()
            db.session.commit()
        print("Initialized the user database.")

    @app.cli.command("seed-exercise-activities")
    def seed_exercise_activities_command():
        """Seeds the database with default exercise activities."""
        with app.app_context():
            if ExerciseActivity.query.first():
                print("Exercise activities already exist. Skipping.")
                return

            print("Adding default exercise activities...")
            activities = [
                ExerciseActivity(name="Walking", met_value=3.5),
                ExerciseActivity(name="Running (moderate)", met_value=8.0),
                ExerciseActivity(name="Cycling (leisure)", met_value=5.0),
                ExerciseActivity(name="Swimming (freestyle)", met_value=7.0),
                ExerciseActivity(name="Weightlifting", met_value=3.0),
                ExerciseActivity(name="Yoga", met_value=2.5),
            ]
            db.session.add_all(activities)
            db.session.commit()
            print("Default exercise activities added.")

    # no cover: start
    @app.cli.command("seed-dev-data")
    @click.argument("count", default=3, type=int)
    def seed_dev_data_command(count):
        """Populates the user database with realistic test data."""
        with app.app_context():
            # Check if seeding is enabled and if the database is empty
            if os.getenv("SEED_DEV_DATA") != "true":
                print(
                    "SEED_DEV_DATA environment variable not set to 'true'. Skipping dev data seeding."
                )
                return

            if User.query.first() is not None:
                print("Database already contains users. Skipping dev data seeding.")
                return

            print("Starting to seed development data...")

            print("Creating main test user...")
            test_user = User(username="markus", email="schulz@alpharesearch.de")
            test_user.set_password("1")
            test_user.is_admin = True
            test_user.is_verified = True
            test_user.has_completed_onboarding = True
            db.session.add(test_user)
            db.session.commit()  # Commit here to get test_user.id
            print(f"Created main test user: {test_user.username}")

            fake = Faker()

            users_created = 0
            my_foods_created = 0
            check_ins_created = 0
            recipes_created = 0
            my_meals_created = 0
            my_meal_items_created = 0
            daily_logs_created = 0
            exercise_logs_created = 0

            # Fetch some FDC IDs from the USDA database for linking
            # This assumes usda_data.db is already populated
            usda_fdc_ids = [f.fdc_id for f in Food.query.all()]

            # Fetch all available food categories
            food_categories = FoodCategory.query.all()
            if not food_categories:
                print(
                    "No food categories found. Please run 'flask seed-usda-categories' first."
                )
                return
            food_category_ids = [fc.id for fc in food_categories]

            for i in range(count):
                user = User(
                    username="user" + f"{i}",
                    email=f"user{i}@example.com",
                    age=random.randint(18, 70),
                    gender=random.choice(["Male", "Female"]),
                    height_cm=random.uniform(150, 190),
                )
                user.is_verified = True
                user.has_completed_onboarding = True
                user.set_password("1")
                db.session.add(user)
                db.session.flush()  # To get user.id
                print(f"Created test user{i}: {user.username}")

                # Make the main test_user friends with this new user
                friendship = Friendship(
                    requester_id=test_user.id, receiver_id=user.id, status="accepted"
                )
                db.session.add(friendship)
                print(
                    f"Created friendship between {test_user.username} and {user.username}"
                )

                # UserGoal
                # current_app.logger.debug(f"UserGoal columns: {[c.name for c in UserGoal.__table__.columns]}")
                # Get latest check-in for initial goal weight/body_fat, if available
                latest_checkin = (
                    CheckIn.query.filter_by(user_id=user.id)
                    .order_by(CheckIn.checkin_date.desc())
                    .first()
                )

                goal = UserGoal(
                    user_id=user.id,
                    calories=random.randint(1800, 2500),
                    protein=random.randint(100, 200),
                    carbs=random.randint(200, 350),
                    fat=random.randint(50, 100),
                    calories_burned_goal_weekly=random.randint(1000, 3000),
                    exercises_per_week_goal=random.randint(3, 7),
                    minutes_per_exercise_goal=random.randint(30, 60),
                    weight_goal_kg=random.uniform(50, 100),
                    body_fat_percentage_goal=random.uniform(10, 25),
                    waist_cm_goal=random.uniform(60, 90),
                    default_fasting_hours=random.uniform(12, 96),
                )
                db.session.add(goal)

                # MyFood
                num_my_foods = random.randint(20, 30)
                user_my_foods = []
                for _ in range(num_my_foods):
                    my_food = None
                    if (
                        random.random() < 0.5 and usda_fdc_ids
                    ):  # 50% chance to create a USDA-sourced MyFood
                        fdc_id = random.choice(usda_fdc_ids)
                        usda_food = (
                            db.session.query(Food)
                            .options(
                                joinedload(Food.nutrients).joinedload(
                                    FoodNutrient.nutrient
                                )
                            )
                            .filter_by(fdc_id=fdc_id)
                            .first()
                        )

                        if usda_food:
                            my_food = MyFood(
                                user_id=user.id,
                                description=usda_food.description
                                + " My Custom USDA Food",
                                food_category_id=usda_food.food_category_id
                                if usda_food.food_category_id in food_category_ids
                                else random.choice(food_category_ids),
                                ingredients=usda_food.ingredients,
                                fdc_id=usda_food.fdc_id,
                                upc=usda_food.upc,
                                calories_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1008
                                    ),
                                    0.0,
                                ),
                                protein_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1003
                                    ),
                                    0.0,
                                ),
                                carbs_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1005
                                    ),
                                    0.0,
                                ),
                                fat_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1004
                                    ),
                                    0.0,
                                ),
                                saturated_fat_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1258
                                    ),
                                    0.0,
                                ),
                                trans_fat_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1257
                                    ),
                                    0.0,
                                ),
                                cholesterol_mg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1253
                                    ),
                                    0.0,
                                ),
                                sodium_mg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1093
                                    ),
                                    0.0,
                                ),
                                fiber_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1079
                                    ),
                                    0.0,
                                ),
                                sugars_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 2000
                                    ),
                                    0.0,
                                ),
                                added_sugars_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1235
                                    ),
                                    0.0,
                                ),
                                vitamin_d_mcg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1110
                                    ),
                                    0.0,
                                ),
                                calcium_mg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1087
                                    ),
                                    0.0,
                                ),
                                iron_mg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1089
                                    ),
                                    0.0,
                                ),
                                potassium_mg_per_100g=next(
                                    (
                                        fn.amount
                                        for fn in usda_food.nutrients
                                        if fn.nutrient.id == 1092
                                    ),
                                    0.0,
                                ),
                            )
                    else:  # Create a purely custom MyFood that mimics the new UI workflow
                        # 1. Define a realistic serving size in grams
                        serving_gram_weight = random.uniform(30, 250)

                        # 2. Generate nutrition facts for THAT serving size
                        calories_for_serving = random.uniform(50, 800)
                        protein_for_serving = random.uniform(1, 70)
                        carbs_for_serving = random.uniform(1, 100)
                        fat_for_serving = random.uniform(1, 60)

                        # 3. Calculate the scaling factor to get to 100g
                        factor = 100.0 / serving_gram_weight

                        # 4. Create the MyFood object with scaled, per-100g values
                        my_food = MyFood(
                            user_id=user.id,
                            description=fake.word().capitalize()
                            + " "
                            + fake.word()
                            + " My Custom Food",
                            food_category_id=random.choice(food_category_ids)
                            if food_category_ids
                            else None,
                            ingredients=fake.sentence(nb_words=6),
                            calories_per_100g=calories_for_serving * factor,
                            protein_per_100g=protein_for_serving * factor,
                            carbs_per_100g=carbs_for_serving * factor,
                            fat_per_100g=fat_for_serving * factor,
                        )

                    if my_food:
                        db.session.add(my_food)
                        user_my_foods.append(my_food)
                        my_foods_created += 1
                        db.session.flush()  # To get my_food.id for portions

                        # Add the mandatory 1-gram portion
                        gram_portion = UnifiedPortion(
                            my_food_id=my_food.id,
                            amount=1.0,
                            measure_unit_description="g",
                            portion_description="",
                            modifier="",
                            gram_weight=1.0,
                        )
                        db.session.add(gram_portion)

                        # Add other diverse portions
                        portion_types = [
                            ("slice", random.uniform(15, 40)),
                            ("bowl", random.uniform(150, 300)),
                            ("unit", random.uniform(5, 20)),
                        ]
                        for desc, weight in portion_types:
                            portion = UnifiedPortion(
                                my_food_id=my_food.id,
                                portion_description=desc,
                                gram_weight=weight,
                                amount=1.0,
                                measure_unit_description=desc,
                            )
                            db.session.add(portion)

                # CheckIn
                num_check_ins = 52  # Approximately one year of weekly check-ins
                for j in range(num_check_ins):
                    checkin_date = date.today() - timedelta(weeks=j)
                    check_in = CheckIn(
                        user_id=user.id,
                        checkin_date=checkin_date,
                        weight_kg=random.uniform(60, 90),
                        body_fat_percentage=random.uniform(10, 30),
                        waist_cm=random.uniform(70, 100),
                    )
                    db.session.add(check_in)
                check_ins_created += num_check_ins

                # Exercise Logs
                num_exercise_logs = random.randint(30, 50)
                all_activities = ExerciseActivity.query.all()
                for j in range(num_exercise_logs):
                    log_date = date.today() - timedelta(days=random.randint(0, 60))
                    duration = random.randint(15, 90)  # minutes

                    if (
                        random.random() < 0.8 and all_activities
                    ):  # 80% chance to use a predefined activity
                        activity = random.choice(all_activities)
                        # Fetch the user's most recent weight for calorie calculation
                        latest_checkin = (
                            CheckIn.query.filter_by(user_id=user.id)
                            .order_by(CheckIn.checkin_date.desc())
                            .first()
                        )
                        user_weight_kg = (
                            latest_checkin.weight_kg if latest_checkin else 70.0
                        )  # Default weight if no check-ins
                        calories_burned = int(
                            (activity.met_value * 3.5 * user_weight_kg / 200) * duration
                        )
                        exercise_log = ExerciseLog(
                            user_id=user.id,
                            log_date=log_date,
                            activity_id=activity.id,
                            duration_minutes=duration,
                            calories_burned=calories_burned,
                        )
                    else:  # 20% chance for a manual entry
                        exercise_log = ExerciseLog(
                            user_id=user.id,
                            log_date=log_date,
                            manual_description=fake.sentence(nb_words=4),
                            duration_minutes=duration,
                            calories_burned=random.randint(
                                50, 500
                            ),  # Random calories for manual entry
                        )
                    db.session.add(exercise_log)
                exercise_logs_created += num_exercise_logs

                # Recipes
                num_recipes = random.randint(2, 5)
                user_recipes = []
                for _ in range(num_recipes):
                    recipe = Recipe(
                        user_id=user.id,
                        name=fake.word().capitalize()
                        + " "
                        + fake.word()
                        + " My Recipe",
                        instructions=fake.paragraph(nb_sentences=5),
                        servings=random.randint(1, 6),
                        is_public=random.choice([True, False]),
                        food_category_id=random.choice(food_category_ids)
                        if food_category_ids
                        else None,
                    )
                    db.session.add(recipe)
                    user_recipes.append(recipe)
                    recipes_created += 1
                    db.session.flush()  # To get recipe.id for ingredients and portions

                    # Add the mandatory 1-gram portion
                    gram_portion = UnifiedPortion(
                        recipe_id=recipe.id,
                        amount=1.0,
                        measure_unit_description="g",
                        portion_description="",
                        modifier="",
                        gram_weight=1.0,
                    )
                    db.session.add(gram_portion)

                # RecipeIngredients
                for r in user_recipes:
                    # Add some ingredients
                    num_ingredients = random.randint(3, 8)
                    for _ in range(num_ingredients):
                        ingredient_food_item = None
                        fdc_id = None
                        my_food_id = None
                        recipe_id_link = None
                        amount_grams = 0.0

                        choice = random.choice(["usda", "my_food", "recipe_link"])

                        if choice == "usda" and usda_fdc_ids:
                            fdc_id = random.choice(usda_fdc_ids)
                            ingredient_food_item = db.session.get(Food, fdc_id)
                        elif choice == "my_food" and user_my_foods:
                            ingredient_food_item = random.choice(user_my_foods)
                            my_food_id = ingredient_food_item.id
                        elif choice == "recipe_link" and user_recipes:
                            # Ensure not to nest the same recipe inside itself
                            possible_linked_recipes = [
                                rec for rec in user_recipes if rec.id != r.id
                            ]
                            if possible_linked_recipes:
                                ingredient_food_item = random.choice(
                                    possible_linked_recipes
                                )
                                recipe_id_link = ingredient_food_item.id
                            else:
                                continue  # Skip if no other recipes are available to link
                        else:
                            continue  # Skip if no suitable item found

                        if ingredient_food_item:
                            # Ensure a 1-gram portion exists for USDA foods
                            if isinstance(ingredient_food_item, Food):
                                gram_portion = UnifiedPortion.query.filter_by(
                                    fdc_id=ingredient_food_item.fdc_id, gram_weight=1.0
                                ).first()
                                if not gram_portion:
                                    gram_portion = UnifiedPortion(
                                        fdc_id=ingredient_food_item.fdc_id,
                                        amount=1.0,
                                        measure_unit_description="g",
                                        portion_description="",
                                        modifier="",
                                        gram_weight=1.0,
                                    )
                                    db.session.add(gram_portion)
                                    db.session.flush()  # Ensure it gets an ID

                                # Re-query available_portions to include the newly created gram_portion
                                available_portions = (
                                    db.session.query(UnifiedPortion)
                                    .filter_by(fdc_id=ingredient_food_item.fdc_id)
                                    .all()
                                )
                            elif hasattr(ingredient_food_item, "portions"):
                                available_portions = ingredient_food_item.portions

                            if available_portions:
                                selected_portion = random.choice(available_portions)
                                amount_grams = (
                                    random.uniform(0.5, 3.0)
                                    * selected_portion.gram_weight
                                )  # Random quantity of the selected portion
                            else:
                                amount_grams = random.uniform(
                                    10, 300
                                )  # Fallback to random grams if no portions""

                            ingredient = RecipeIngredient(
                                recipe_id=r.id,
                                fdc_id=fdc_id,
                                my_food_id=my_food_id,
                                recipe_id_link=recipe_id_link,
                                amount_grams=amount_grams,
                            )
                            db.session.add(ingredient)
                db.session.flush()  # Ensure ingredients are in the session to be calculated

                # Seed Recipe Portions
                for r in user_recipes:
                    # Calculate total weight to create realistic portions
                    total_gram_weight = sum(ing.amount_grams for ing in r.ingredients)

                    # Create a portion based on the recipe's servings
                    if r.servings and r.servings > 0 and total_gram_weight > 0:
                        gram_weight_per_serving = total_gram_weight / r.servings
                        serving_portion = UnifiedPortion(
                            recipe_id=r.id,
                            amount=1.0,
                            measure_unit_description="serving",
                            portion_description=f"1 of {r.servings}",
                            modifier=None,
                            gram_weight=gram_weight_per_serving,
                        )
                        db.session.add(serving_portion)

                    # Add a standard 100g portion for easy logging
                    if total_gram_weight > 0:
                        g100_portion = UnifiedPortion(
                            recipe_id=r.id,
                            amount=100.0,
                            measure_unit_description="g",
                            portion_description=None,
                            modifier=None,
                            gram_weight=100.0,
                        )
                        db.session.add(g100_portion)

                    # Create one or two other random, descriptive portions
                    if (
                        total_gram_weight > 10
                    ):  # Only add random portions if recipe is substantial
                        portion_ideas = [
                            (
                                "slice",
                                total_gram_weight
                                / (r.servings * 2 if r.servings else 2),
                            ),
                            ("bowl", random.uniform(200, 400)),
                        ]

                        # Ensure we don't pick more samples than available
                        num_samples = min(random.randint(1, 2), len(portion_ideas))

                        for desc, weight in random.sample(portion_ideas, num_samples):
                            if weight > 1:  # Ensure weight is sensible
                                random_portion = UnifiedPortion(
                                    recipe_id=r.id,
                                    amount=1.0,
                                    measure_unit_description=desc,
                                    portion_description=None,
                                    modifier=None,
                                    gram_weight=weight,
                                )
                                db.session.add(random_portion)

                # MyMeals
                num_my_meals = random.randint(5, 10)
                user_my_meals = []
                for _ in range(num_my_meals):
                    meal = MyMeal(
                        user_id=user.id, name=fake.word().capitalize() + " My Meal"
                    )
                    db.session.add(meal)
                    user_my_meals.append(meal)
                my_meals_created += num_my_meals
                db.session.flush()  # To get meal.id for items

                # MyMealItems
                for m in user_my_meals:
                    num_meal_items = random.randint(2, 5)
                    for _ in range(num_meal_items):
                        choice = random.choice(["usda", "my_food", "recipe"])
                        fdc_id = None
                        my_food_id = None
                        recipe_id = None

                        if choice == "usda" and usda_fdc_ids:
                            fdc_id = random.choice(usda_fdc_ids)
                        elif choice == "my_food" and user_my_foods:
                            my_food_id = random.choice(user_my_foods).id
                        elif choice == "recipe" and user_recipes:
                            recipe_id = random.choice(user_recipes).id
                        else:
                            continue  # Skip if no suitable item found

                        if fdc_id or my_food_id or recipe_id:
                            item = MyMealItem(
                                my_meal_id=m.id,
                                fdc_id=fdc_id,
                                my_food_id=my_food_id,
                                recipe_id=recipe_id,
                                amount_grams=random.uniform(20, 400),
                            )
                            db.session.add(item)
                            my_meal_items_created += 1

                # DailyLog
                num_daily_logs = random.randint(100, 150)
                for j in range(num_daily_logs):
                    log_date = date.today() - timedelta(
                        days=random.randint(0, 60)
                    )  # Last 2 months
                    meal_name = random.choice(
                        [
                            "Breakfast",
                            "Snack (morning)",
                            "Lunch",
                            "Snack (afternoon)",
                            "Dinner",
                            "Snack (evening)",
                        ]
                    )

                    # Randomly link to USDA, MyFood, Recipe, or MyMeal
                    choice = random.choice(["usda", "my_food", "recipe", "my_meal"])
                    fdc_id = None
                    my_food_id = None
                    recipe_id = None
                    food_item_for_portions = None

                    if choice == "usda" and usda_fdc_ids:
                        fdc_id = random.choice(usda_fdc_ids)
                        food_item_for_portions = db.session.get(Food, fdc_id)
                    elif choice == "my_food" and user_my_foods:
                        selected_my_food = random.choice(user_my_foods)
                        my_food_id = selected_my_food.id
                        food_item_for_portions = selected_my_food
                    elif choice == "recipe" and user_recipes:
                        selected_recipe = random.choice(user_recipes)
                        recipe_id = selected_recipe.id
                        food_item_for_portions = selected_recipe
                    elif choice == "my_meal" and user_my_meals:
                        selected_meal = random.choice(user_my_meals)
                        selected_meal.usage_count += 1  # Increment usage count
                        for item in selected_meal.items:
                            # For my_meal items, we don't select portions, just log their base grams
                            log_entry = DailyLog(
                                user_id=user.id,
                                log_date=log_date,
                                meal_name=meal_name,
                                fdc_id=item.fdc_id,
                                my_food_id=item.my_food_id,
                                recipe_id=item.recipe_id,
                                amount_grams=item.amount_grams
                                * random.uniform(0.8, 1.2),  # Vary amount slightly
                            )
                            db.session.add(log_entry)
                            daily_logs_created += 1
                        continue  # Skip the rest of the loop for this iteration
                    else:  # Fallback if no suitable item found
                        # Try to pick a food item that has portions, prioritizing MyFoods/Recipes
                        potential_food_items = []
                        if user_my_foods:
                            potential_food_items.extend(
                                [mf for mf in user_my_foods if mf.portions]
                            )
                        if user_recipes:
                            potential_food_items.extend(
                                [r for r in user_recipes if r.portions]
                            )

                        if potential_food_items:
                            food_item_for_portions = random.choice(potential_food_items)
                            if isinstance(food_item_for_portions, MyFood):
                                my_food_id = food_item_for_portions.id
                            elif isinstance(food_item_for_portions, Recipe):
                                recipe_id = food_item_for_portions.id
                        elif usda_fdc_ids:
                            # Fallback to any USDA food if no MyFoods/Recipes with portions
                            fdc_id = random.choice(usda_fdc_ids)
                            food_item_for_portions = db.session.get(Food, fdc_id)
                        else:
                            continue  # Skip if no food items can be linked

                    # Select a random portion for the DailyLog entry
                    portion_id_fk = None
                    serving_type = "g"
                    amount_grams = random.uniform(50, 500)  # Default to random grams

                    if food_item_for_portions:
                        # Ensure a 1-gram portion exists for USDA foods
                        if isinstance(food_item_for_portions, Food):
                            gram_portion = UnifiedPortion.query.filter_by(
                                fdc_id=food_item_for_portions.fdc_id, gram_weight=1.0
                            ).first()
                            if not gram_portion:
                                gram_portion = UnifiedPortion(
                                    fdc_id=food_item_for_portions.fdc_id,
                                    amount=1.0,
                                    measure_unit_description="g",
                                    portion_description="",
                                    modifier="",
                                    gram_weight=1.0,
                                )
                                db.session.add(gram_portion)
                                db.session.flush()  # Ensure it gets an ID

                            # Re-query available_portions to include the newly created gram_portion
                            available_portions = (
                                db.session.query(UnifiedPortion)
                                .filter_by(fdc_id=food_item_for_portions.fdc_id)
                                .all()
                            )
                        elif hasattr(food_item_for_portions, "portions"):
                            # For MyFood and Recipe, use the relationship
                            available_portions = food_item_for_portions.portions

                        if available_portions:
                            selected_portion = random.choice(available_portions)
                            portion_id_fk = selected_portion.id
                            serving_type = selected_portion.full_description_str
                            amount_grams = (
                                random.uniform(0.5, 2.0) * selected_portion.gram_weight
                            )  # Random quantity of the selected portion
                        else:
                            # If no specific portions, default to grams
                            amount_grams = random.uniform(50, 500)
                            serving_type = "g"
                            portion_id_fk = None

                    # Only create a single log_entry if not a my_meal type that was expanded
                    if choice != "my_meal" or not user_my_meals:
                        log_entry = DailyLog(
                            user_id=user.id,
                            log_date=log_date,
                            meal_name=meal_name,
                            amount_grams=amount_grams,
                            fdc_id=fdc_id,
                            my_food_id=my_food_id,
                            recipe_id=recipe_id,
                            serving_type=serving_type,
                            portion_id_fk=portion_id_fk,
                        )
                        db.session.add(log_entry)
                        daily_logs_created += 1

                users_created += 1

                users_created += 1

            db.session.commit()
            print(
                f"Database seeded with {users_created} users, {my_foods_created} MyFoods, {check_ins_created} CheckIns, {recipes_created} Recipes, {my_meals_created} MyMeals, {my_meal_items_created} MyMealItems, {daily_logs_created} Daily Logs, and {exercise_logs_created} Exercise Logs."
            )

    # no cover: stop
    @app.cli.command("seed-usda-portions")
    def seed_usda_portions_command():
        """
        Seeds USDA food portions from food_portion.csv into the unified portions table.
        This command is smart: it will not overwrite portions for any food that has
        been manually curated by a key user (i.e., where at least one portion
        has `was_imported` set to False).
        It also prevents duplicate portions from being created.
        """
        with app.app_context():
            print("Seeding USDA portions...")

            # 1. Clean up any pre-existing duplicate imported portions from previous runs.
            # This ensures that even curated foods are cleaned of duplicates without
            # affecting manually added (non-imported) portions.
            print("Checking for and removing existing duplicate imported portions...")
            from sqlalchemy import func

            group_by_columns = [
                UnifiedPortion.fdc_id,
                UnifiedPortion.amount,
                UnifiedPortion.measure_unit_description,
                UnifiedPortion.portion_description,
                UnifiedPortion.modifier,
                UnifiedPortion.gram_weight,
            ]
            # Subquery to find the minimum ID for each unique group of imported portions
            subquery = (
                db.session.query(func.min(UnifiedPortion.id).label("min_id"))
                .filter(UnifiedPortion.was_imported)
                .group_by(*group_by_columns)
                .subquery()
            )
            # Get the list of IDs to keep (the first instance of each unique portion)
            ids_to_keep_query = db.session.query(subquery.c.min_id)
            ids_to_keep = {row[0] for row in ids_to_keep_query}
            # Delete all imported portions whose IDs are not in the list of IDs to keep
            duplicates_delete_query = UnifiedPortion.query.filter(
                UnifiedPortion.was_imported, ~UnifiedPortion.id.in_(ids_to_keep)
            )
            deleted_duplicates_count = duplicates_delete_query.delete(
                synchronize_session=False
            )
            db.session.commit()
            if deleted_duplicates_count > 0:
                print(
                    f"Removed {deleted_duplicates_count} pre-existing duplicate imported portions."
                )
            else:
                print("No pre-existing duplicate imported portions found.")

            # 2. Find all fdc_ids that have been manually curated.
            # These are foods where at least one portion has was_imported = False.
            curated_fdc_ids_query = (
                db.session.query(UnifiedPortion.fdc_id)
                .filter_by(was_imported=False)
                .distinct()
            )
            curated_fdc_ids = {row.fdc_id for row in curated_fdc_ids_query}
            if curated_fdc_ids:
                print(
                    f"Found {len(curated_fdc_ids)} manually curated foods. Their portions will be skipped during re-import."
                )

            # 3. Delete existing imported USDA portions for non-curated foods only.
            # This clears the way for a fresh import.
            delete_query = UnifiedPortion.query.filter(
                UnifiedPortion.was_imported,
                ~UnifiedPortion.fdc_id.in_(curated_fdc_ids),
            )
            deleted_count = delete_query.delete(synchronize_session=False)
            db.session.commit()
            print(
                f"Deleted {deleted_count} existing imported USDA portions from non-curated foods for re-import."
            )

            usda_data_dir = os.path.join(
                current_app.root_path, "..", "persistent", "usda_data"
            )
            measure_unit_csv_path = os.path.join(usda_data_dir, "measure_unit.csv")
            food_portion_csv_path = os.path.join(usda_data_dir, "food_portion.csv")

            if not os.path.exists(measure_unit_csv_path) or not os.path.exists(
                food_portion_csv_path
            ):
                print(
                    f"Error: USDA data files (measure_unit.csv, food_portion.csv) not found in {usda_data_dir}."
                )
                return

            # 4. Load measure units from CSV for efficient lookup.
            measure_units = {}
            with open(measure_unit_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    measure_units[row[0]] = row[1]
            print(f"Loaded {len(measure_units)} measure units from CSV.")

            # 5. Load all portions from the USDA's food_portion.csv, preventing duplicates.
            portions_to_add = []
            unique_portions_tracker = set()
            with open(food_portion_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    fdc_id = int(row[1])
                    # Skip this portion if its fdc_id is in the curated list
                    if fdc_id in curated_fdc_ids:
                        continue

                    # Sanitize the modifier: if it's a number, discard it.
                    modifier_val = row[6]
                    if modifier_val.isdigit():
                        modifier_val = None
                    else:
                        modifier_val = modifier_val or None

                    seq_num = int(row[2]) if row[2] else None
                    amount = float(row[3]) if row[3] else None
                    measure_unit_desc = (
                        measure_units.get(row[4], "") if row[4] != "9999" else ""
                    )
                    portion_desc = row[5] or None
                    gram_weight = float(row[7])

                    # Create a unique key to prevent adding duplicates from the CSV
                    portion_key = (
                        fdc_id,
                        amount,
                        measure_unit_desc,
                        portion_desc,
                        modifier_val,
                        gram_weight,
                    )
                    if portion_key in unique_portions_tracker:
                        continue
                    unique_portions_tracker.add(portion_key)

                    # Create a UnifiedPortion object for each unique row
                    portion = UnifiedPortion(
                        fdc_id=fdc_id,
                        seq_num=seq_num,
                        amount=amount,
                        measure_unit_description=measure_unit_desc,
                        portion_description=portion_desc,
                        modifier=modifier_val,
                        gram_weight=gram_weight,
                        was_imported=True,  # Mark as imported
                    )
                    portions_to_add.append(portion)
            print(
                f"Loaded {len(portions_to_add)} new, unique portions to add from food_portion.csv."
            )

            # 6. Add all collected portions to the database in a single transaction.
            if portions_to_add:
                db.session.bulk_save_objects(portions_to_add)
                db.session.commit()
                print(
                    f"Successfully seeded {len(portions_to_add)} new USDA portions to the user database."
                )
            else:
                print("No new USDA portions were found or needed to be added.")

    @app.cli.command("deduplicate-portions")
    def deduplicate_portions_command():
        """
        Finds and removes duplicate portions from the unified_portion table,
        keeping only the first instance of each unique portion.
        """
        with app.app_context():
            print("Checking for and removing duplicate portions...")
            from sqlalchemy import func

            group_by_columns = [
                UnifiedPortion.fdc_id,
                UnifiedPortion.my_food_id,
                UnifiedPortion.recipe_id,
                UnifiedPortion.amount,
                UnifiedPortion.measure_unit_description,
                UnifiedPortion.portion_description,
                UnifiedPortion.modifier,
                UnifiedPortion.gram_weight,
            ]
            # Subquery to find the minimum ID for each unique group of portions
            subquery = (
                db.session.query(func.min(UnifiedPortion.id).label("min_id"))
                .group_by(*group_by_columns)
                .subquery()
            )
            # Get the list of IDs to keep (the first instance of each unique portion)
            ids_to_keep_query = db.session.query(subquery.c.min_id)
            ids_to_keep = {row[0] for row in ids_to_keep_query}

            # Find all portion IDs to determine which ones to delete
            all_ids_query = db.session.query(UnifiedPortion.id)
            all_ids = {row[0] for row in all_ids_query}
            ids_to_delete = all_ids - ids_to_keep

            if not ids_to_delete:
                print("No duplicate portions found.")
                return

            # Delete all portions whose IDs are in the list of IDs to delete
            duplicates_delete_query = UnifiedPortion.query.filter(
                UnifiedPortion.id.in_(ids_to_delete)
            )
            deleted_duplicates_count = duplicates_delete_query.delete(
                synchronize_session=False
            )
            db.session.commit()

            print(f"Removed {deleted_duplicates_count} duplicate portions.")

    @app.cli.command("seed-usda-categories")
    def seed_usda_categories_command():
        """Seeds the database with USDA food categories."""
        with app.app_context():
            if FoodCategory.query.first():
                print("Food categories already exist. Skipping.")
                return

            print("Seeding USDA food categories...")
            usda_data_dir = os.path.join(
                current_app.root_path, "..", "persistent", "usda_data"
            )
            food_category_csv_path = os.path.join(usda_data_dir, "food_category.csv")

            if not os.path.exists(food_category_csv_path):
                print(
                    f"Error: USDA data file (food_category.csv) not found in {usda_data_dir}."
                )
                return

            categories_to_add = []
            with open(food_category_csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    category = FoodCategory(
                        id=int(row[0]), code=int(row[1]), description=row[2]
                    )
                    categories_to_add.append(category)

            if categories_to_add:
                db.session.bulk_save_objects(categories_to_add)
                db.session.commit()
                print(f"Successfully seeded {len(categories_to_add)} food categories.")
            else:
                print("No food categories found to seed.")

    user_cli = app.cli.group("user")(lambda: None)

    @user_cli.command("manage-admin")
    @click.argument("username")
    @click.option(
        "--action",
        type=click.Choice(["grant", "revoke"]),
        required=True,
        help="Action to perform: grant or revoke admin rights.",
    )
    def manage_admin(username, action):
        """Grant or revoke administrator privileges for a user."""
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if not user:
                print(f"Error: User '{username}' not found.")
                return

            if action == "grant":
                if user.is_admin:
                    print(f"User '{username}' already has admin privileges.")
                else:
                    user.is_admin = True
                    db.session.commit()
                    print(f"Successfully granted admin privileges to '{username}'.")
            elif action == "revoke":
                if not user.is_admin:
                    print(f"User '{username}' does not have admin privileges.")
                else:
                    user.is_admin = False
                    db.session.commit()
                    print(f"Successfully revoked admin privileges from '{username}'.")

    @user_cli.command("manage-key-user")
    @click.argument("username")
    @click.option(
        "--action",
        type=click.Choice(["grant", "revoke"]),
        required=True,
        help="Action to perform: grant or revoke key user rights.",
    )
    def manage_key_user(username, action):
        """Grant or revoke key user privileges for a user."""
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if not user:
                print(f"Error: User '{username}' not found.")
                return

            if action == "grant":
                if user.is_key_user:
                    print(f"User '{username}' already has key user privileges.")
                else:
                    user.is_key_user = True
                    db.session.commit()
                    print(f"Successfully granted key user privileges to '{username}'.")
            elif action == "revoke":
                if not user.is_key_user:
                    print(f"User '{username}' does not have key user privileges.")
                else:
                    user.is_key_user = False
                    db.session.commit()
                    print(
                        f"Successfully revoked key user privileges from '{username}'."
                    )

    return app
