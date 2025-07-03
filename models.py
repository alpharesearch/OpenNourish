from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

db = SQLAlchemy()

# --- User-specific Models (Default Bind) ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    goal = db.relationship('UserGoal', backref='user', uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class UserGoal(db.Model):
    __tablename__ = 'user_goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    calories = db.Column(db.Float, default=2000)
    protein = db.Column(db.Float, default=150)
    carbs = db.Column(db.Float, default=250)
    fat = db.Column(db.Float, default=60)

class CheckIn(db.Model):
    __tablename__ = 'check_ins'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    checkin_date = db.Column(db.Date, default=date.today)
    weight_kg = db.Column(db.Float)
    body_fat_percentage = db.Column(db.Float)
    waist_cm = db.Column(db.Float)

class MyFood(db.Model):
    __tablename__ = 'my_foods'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String)
    calories_per_100g = db.Column(db.Float)
    protein_per_100g = db.Column(db.Float)
    carbs_per_100g = db.Column(db.Float)
    fat_per_100g = db.Column(db.Float)

class DailyLog(db.Model):
    __tablename__ = 'daily_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False)
    meal_name = db.Column(db.String)
    fdc_id = db.Column(db.Integer, nullable=True)
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    amount_grams = db.Column(db.Float)

class Recipe(db.Model):
    __tablename__ = 'recipes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String)
    instructions = db.Column(db.Text)
    ingredients = db.relationship('RecipeIngredient', backref='recipe', cascade="all, delete-orphan")

class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    fdc_id = db.Column(db.Integer, nullable=True)
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    amount_grams = db.Column(db.Float)

    my_food = db.relationship('MyFood')

    @property
    def food(self):
        if self.fdc_id:
            return db.session.get(Food, self.fdc_id)
        return None

class MyMeal(db.Model):
    __tablename__ = 'my_meals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    items = db.relationship('MyMealItem', backref='meal', cascade="all, delete-orphan")

class MyMealItem(db.Model):
    __tablename__ = 'my_meal_items'
    id = db.Column(db.Integer, primary_key=True)
    my_meal_id = db.Column(db.Integer, db.ForeignKey('my_meals.id'), nullable=False)
    fdc_id = db.Column(db.Integer, nullable=True)
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    amount_grams = db.Column(db.Float)
    
    my_food = db.relationship('MyFood')
    
    @property
    def food(self):
        if self.fdc_id:
            return db.session.get(Food, self.fdc_id)
        return None



# --- USDA Data Models (USDA Bind) ---

class Food(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'foods'
    fdc_id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String, nullable=False)
    upc = db.Column(db.String, unique=True)
    ingredients = db.Column(db.String)
    nutrients = db.relationship('FoodNutrient', backref='food')
    portions = db.relationship('Portion', backref='food')

class Nutrient(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'nutrients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    unit_name = db.Column(db.String, nullable=False)

class FoodNutrient(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'food_nutrients'
    fdc_id = db.Column(db.Integer, db.ForeignKey('foods.fdc_id'), primary_key=True)
    nutrient_id = db.Column(db.Integer, db.ForeignKey('nutrients.id'), primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    nutrient = db.relationship('Nutrient', backref='food_nutrients')


class MeasureUnit(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'measure_units'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Portion(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'portions'
    id = db.Column(db.Integer, primary_key=True)
    fdc_id = db.Column(db.Integer, db.ForeignKey('foods.fdc_id'), nullable=False)
    seq_num = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float)
    measure_unit_id = db.Column(db.Integer, db.ForeignKey('measure_units.id'), nullable=False)
    portion_description = db.Column(db.String)
    modifier = db.Column(db.String)
    gram_weight = db.Column(db.Float, nullable=False)
    measure_unit = db.relationship('MeasureUnit', backref='portions')
