from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FloatField, RadioField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Optional, EqualTo

class SettingsForm(FlaskForm):
    age = FloatField('Age', validators=[Optional()])
    gender = SelectField('Gender', choices=[('', 'Select...'), ('Male', 'Male'), ('Female', 'Female')], validators=[Optional()])
    
    # Fields for US Customary units
    height_ft = FloatField('Height (ft)', validators=[Optional()])
    height_in = FloatField('Height (in)', validators=[Optional()])
    
    # Field for Metric units
    height_cm = FloatField('Height (cm)', validators=[Optional()])

    measurement_system = RadioField(
        'Measurement System',
        choices=[('metric', 'Metric (kg, cm)'), ('us', 'US (lbs, ft/in)')],
        validators=[DataRequired()]
    )
    navbar_preference = SelectField(
        'Navbar Color',
        choices=[
            ('bg-dark navbar-dark', 'Default Dark'),
            ('bg-primary navbar-dark', 'Primary Blue'),
            ('bg-success navbar-dark', 'Green'),
            ('bg-danger navbar-dark', 'Red'),
            ('bg-light navbar-light', 'Light Gray'),
            ('bg-white navbar-light', 'White')
        ],
        validators=[DataRequired()]
    )
    diary_default_view = SelectField(
        'Default Diary View',
        choices=[
            ('today', 'Today'),
            ('yesterday', 'Yesterday')
        ],
        validators=[DataRequired()]
    )
    theme_preference = SelectField(
        'Theme Preference',
        choices=[
            ('light', 'Light Mode'),
            ('dark', 'Dark Mode'),
            ('auto', 'System Default')
        ],
        validators=[DataRequired()]
    )
    meals_per_day = SelectField(
        'Meals Per Day',
        choices=[('3', '3 (Breakfast, Lunch, Dinner)'), ('6', '6 (Breakfast, Snacks, Lunch, Snacks, Dinner, Snacks)')],
        validators=[DataRequired()]
    )
    submit = SubmitField('Save Settings')

class ChangePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Change Password')