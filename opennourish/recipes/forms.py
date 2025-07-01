from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, HiddenField, IntegerField
from wtforms.validators import DataRequired, NumberRange

class RecipeForm(FlaskForm):
    name = StringField('Recipe Name', validators=[DataRequired()])
    instructions = TextAreaField('Instructions', validators=[DataRequired()])
    submit = SubmitField('Save Recipe')

class IngredientForm(FlaskForm):
    food_id = HiddenField('Food ID', validators=[DataRequired()])
    food_type = HiddenField('Food Type', validators=[DataRequired()])
    amount = IntegerField('Amount (g)', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Add Ingredient')

class AddToLogForm(FlaskForm):
    servings = IntegerField('Number of Servings', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Add to Diary')
