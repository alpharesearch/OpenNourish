from flask_wtf import FlaskForm
from wtforms import FloatField
from wtforms.validators import DataRequired

class GoalForm(FlaskForm):
    calories = FloatField('Calories', validators=[DataRequired()])
    protein = FloatField('Protein (g)', validators=[DataRequired()])
    carbs = FloatField('Carbohydrates (g)', validators=[DataRequired()])
    fat = FloatField('Fat (g)', validators=[DataRequired()])