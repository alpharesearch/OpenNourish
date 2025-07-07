from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, RadioField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange
from config import Config
from flask_login import current_user

class GoalForm(FlaskForm):
    age = IntegerField('Age', validators=[Optional(), NumberRange(min=1, max=120)])
    gender = SelectField('Gender', choices=[('', 'Select...'), ('Male', 'Male'), ('Female', 'Female')], validators=[Optional()])
    
    # Metric fields
    height_cm = FloatField('Height (cm)', validators=[Optional(), NumberRange(min=50, max=250)])
    weight_kg = FloatField('Current Weight (kg)', validators=[Optional(), NumberRange(min=1, max=300)])
    
    # US fields
    height_ft = IntegerField('Height (ft)', validators=[Optional(), NumberRange(min=1, max=8)])
    height_in = FloatField('Height (in)', validators=[Optional(), NumberRange(min=0, max=11.9)])
    weight_lbs = FloatField('Current Weight (lbs)', validators=[Optional(), NumberRange(min=1, max=700)])

    body_fat_percentage = FloatField('Body Fat % (optional)', validators=[Optional(), NumberRange(min=0, max=100)])
    diet_preset = SelectField('Diet Preset', choices=[('', '-- Select a Preset --')] + [(key, key) for key in Config.DIET_PRESETS.keys()], validators=[Optional()])
    calories = FloatField('Calories', validators=[Optional()])
    protein = FloatField('Protein (g)', validators=[Optional()])
    carbs = FloatField('Carbohydrates (g)', validators=[Optional()])
    fat = FloatField('Fat (g)', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super(GoalForm, self).__init__(*args, **kwargs)
        if current_user.is_authenticated:
            if current_user.measurement_system == 'us':
                del self.height_cm
                del self.weight_kg
            else: # metric
                del self.height_ft
                del self.height_in
                del self.weight_lbs