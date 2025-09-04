from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Optional, NumberRange


class MyFoodForm(FlaskForm):
    description = StringField("Description", validators=[DataRequired()])
    food_category = SelectField(
        "Category", coerce=lambda x: int(x) if x else None, validators=[Optional()]
    )
    servings = FloatField(
        "Servings", validators=[Optional(), NumberRange(min=0)], default=1.0
    )
    instructions = TextAreaField("Instructions", validators=[Optional()])
    fdc_id = StringField("USDA FDC ID", validators=[Optional()])
    upc = StringField("UPC Code", validators=[Optional()])
    ingredients = TextAreaField("Ingredients", validators=[Optional()])
    calories_per_100g = FloatField(
        "Calories (cal per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    protein_per_100g = FloatField(
        "Protein (g per 100g)", validators=[Optional(), NumberRange(min=0)]
    )
    carbs_per_100g = FloatField(
        "Carbohydrates (g per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    fat_per_100g = FloatField(
        "Fat (g per 100g)", validators=[Optional(), NumberRange(min=0)]
    )
    saturated_fat_per_100g = FloatField(
        "Saturated Fat (g per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    trans_fat_per_100g = FloatField(
        "Trans Fat (g per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    cholesterol_mg_per_100g = FloatField(
        "Cholesterol (mg per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    sodium_mg_per_100g = FloatField(
        "Sodium (mg per 100g)", validators=[Optional(), NumberRange(min=0)]
    )
    fiber_per_100g = FloatField(
        "Fiber (g per 100g)", validators=[Optional(), NumberRange(min=0)]
    )
    sugars_per_100g = FloatField(
        "Total Sugars (g per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    added_sugars_per_100g = FloatField(
        "Added Sugars (g per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    vitamin_d_mcg_per_100g = FloatField(
        "Vitamin D (mcg per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    calcium_mg_per_100g = FloatField(
        "Calcium (mg per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    iron_mg_per_100g = FloatField(
        "Iron (mg per 100g)", validators=[Optional(), NumberRange(min=0)]
    )
    potassium_mg_per_100g = FloatField(
        "Potassium (mg per 100g)",
        validators=[Optional(), NumberRange(min=0)],
    )
    submit = SubmitField("Save Food")


class PortionForm(FlaskForm):
    amount = FloatField("Amount", validators=[Optional(), NumberRange(min=0)])
    measure_unit_description = StringField("Unit", validators=[Optional()])
    portion_description = StringField("Description", validators=[Optional()])
    modifier = StringField("Modifier", validators=[Optional()])
    gram_weight = FloatField(
        "Gram Weight", validators=[DataRequired(), NumberRange(min=0.01)]
    )
    submit = SubmitField("Add Portion")
