from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Optional


class EditFastForm(FlaskForm):
    start_time = DateTimeLocalField(
        "Start Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M"
    )
    end_time = DateTimeLocalField(
        "End Time", validators=[Optional()], format="%Y-%m-%dT%H:%M"
    )
    submit = SubmitField("Save")
