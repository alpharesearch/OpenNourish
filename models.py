from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
from sqlalchemy import and_

db = SQLAlchemy()

# --- User-specific Models (Default Bind) ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(10), nullable=True) # 'Male', 'Female'
    measurement_system = db.Column(db.String(10), default='metric', nullable=False) # 'metric' or 'us'
    height_cm = db.Column(db.Float, nullable=True)
    goal = db.relationship('UserGoal', backref='user', uselist=False)
    sent_friend_requests = db.relationship(
        'Friendship',
        foreign_keys='Friendship.requester_id',
        backref='requester',
        lazy='dynamic'
    )
    received_friend_requests = db.relationship(
        'Friendship',
        foreign_keys='Friendship.receiver_id',
        backref='receiver',
        lazy='dynamic'
    )

    @property
    def friends(self):
        sent_requests = db.session.query(Friendship).filter_by(
            requester_id=self.id, status='accepted'
        ).all()
        received_requests = db.session.query(Friendship).filter_by(
            receiver_id=self.id, status='accepted'
        ).all()
        friend_ids = [fr.receiver_id for fr in sent_requests] + [fr.requester_id for fr in received_requests]
        return User.query.filter(User.id.in_(friend_ids)).all()

    @property
    def pending_requests_sent(self):
        return self.sent_friend_requests.filter_by(status='pending').all()

    @property
    def pending_requests_received(self):
        return self.received_friend_requests.filter_by(status='pending').all()

    @property
    def is_admin(self):
        return self.id == 1

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Friendship(db.Model):
    __tablename__ = 'friendships'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String, default='pending', nullable=False) # 'pending', 'accepted'
    timestamp = db.Column(db.DateTime, default=db.func.now())

    __table_args__ = (db.UniqueConstraint('requester_id', 'receiver_id', name='uq_friendship'),)

class UserGoal(db.Model):
    __tablename__ = 'user_goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    calories = db.Column(db.Float, default=2000)
    protein = db.Column(db.Float, default=150)
    carbs = db.Column(db.Float, default=250)
    fat = db.Column(db.Float, default=60)
    calories_burned_goal_weekly = db.Column(db.Integer, default=0)
    exercises_per_week_goal = db.Column(db.Integer, default=0)
    minutes_per_exercise_goal = db.Column(db.Integer, default=0)
    weight_goal_kg = db.Column(db.Float, nullable=True)
    body_fat_percentage_goal = db.Column(db.Float, nullable=True)
    waist_cm_goal = db.Column(db.Float, nullable=True)

class CheckIn(db.Model):
    __tablename__ = 'check_ins'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    checkin_date = db.Column(db.Date, default=date.today)
    weight_kg = db.Column(db.Float)
    body_fat_percentage = db.Column(db.Float)
    waist_cm = db.Column(db.Float)

class UnifiedPortion(db.Model):
    __tablename__ = 'portions'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys to link to different parent types
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    fdc_id = db.Column(db.Integer, index=True, nullable=True) # Logical link to usda_data.db

    # Common fields
    seq_num = db.Column(db.Integer)
    amount = db.Column(db.Float)
    measure_unit_description = db.Column(db.String)
    portion_description = db.Column(db.String)
    modifier = db.Column(db.String)
    gram_weight = db.Column(db.Float, nullable=False)

    @property
    def full_description_str(self):
        parts = []
        if self.amount:
            # Format amount to avoid trailing .0 if it's a whole number
            amount_str = f'{self.amount:.0f}' if self.amount == int(self.amount) else f'{self.amount:.2f}'
            parts.append(amount_str)
        if self.measure_unit_description:
            parts.append(self.measure_unit_description)
        if self.portion_description:
            parts.append(self.portion_description)
        if self.modifier:
            parts.append(f"{self.modifier}")
        
        return " ".join(parts).strip() or "g"


class MyFood(db.Model):
    __tablename__ = 'my_foods'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String)
    ingredients = db.Column(db.Text, nullable=True)
    fdc_id = db.Column(db.Integer, nullable=True)
    upc = db.Column(db.String, nullable=True)
    calories_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    protein_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    carbs_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    fat_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    saturated_fat_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    trans_fat_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    cholesterol_mg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    sodium_mg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    fiber_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    sugars_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    vitamin_d_mcg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    calcium_mg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    iron_mg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    potassium_mg_per_100g = db.Column(db.Float, nullable=False, default=0.0)
    portions = db.relationship('UnifiedPortion', foreign_keys=[UnifiedPortion.my_food_id], backref='my_food', cascade='all, delete-orphan')
    user = db.relationship('User')


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
    serving_type = db.Column(db.String(50), default='g')
    portion_id_fk = db.Column(db.Integer, db.ForeignKey('portions.id'), nullable=True)

class Recipe(db.Model):
    __tablename__ = 'recipes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String)
    is_public = db.Column(db.Boolean, default=False, nullable=False, index=True)
    instructions = db.Column(db.Text)
    servings = db.Column(db.Float, default=1)
    ingredients = db.relationship('RecipeIngredient', backref='recipe', cascade="all, delete-orphan", foreign_keys='RecipeIngredient.recipe_id')
    portions = db.relationship('UnifiedPortion', foreign_keys=[UnifiedPortion.recipe_id], backref='recipe', cascade='all, delete-orphan')
    user = db.relationship('User')

class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    fdc_id = db.Column(db.Integer, nullable=True)
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    recipe_id_link = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True) # For nested recipes
    amount_grams = db.Column(db.Float)
    serving_type = db.Column(db.String(50), default='g')
    portion_id_fk = db.Column(db.Integer, db.ForeignKey('portions.id'), nullable=True)

    @property
    def food(self):
        return db.session.get(Food, self.fdc_id)
    my_food = db.relationship('MyFood', foreign_keys=[my_food_id])
    linked_recipe = db.relationship('Recipe', foreign_keys=[recipe_id_link])

class MyMeal(db.Model):
    __tablename__ = 'my_meals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String, nullable=False)
    usage_count = db.Column(db.Integer, default=0, nullable=False)
    items = db.relationship('MyMealItem', backref='meal', cascade="all, delete-orphan")
    user = db.relationship('User')

class MyMealItem(db.Model):
    __tablename__ = 'my_meal_items'
    id = db.Column(db.Integer, primary_key=True)
    my_meal_id = db.Column(db.Integer, db.ForeignKey('my_meals.id'), nullable=False)
    fdc_id = db.Column(db.Integer, nullable=True)
    my_food_id = db.Column(db.Integer, db.ForeignKey('my_foods.id'), nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=True)
    amount_grams = db.Column(db.Float)

    @property
    def food(self):
        return db.session.get(Food, self.fdc_id)
    my_food = db.relationship('MyFood', foreign_keys=[my_food_id], uselist=False)
    recipe = db.relationship('Recipe', foreign_keys=[recipe_id], uselist=False)

class ExerciseActivity(db.Model):
    __tablename__ = 'exercise_activities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    met_value = db.Column(db.Float, nullable=False)

class ExerciseLog(db.Model):
    __tablename__ = 'exercise_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    log_date = db.Column(db.Date, default=date.today)
    activity_id = db.Column(db.Integer, db.ForeignKey('exercise_activities.id'), nullable=True)
    manual_description = db.Column(db.String, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False)
    calories_burned = db.Column(db.Integer, nullable=False)

    activity = db.relationship('ExerciseActivity')


# --- USDA Data Models (USDA Bind) ---

class Food(db.Model):
    __bind_key__ = 'usda'
    __tablename__ = 'foods'
    fdc_id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String, nullable=False)
    upc = db.Column(db.String, unique=True)
    ingredients = db.Column(db.String)
    portions = db.relationship(
        'UnifiedPortion',
        primaryjoin="foreign(UnifiedPortion.fdc_id) == Food.fdc_id",
        viewonly=True,
        uselist=True
    )
    nutrients = db.relationship('FoodNutrient', backref='food')

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


