from flask_wtf import FlaskForm
from wtforms import BooleanField, SubmitField

class AdminSettingsForm(FlaskForm):
    allow_registration = BooleanField('Allow New User Registrations?')
    submit = SubmitField('Save Settings')