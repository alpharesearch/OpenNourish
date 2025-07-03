from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, SubmitField
from wtforms.validators import DataRequired
from datetime import date

class CheckInForm(FlaskForm):
    checkin_date = DateField('Check-in Date', default=date.today, validators=[DataRequired()])
    weight_kg = FloatField('Weight (kg)', validators=[DataRequired()])
    body_fat_percentage = FloatField('Body Fat (%)')
    waist_cm = FloatField('Waist (cm)')
    submit = SubmitField('Submit')
