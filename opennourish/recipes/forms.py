from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, HiddenField, IntegerField, FloatField
from wtforms.validators import DataRequired, NumberRange

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired()])
    instructions = TextAreaField('Instructions', validators=[DataRequired()])
    servings = FloatField('Servings', default=1, validators=[DataRequired(), NumberRange(min=0.1)])
    submit = SubmitField('Save Recipe')

class IngredientForm(FlaskForm):
    food_type = HiddenField('Food Type')
    submit = SubmitField('Add Ingredient')

class AddToLogForm(FlaskForm):
    servings = IntegerField('Number of Servings', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Add to Diary')


class RecipePortionForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
