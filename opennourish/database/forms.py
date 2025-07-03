from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField
from wtforms.validators import DataRequired, NumberRange

class MyFoodForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
    calories = FloatField('Calories (per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    protein = FloatField('Protein (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    carbs = FloatField('Carbohydrates (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    fat = FloatField('Fat (g per 100g)', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Add Food')