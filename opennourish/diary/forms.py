from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FloatField
from wtforms.validators import DataRequired, Length, NumberRange

class MealForm(FlaskForm):
    name = StringField('Meal Name', validators=[DataRequired(), Length(min=2, max=100)])
    submit = SubmitField('Update Name')

class DailyLogForm(FlaskForm):
    amount = FloatField('Amount (grams)', validators=[DataRequired(), NumberRange(min=0.1)])
    submit = SubmitField('Update Entry')