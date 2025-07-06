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
    amount = FloatField('Amount', validators=[DataRequired()])
    measure_unit_description = StringField('Unit (e.g., cup, slice)', validators=[DataRequired()])
    description = StringField('Description (e.g., large, chopped)')
    modifier = StringField('Modifier (e.g., raw, cooked)')
    gram_weight = FloatField('Gram Weight', validators=[DataRequired(), NumberRange(min=0.1)])
    submit = SubmitField('Add Portion')
