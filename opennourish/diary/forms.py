from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class MealForm(FlaskForm):
    name = StringField('Meal Name', validators=[DataRequired(), Length(min=2, max=100)])
    submit = SubmitField('Update Name')
