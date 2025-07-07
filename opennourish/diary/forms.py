from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FloatField, HiddenField, DateField, SelectField
from wtforms.validators import DataRequired, Length, NumberRange
from datetime import date

class MealForm(FlaskForm):
    name = StringField('Meal Name', validators=[DataRequired(), Length(min=2, max=100)])
    submit = SubmitField('Update Name')

class DailyLogForm(FlaskForm):
    amount = FloatField('Amount (grams)', validators=[DataRequired(), NumberRange(min=0.1)])
    submit = SubmitField('Update Entry')

class MealItemForm(FlaskForm):
    amount = FloatField('Amount (grams)', validators=[DataRequired(), NumberRange(min=0.1)])
    submit = SubmitField('Update Item')

class AddToLogForm(FlaskForm):
    food_id = HiddenField(validators=[DataRequired()])
    food_type = HiddenField(validators=[DataRequired()])
    quantity = FloatField('Quantity', validators=[DataRequired(), NumberRange(min=0.1)])
    meal_name = SelectField('Meal', choices=[
        ('Breakfast', 'Breakfast'),
        ('Lunch', 'Lunch'),
        ('Dinner', 'Dinner'),
        ('Snack', 'Snack')
    ], validators=[DataRequired()])
    log_date = DateField('Date', default=date.today, format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Add to Diary')