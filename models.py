from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# --- User-specific Models (Default Bind) ---

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Recipe(db.Model):
    __tablename__ = 'recipes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    user = db.relationship('User', backref=db.backref('recipes', lazy=True))
    ingredients = db.relationship('RecipeIngredient', backref='recipe', cascade="all, delete-orphan")

class RecipeIngredient(db.Model):
    __tablename__ = 'recipe_ingredients'
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipes.id'), nullable=False)
    fdc_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    serving_type = db.Column(db.String(50), nullable=False)

class DailyLog(db.Model):
    __tablename__ = 'daily_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False)
    fdc_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    serving_type = db.Column(db.String(50), nullable=False)
    user = db.relationship('User', backref=db.backref('daily_logs', lazy=True))


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