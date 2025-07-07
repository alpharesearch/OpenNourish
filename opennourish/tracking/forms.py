from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, SubmitField
from wtforms.validators import DataRequired, Optional
from datetime import date
from flask_login import current_user

class CheckInForm(FlaskForm):
    checkin_date = DateField('Check-in Date', default=date.today, validators=[DataRequired()])
    
    # Metric fields
    weight_kg = FloatField('Weight (kg)', validators=[Optional()])
    waist_cm = FloatField('Waist (cm)', validators=[Optional()])

    # US fields
    weight_lbs = FloatField('Weight (lbs)', validators=[Optional()])
    waist_in = FloatField('Waist (in)', validators=[Optional()])

    body_fat_percentage = FloatField('Body Fat (%)', validators=[Optional()])
    submit = SubmitField('Submit')

    def __init__(self, *args, **kwargs):
        super(CheckInForm, self).__init__(*args, **kwargs)
        if current_user.is_authenticated:
            if current_user.measurement_system == 'us':
                del self.weight_kg
                del self.waist_cm
            else: # metric
                del self.weight_lbs
                del self.waist_in

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        
        if current_user.measurement_system == 'us':
            if self.weight_lbs.data is None:
                self.weight_lbs.errors.append('This field is required.')
                return False
        else:
            if self.weight_kg.data is None:
                self.weight_kg.errors.append('This field is required.')
                return False
        return True
