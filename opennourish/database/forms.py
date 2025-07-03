from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField
from wtforms.validators import DataRequired, NumberRange

class MyFoodForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
    calories_per_100g = FloatField('Calories (per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    protein_per_100g = FloatField('Protein (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    carbs_per_100g = FloatField('Carbohydrates (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    fat_per_100g = FloatField('Fat (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Add Food')