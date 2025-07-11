from flask import Flask, current_app
import os
from models import db, User, UserGoal, MyFood, CheckIn, Recipe, DailyLog, Food, Nutrient, FoodNutrient, UnifiedPortion, RecipeIngredient, MyMeal, MyMealItem, ExerciseActivity, ExerciseLog, Friendship
from sqlalchemy.orm import joinedload
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
                instance_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance'),
                instance_relative_config=True,
                template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
                static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'))
    if isinstance(config_class, dict):
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)

    # Enable the Jinja2 'do' extension
    app.jinja_env.add_extension('jinja2.ext.do')

    from opennourish.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from opennourish.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    from opennourish.my_foods.routes import my_foods_bp
    app.register_blueprint(my_foods_bp, url_prefix='/my_foods')

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

    from opennourish.search import search_bp
    app.register_blueprint(search_bp, url_prefix='/search')

    from opennourish.friends import friends_bp
    app.register_blueprint(friends_bp, url_prefix='/friends')

    from opennourish.profile import profile_bp
    app.register_blueprint(profile_bp, url_prefix='/user')

    from opennourish.admin import admin_bp
    app.register_blueprint(admin_bp)

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

    @app.cli.command("seed-exercise-activities")
    def seed_exercise_activities_command():
        """Seeds the database with default exercise activities."""
        with app.app_context():
            if ExerciseActivity.query.first():
                print("Exercise activities already exist. Skipping.")
                return

            print("Adding default exercise activities...")
            activities = [
                ExerciseActivity(name='Walking', met_value=3.5),
                ExerciseActivity(name='Running (moderate)', met_value=8.0),
                ExerciseActivity(name='Cycling (leisure)', met_value=5.0),
                ExerciseActivity(name='Swimming (freestyle)', met_value=7.0),
                ExerciseActivity(name='Weightlifting', met_value=3.0),
                ExerciseActivity(name='Yoga', met_value=2.5),
            ]
            db.session.add_all(activities)
            db.session.commit()
            print("Default exercise activities added.")

    @app.cli.command("seed-dev-data")
    @click.argument('count', default=3, type=int)
    def seed_dev_data_command(count):
        """Populates the user database with realistic test data."""
        with app.app_context():
            # Check if seeding is enabled and if the database is empty
            if os.getenv('SEED_DEV_DATA') != 'true':
                print("SEED_DEV_DATA environment variable not set to 'true'. Skipping dev data seeding.")
                return

            if User.query.first() is not None:
                print("Database already contains users. Skipping dev data seeding.")
                return
            
            print("Starting to seed development data...")

            print("Creating main test user...")
            test_user = User(username='markus')
            test_user.set_password('1')
            db.session.add(test_user)
            db.session.commit() # Commit here to get test_user.id
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

            for i in range(count):
                user = User(
                    username='user'+f"{i}",
                    age=random.randint(18, 70),
                    gender=random.choice(['Male', 'Female']),
                    height_cm=random.uniform(150, 190)
                )
                user.set_password('1')
                db.session.add(user)
                db.session.flush()  # To get user.id
                print(f"Created test user{i}: {user.username}")

                # Make the main test_user friends with this new user
                friendship = Friendship(
                    requester_id=test_user.id,
                    receiver_id=user.id,
                    status='accepted'
                )
                db.session.add(friendship)
                print(f"Created friendship between {test_user.username} and {user.username}")

                # UserGoal
                current_app.logger.debug(f"UserGoal columns: {[c.name for c in UserGoal.__table__.columns]}")
                # Get latest check-in for initial goal weight/body_fat, if available
                latest_checkin = CheckIn.query.filter_by(user_id=user.id).order_by(CheckIn.checkin_date.desc()).first()
                
                goal = UserGoal(
                    user_id=user.id,
                    calories=random.randint(1800, 2500),
                    protein=random.randint(100, 200),
                    carbs=random.randint(200, 350),
                    fat=random.randint(50, 100),
                    calories_burned_goal_weekly=random.randint(1000, 3000),
                    exercises_per_week_goal=random.randint(3, 7),
                    minutes_per_exercise_goal=random.randint(30, 60)
                )
                db.session.add(goal)

                # MyFood
                num_my_foods = random.randint(20, 30)
                user_my_foods = []
                for _ in range(num_my_foods):
                    if random.random() < 0.5 and usda_fdc_ids: # 50% chance to create a USDA-sourced MyFood
                        fdc_id = random.choice(usda_fdc_ids)
                        usda_food = db.session.query(Food).options(
                            joinedload(Food.nutrients).joinedload(FoodNutrient.nutrient)
                        ).filter_by(fdc_id=fdc_id).first()

                        if usda_food:
                            my_food = MyFood(
                                user_id=user.id,
                                description=usda_food.description + ' My Custom USDA Food',
                                ingredients=usda_food.ingredients,
                                fdc_id=usda_food.fdc_id,
                                upc=usda_food.upc,
                                calories_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1008), 0.0),
                                protein_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1003), 0.0),
                                carbs_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1005), 0.0),
                                fat_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1004), 0.0),
                                saturated_fat_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1258), 0.0),
                                trans_fat_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1257), 0.0),
                                cholesterol_mg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1253), 0.0),
                                sodium_mg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1093), 0.0),
                                fiber_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1079), 0.0),
                                sugars_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 2000), 0.0),
                                vitamin_d_mcg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1110), 0.0),
                                calcium_mg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1087), 0.0),
                                iron_mg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1089), 0.0),
                                potassium_mg_per_100g=next((fn.amount for fn in usda_food.nutrients if fn.nutrient.id == 1092), 0.0)
                            )
                            db.session.add(my_food)
                            user_my_foods.append(my_food)
                            my_foods_created += 1
                            db.session.flush() # To get my_food.id for portions

                            # Add diverse portions for USDA-sourced MyFood
                            portion_types = [
                                ("cup", random.uniform(100, 250)),
                                ("serving", random.uniform(50, 150)),
                                ("piece", random.uniform(10, 50))
                            ]
                            for desc, weight in portion_types:
                                my_portion = UnifiedPortion(
                                    my_food_id=my_food.id,
                                    portion_description=desc,
                                    gram_weight=weight,
                                    amount=1.0,
                                    measure_unit_description=desc,
                                )
                                db.session.add(my_portion)
                    else: # Create a purely custom MyFood
                        my_food = MyFood(
                            user_id=user.id,
                            description=fake.word().capitalize() + ' ' + fake.word()+ ' My Custom Food',
                            ingredients=fake.sentence(nb_words=6),
                            calories_per_100g=random.uniform(50, 500),
                            protein_per_100g=random.uniform(1, 50),
                            carbs_per_100g=random.uniform(1, 80),
                            fat_per_100g=random.uniform(1, 50)
                        )
                        db.session.add(my_food)
                        user_my_foods.append(my_food)
                        my_foods_created += 1
                        db.session.flush()  # To get my_food.id for portions

                        # Add diverse portions for custom MyFood
                        portion_types = [
                            ("slice", random.uniform(15, 40)),
                            ("bowl", random.uniform(150, 300)),
                            ("unit", random.uniform(5, 20))
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
                num_check_ins = 52 # Approximately one year of weekly check-ins
                for j in range(num_check_ins):
                    checkin_date = date.today() - timedelta(weeks=j)
                    check_in = CheckIn(
                        user_id=user.id,
                        checkin_date=checkin_date,
                        weight_kg=random.uniform(60, 90),
                        body_fat_percentage=random.uniform(10, 30),
                        waist_cm=random.uniform(70, 100)
                    )
                    db.session.add(check_in)
                check_ins_created += num_check_ins

                # Exercise Logs
                num_exercise_logs = random.randint(30, 50)
                all_activities = ExerciseActivity.query.all()
                for j in range(num_exercise_logs):
                    log_date = date.today() - timedelta(days=random.randint(0, 60))
                    duration = random.randint(15, 90) # minutes
                    
                    if random.random() < 0.8 and all_activities: # 80% chance to use a predefined activity
                        activity = random.choice(all_activities)
                        # Fetch the user's most recent weight for calorie calculation
                        latest_checkin = CheckIn.query.filter_by(user_id=user.id).order_by(CheckIn.checkin_date.desc()).first()
                        user_weight_kg = latest_checkin.weight_kg if latest_checkin else 70.0 # Default weight if no check-ins
                        calories_burned = int((activity.met_value * 3.5 * user_weight_kg / 200) * duration)
                        exercise_log = ExerciseLog(
                            user_id=user.id,
                            log_date=log_date,
                            activity_id=activity.id,
                            duration_minutes=duration,
                            calories_burned=calories_burned
                        )
                    else: # 20% chance for a manual entry
                        exercise_log = ExerciseLog(
                            user_id=user.id,
                            log_date=log_date,
                            manual_description=fake.sentence(nb_words=4),
                            duration_minutes=duration,
                            calories_burned=random.randint(50, 500) # Random calories for manual entry
                        )
                    db.session.add(exercise_log)
                exercise_logs_created += num_exercise_logs

                # Recipes
                num_recipes = random.randint(2, 5)
                user_recipes = []
                for _ in range(num_recipes):
                    recipe = Recipe(
                        user_id=user.id,
                        name=fake.word().capitalize() + ' ' + fake.word() + ' My Recipe',
                        instructions=fake.paragraph(nb_sentences=5),
                        servings=random.randint(1, 6),
                        is_public=random.choice([True, False])
                    )
                    db.session.add(recipe)
                    user_recipes.append(recipe)
                recipes_created += num_recipes
                db.session.flush()  # To get recipe.id for ingredients and portions

                # RecipeIngredients
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
                db.session.flush() # Ensure ingredients are in the session to be calculated

                # Seed Recipe Portions
                for r in user_recipes:
                    # Create a few random portions for the recipe
                    portion_types = [
                        ("serving", random.uniform(100, 300)),
                        ("bowl", random.uniform(200, 500)),
                        ("plate", random.uniform(300, 700))
                    ]
                    for desc, weight in portion_types:
                        new_portion = UnifiedPortion(
                            recipe_id=r.id,
                            amount=1.0,
                            measure_unit_description=desc,
                            portion_description=desc,
                            gram_weight=weight
                        )
                        db.session.add(new_portion)

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

                    # Randomly link to USDA, MyFood, Recipe, or MyMeal
                    choice = random.choice(['usda', 'my_food', 'recipe', 'my_meal'])
                    fdc_id = None
                    my_food_id = None
                    recipe_id = None
                    food_item_for_portions = None

                    if choice == 'usda' and usda_fdc_ids:
                        fdc_id = random.choice(usda_fdc_ids)
                        food_item_for_portions = db.session.get(Food, fdc_id)
                    elif choice == 'my_food' and user_my_foods:
                        selected_my_food = random.choice(user_my_foods)
                        my_food_id = selected_my_food.id
                        food_item_for_portions = selected_my_food
                    elif choice == 'recipe' and user_recipes:
                        selected_recipe = random.choice(user_recipes)
                        recipe_id = selected_recipe.id
                        food_item_for_portions = selected_recipe
                    elif choice == 'my_meal' and user_my_meals:
                        selected_meal = random.choice(user_my_meals)
                        selected_meal.usage_count += 1 # Increment usage count
                        for item in selected_meal.items:
                            # For my_meal items, we don't select portions, just log their base grams
                            log_entry = DailyLog(
                                user_id=user.id,
                                log_date=log_date,
                                meal_name=meal_name,
                                fdc_id=item.fdc_id,
                                my_food_id=item.my_food_id,
                                recipe_id=item.recipe_id,
                                amount_grams=item.amount_grams * random.uniform(0.8, 1.2) # Vary amount slightly
                            )
                            db.session.add(log_entry)
                            daily_logs_created += 1
                        continue # Skip the rest of the loop for this iteration
                    else:  # Fallback if no suitable item found
                        # Try to pick a food item that has portions, prioritizing MyFoods/Recipes
                        potential_food_items = []
                        if user_my_foods:
                            potential_food_items.extend([mf for mf in user_my_foods if mf.portions])
                        if user_recipes:
                            potential_food_items.extend([r for r in user_recipes if r.portions])
                        
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
                    serving_type = 'g'
                    amount_grams = random.uniform(50, 500) # Default to random grams

                    if food_item_for_portions:
                        available_portions = []
                        if isinstance(food_item_for_portions, Food):
                            # For USDA Food, query UnifiedPortion directly
                            available_portions = db.session.query(UnifiedPortion).filter_by(fdc_id=food_item_for_portions.fdc_id).all()
                        elif hasattr(food_item_for_portions, 'portions'):
                            # For MyFood and Recipe, use the relationship
                            available_portions = food_item_for_portions.portions
                        
                        if available_portions:
                            selected_portion = random.choice(available_portions)
                            portion_id_fk = selected_portion.id
                            serving_type = selected_portion.full_description_str
                            amount_grams = random.uniform(0.5, 2.0) * selected_portion.gram_weight # Random quantity of the selected portion
                        else:
                            # If no specific portions, default to grams
                            amount_grams = random.uniform(50, 500)
                            serving_type = 'g'
                            portion_id_fk = None

                    # Only create a single log_entry if not a my_meal type that was expanded
                    if choice != 'my_meal' or not user_my_meals:
                        log_entry = DailyLog(
                            user_id=user.id,
                            log_date=log_date,
                            meal_name=meal_name,
                            amount_grams=amount_grams,
                            fdc_id=fdc_id,
                            my_food_id=my_food_id,
                            recipe_id=recipe_id,
                            serving_type=serving_type,
                            portion_id_fk=portion_id_fk
                        )
                        db.session.add(log_entry)
                        daily_logs_created += 1

                users_created += 1

                users_created += 1

            db.session.commit()
            print(f"Database seeded with {users_created} users, {my_foods_created} MyFoods, {check_ins_created} CheckIns, {recipes_created} Recipes, {my_meals_created} MyMeals, {my_meal_items_created} MyMealItems, {daily_logs_created} Daily Logs, and {exercise_logs_created} Exercise Logs.")

    @app.cli.command("seed-usda-portions")
    def seed_usda_portions_command():
        """Seeds USDA food portions into the unified portions table in the user database."""
        import csv
        import os
        import sqlite3 # For reading usda_data.db directly

        with app.app_context():
            print("Seeding USDA portions...")

            # 1. Delete existing USDA-linked portions from the user database
            # This ensures idempotency for USDA portions
            deleted_count = UnifiedPortion.query.filter(UnifiedPortion.fdc_id.isnot(None)).delete()
            db.session.commit()
            print(f"Deleted {deleted_count} existing USDA-linked portions from user_data.db.")

            usda_data_dir = 'usda_data'
            usda_db_file = os.path.join(os.getcwd(), 'usda_data.db')

            if not os.path.exists(usda_db_file):
                print(f"Error: USDA database not found at {usda_db_file}. Please run 'python import_usda_data.py' first.")
                return

            # Load measure units from CSV for efficient lookup
            measure_units = {}
            measure_unit_csv_path = os.path.join(usda_data_dir, 'measure_unit.csv')
            if not os.path.exists(measure_unit_csv_path):
                print(f"Error: measure_unit.csv not found at {measure_unit_csv_path}.")
                return
            with open(measure_unit_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    measure_units[row[0]] = row[1]
            print(f"Loaded {len(measure_units)} measure units from CSV.")

            portions_to_add = []
            food_portion_csv_path = os.path.join(usda_data_dir, 'food_portion.csv')

            if not os.path.exists(food_portion_csv_path):
                print(f"Error: food_portion.csv not found at {food_portion_csv_path}.")
                return

            with open(food_portion_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader) # Skip header
                for row in reader:
                    fdc_id = int(row[1])
                    seq_num = int(row[2]) if row[2] else None
                    amount_str = row[3]
                    measure_unit_id = row[4]
                    portion_description = row[5]
                    modifier = row[6]
                    gram_weight = float(row[7])

                    # Construct the full description string
                    desc_parts = []
                    if amount_str:
                        try:
                            amount_float = float(amount_str)
                            if amount_float.is_integer():
                                desc_parts.append(str(int(amount_float)))
                            else:
                                desc_parts.append(str(amount_float))
                        except ValueError:
                            desc_parts.append(amount_str)
                    
                    unit_name = measure_units.get(measure_unit_id)
                    if unit_name and measure_unit_id != '9999':
                        desc_parts.append(unit_name)

                    if portion_description:
                        desc_parts.append(portion_description)
                    
                    if modifier:
                        desc_parts.append(modifier)
                    
                    portion = UnifiedPortion(
                        fdc_id=fdc_id,
                        seq_num=seq_num,
                        amount=float(amount_str) if amount_str else None,
                        measure_unit_description=measure_units.get(measure_unit_id, "") if measure_unit_id != '9999' else "",
                        portion_description=portion_description,
                        modifier=modifier,
                        gram_weight=gram_weight
                    )
                    portions_to_add.append(portion)
            
            db.session.add_all(portions_to_add)
            db.session.commit()
            print(f"Successfully added {len(portions_to_add)} USDA portions to the user database.")

    return app
