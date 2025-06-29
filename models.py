from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Food(db.Model):
    __tablename__ = 'foods'
    fdc_id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String, nullable=False)
    upc = db.Column(db.String, unique=True)
    ingredients = db.Column(db.String)
    nutrients = db.relationship('FoodNutrient', backref='food')
    portions = db.relationship('Portion', backref='food')

class Nutrient(db.Model):
    __tablename__ = 'nutrients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    unit_name = db.Column(db.String, nullable=False)

class FoodNutrient(db.Model):
    __tablename__ = 'food_nutrients'
    fdc_id = db.Column(db.Integer, db.ForeignKey('foods.fdc_id'), primary_key=True)
    nutrient_id = db.Column(db.Integer, db.ForeignKey('nutrients.id'), primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    nutrient = db.relationship('Nutrient', backref='food_nutrients')


class Portion(db.Model):
    __tablename__ = 'portions'
    # Define a composite primary key because the table doesn't have a single one
    fdc_id = db.Column(db.Integer, db.ForeignKey('foods.fdc_id'), primary_key=True)
    measure_description = db.Column(db.String, primary_key=True)
    gram_weight = db.Column(db.Float, nullable=False)
