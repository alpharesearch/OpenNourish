from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    BooleanField,
    SelectField,
    FloatField,
    RadioField,
)
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Optional
from models import User
from flask_login import current_user
from zoneinfo import available_timezones


class SettingsForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    age = FloatField("Age", validators=[Optional()])
    gender = SelectField(
        "Gender",
        choices=[("", "Select..."), ("Male", "Male"), ("Female", "Female")],
        validators=[Optional()],
    )

    # Fields for US Customary units
    height_ft = FloatField("Height (ft)", validators=[Optional()])
    height_in = FloatField("Height (in)", validators=[Optional()])

    # Field for Metric units
    height_cm = FloatField("Height (cm)", validators=[Optional()])

    measurement_system = RadioField(
        "Measurement System",
        choices=[("metric", "Metric (kg, cm)"), ("us", "US (lbs, ft/in)")],
        validators=[DataRequired()],
    )
    navbar_preference = SelectField(
        "Navbar Color",
        choices=[
            ("bg-dark navbar-dark", "Default Dark"),
            ("bg-primary navbar-dark", "Primary Blue"),
            ("bg-success navbar-dark", "Green"),
            ("bg-danger navbar-dark", "Red"),
            ("bg-light navbar-light", "Light Gray"),
            ("bg-white navbar-light", "White"),
        ],
        validators=[DataRequired()],
    )
    diary_default_view = SelectField(
        "Default Diary View",
        choices=[("today", "Today"), ("yesterday", "Yesterday")],
        validators=[DataRequired()],
    )
    theme_preference = SelectField(
        "Theme Preference",
        choices=[
            ("light", "Light Mode"),
            ("dark", "Dark Mode"),
            ("auto", "System Default"),
        ],
        validators=[DataRequired()],
    )
    meals_per_day = SelectField(
        "Meals Per Day",
        choices=[
            ("3", "3 (Breakfast, Lunch, Dinner)"),
            ("4", "4 (3 meals + Water)"),
            ("6", "6 (Breakfast, Snacks, Lunch, Snacks, Dinner, Snacks)"),
            ("7", "7 (6 meals + Water)"),
        ],
        validators=[DataRequired()],
    )
    is_private = BooleanField("Enable Unlisted Mode")
    week_start_day = SelectField(
        "Start of the Week",
        choices=[("Monday", "Monday"), ("Sunday", "Sunday"), ("Saturday", "Saturday")],
        validators=[DataRequired()],
    )
    timezone = SelectField(
        "Timezone", choices=[(tz, tz) for tz in sorted(available_timezones())]
    )
    submit = SubmitField("Save Settings")

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError("This email is already registered.")


class ChangePasswordForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired()])
    password2 = PasswordField(
        "Repeat Password", validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField("Change Password")


class DeleteAccountConfirmForm(FlaskForm):
    password = PasswordField("Current Password", validators=[DataRequired()])
    submit = SubmitField("Delete Account")
