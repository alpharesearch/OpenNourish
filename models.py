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


class MeasureUnit(db.Model):
    __tablename__ = 'measure_units'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Portion(db.Model):
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
