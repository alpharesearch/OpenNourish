from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, SubmitField
from wtforms.validators import DataRequired, Optional
from datetime import date
from flask_login import current_user


class CheckInForm(FlaskForm):
    checkin_date = DateField(
        "Check-in Date", default=date.today, validators=[DataRequired()]
    )

    # Metric fields
    weight_kg = FloatField("Weight (kg)", validators=[Optional()])
    waist_cm = FloatField("Waist (cm)", validators=[Optional()])

    # US fields
    weight_lbs = FloatField("Weight (lbs)", validators=[Optional()])
    waist_in = FloatField("Waist (in)", validators=[Optional()])

    body_fat_percentage = FloatField("Body Fat (%)", validators=[Optional()])
    submit = SubmitField("Submit")

    def __init__(self, *args, **kwargs):
        super(CheckInForm, self).__init__(*args, **kwargs)
        if current_user.is_authenticated:
            if current_user.measurement_system == "us":
                del self.weight_kg
                del self.waist_cm
            else:  # metric
                del self.weight_lbs
                del self.waist_in

    def validate(self, extra_validators=None):
        # Call base FlaskForm validation first
        initial_validation = super().validate(extra_validators)

        # Custom validation for weight based on measurement system
        # Only require weight if it's a new entry or if the field is present in submitted data
        is_new_entry = not hasattr(self, "obj") or self.obj is None

        if current_user.measurement_system == "us":
            if self.weight_lbs.data is None and (
                is_new_entry or "weight_lbs" in self.form
            ):
                self.weight_lbs.errors.append("This field is required.")
                return False
        else:  # metric
            if self.weight_kg.data is None and (
                is_new_entry or "weight_kg" in self.form
            ):
                self.weight_kg.errors.append("This field is required.")
                return False

        return initial_validation
