from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, DateField
from wtforms.validators import DataRequired, Optional
from wtforms_sqlalchemy.fields import QuerySelectField
from models import ExerciseActivity

def get_activities():
    return ExerciseActivity.query.all()

class ExerciseLogForm(FlaskForm):
    log_date = DateField('Date', validators=[DataRequired()])
    activity = QuerySelectField('Activity', query_factory=get_activities, get_label='name', allow_blank=True, blank_text='-- Manual Entry --')
    manual_description = StringField('Manual Description')
    duration_minutes = IntegerField('Duration (minutes)', validators=[DataRequired()])
    calories_burned = IntegerField('Calories Burned', validators=[Optional()])
    submit = SubmitField('Log Exercise')
