from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, TextAreaField, BooleanField, SelectField
from wtforms.validators import DataRequired, Optional, NumberRange

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired()])
    food_category = SelectField('Category', coerce=lambda x: int(x) if x else None, validators=[Optional()])
    servings = FloatField('Servings', validators=[DataRequired(), NumberRange(min=0.01)])
    instructions = TextAreaField('Instructions', validators=[Optional()])
    upc = StringField('UPC Code', validators=[Optional()])
    is_public = BooleanField('Make this recipe public and searchable by other users?')
    submit = SubmitField('Save Recipe')