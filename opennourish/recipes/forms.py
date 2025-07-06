from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional, NumberRange

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired()])
    servings = FloatField('Servings', validators=[DataRequired(), NumberRange(min=0.01)])
    instructions = TextAreaField('Instructions', validators=[Optional()])
    submit = SubmitField('Save Recipe')