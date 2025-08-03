from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, IntegerField, SubmitField
from wtforms.validators import Optional, NumberRange
from config import Config
from flask_login import current_user


class GoalForm(FlaskForm):
    age = IntegerField("Age", validators=[Optional(), NumberRange(min=1, max=120)])
    gender = SelectField(
        "Gender",
        choices=[("", "Select..."), ("Male", "Male"), ("Female", "Female")],
        validators=[Optional()],
    )

    # Metric fields
    height_cm = FloatField(
        "Height (cm)", validators=[Optional(), NumberRange(min=50, max=250)]
    )
    weight_kg = FloatField(
        "Current Weight (kg)", validators=[Optional(), NumberRange(min=1, max=300)]
    )

    # US fields
    height_ft = IntegerField(
        "Height (ft)", validators=[Optional(), NumberRange(min=1, max=8)]
    )
    height_in = FloatField(
        "Height (in)", validators=[Optional(), NumberRange(min=0, max=11.9)]
    )
    weight_lbs = FloatField(
        "Current Weight (lbs)", validators=[Optional(), NumberRange(min=1, max=700)]
    )

    body_fat_percentage = FloatField(
        "Body Fat % (optional)", validators=[Optional(), NumberRange(min=0, max=100)]
    )
    goal_modifier = SelectField(
        "Adjust Nutritional Goals",
        choices=[
            ("manual", "Manual Entry"),
            ("max_loss", "Max Loss"),
            ("safe_max_loss", "Safe Max Loss"),
            ("moderate_loss", "Moderate Loss"),
            ("maintain", "Maintain"),
            ("moderate_gain", "Moderate Gain"),
            ("safe_max_gain", "Safe Max Gain"),
        ],
        validators=[Optional()],
    )
    diet_preset = SelectField(
        "Diet Preset",
        choices=[("manual", "Manual Entry")]
        + [(key, key) for key in Config.DIET_PRESETS.keys()],
        validators=[Optional()],
    )
    calories = FloatField("Calories", validators=[Optional()])
    protein = FloatField("Protein (g)", validators=[Optional()])
    carbs = FloatField("Carbohydrates (g)", validators=[Optional()])
    fat = FloatField("Fat (g)", validators=[Optional()])

    # Exercise Goals
    calories_burned_goal_weekly = IntegerField(
        "Weekly Calories Burned Goal", validators=[Optional(), NumberRange(min=0)]
    )
    exercises_per_week_goal = IntegerField(
        "Weekly Exercise Frequency Goal", validators=[Optional(), NumberRange(min=0)]
    )
    minutes_per_exercise_goal = IntegerField(
        "Minutes Per Exercise Goal", validators=[Optional(), NumberRange(min=0)]
    )

    # Body Composition Goals
    weight_goal_kg = FloatField(
        "Target Weight (kg)", validators=[Optional(), NumberRange(min=1, max=300)]
    )
    body_fat_percentage_goal = FloatField(
        "Target Body Fat %", validators=[Optional(), NumberRange(min=0, max=100)]
    )
    waist_cm_goal = FloatField(
        "Target Waist Circumference (cm)",
        validators=[Optional(), NumberRange(min=1, max=200)],
    )

    # US Body Composition Fields
    weight_goal_lbs = FloatField(
        "Target Weight (lbs)", validators=[Optional(), NumberRange(min=1, max=700)]
    )
    waist_in_goal = FloatField(
        "Target Waist Circumference (in)",
        validators=[Optional(), NumberRange(min=1, max=100)],
    )

    default_fasting_hours = IntegerField(
        "Default Fasting Duration (hours)",
        validators=[Optional(), NumberRange(min=1, max=960)],
    )

    submit = SubmitField("Save Goals")

    def __init__(self, *args, **kwargs):
        super(GoalForm, self).__init__(*args, **kwargs)
        if current_user and current_user.is_authenticated:
            if current_user.measurement_system == "us":
                del self.height_cm
                del self.weight_kg
                del self.weight_goal_kg
                del self.waist_cm_goal
            else:  # metric
                del self.height_ft
                del self.height_in
                del self.weight_lbs
                del self.weight_goal_lbs
                del self.waist_in_goal
