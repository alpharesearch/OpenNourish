from flask_wtf import FlaskForm
from wtforms import RadioField, IntegerField, FloatField, SelectField, SubmitField, StringField
from wtforms.validators import DataRequired, NumberRange, Optional, Email, ValidationError
from models import User

class MeasurementSystemForm(FlaskForm):
    measurement_system = RadioField(
        'Select Measurement System',
        choices=[('metric', 'Metric (kg, cm)'), ('us', 'US (lbs, ft/in)')],
        default='metric',
        validators=[DataRequired()]
    )
    theme_preference = SelectField(
        'Theme Preference',
        choices=[('light', 'Light'), ('dark', 'Dark')],
        default='light',
        validators=[DataRequired()]
    )
    submit = SubmitField('Next')

class PersonalInfoForm(FlaskForm):
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=1, max=120)])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[DataRequired()])
    
    # Height fields for Metric
    height_cm = FloatField('Height (cm)', validators=[Optional(), NumberRange(min=50, max=250)])
    
    # Height fields for US
    height_ft = IntegerField('Height (feet)', validators=[Optional(), NumberRange(min=1, max=8)])
    height_in = FloatField('Height (inches)', validators=[Optional(), NumberRange(min=0, max=11.9)])

    # Weight fields for Metric
    weight_kg = FloatField('Weight (kg)', validators=[Optional(), NumberRange(min=20, max=600)])
    
    # Weight fields for US
    weight_lbs = FloatField('Weight (lbs)', validators=[Optional(), NumberRange(min=40, max=1300)])

    body_fat_percentage = FloatField('Body Fat % (Optional)', validators=[Optional(), NumberRange(min=1, max=60)])

    # Waist fields for Metric
    waist_cm = FloatField('Waist (cm) (Optional)', validators=[Optional(), NumberRange(min=30, max=200)])

    # Waist fields for US
    waist_in = FloatField('Waist (in) (Optional)', validators=[Optional(), NumberRange(min=10, max=80)])

    submit = SubmitField('Next')

class InitialGoalsForm(FlaskForm):
    diet_preset = SelectField('Diet Preset', choices=[], validators=[Optional()])
    calories = FloatField('Daily Calories (kcal)', validators=[DataRequired(), NumberRange(min=500, max=10000)])
    protein = FloatField('Daily Protein (g)', validators=[DataRequired(), NumberRange(min=10, max=1000)])
    carbs = FloatField('Daily Carbohydrates (g)', validators=[DataRequired(), NumberRange(min=10, max=1000)])
    fat = FloatField('Daily Fat (g)', validators=[DataRequired(), NumberRange(min=10, max=500)])

    # Weight Goal
    weight_goal_kg = FloatField('Weight Goal (kg)', validators=[Optional(), NumberRange(min=20, max=600)])
    weight_goal_lbs = FloatField('Weight Goal (lbs)', validators=[Optional(), NumberRange(min=40, max=1300)])

    submit = SubmitField('Finish Setup')
