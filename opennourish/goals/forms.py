from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, RadioField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange
from config import Config

from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, RadioField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange
from config import Config

class GoalForm(FlaskForm):
    age = IntegerField('Age', validators=[Optional(), NumberRange(min=1, max=120)])
    gender = RadioField('Gender', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[Optional()])
    height_cm = FloatField('Height (cm)', validators=[Optional(), NumberRange(min=50, max=250)])
    weight_kg = FloatField('Current Weight (kg)', validators=[Optional(), NumberRange(min=1, max=300)])
    body_fat_percentage = FloatField('Body Fat % (optional)', validators=[Optional(), NumberRange(min=0, max=100)])
    diet_preset = SelectField('Diet Preset', choices=[('', '-- Select a Preset --')] + [(key, key) for key in Config.DIET_PRESETS.keys()], validators=[Optional()])
    calories = FloatField('Calories', validators=[DataRequired()])
    protein = FloatField('Protein (g)', validators=[DataRequired()])
    carbs = FloatField('Carbohydrates (g)', validators=[DataRequired()])
    fat = FloatField('Fat (g)', validators=[DataRequired()])