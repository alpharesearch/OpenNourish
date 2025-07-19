from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Optional

class AdminSettingsForm(FlaskForm):
    allow_registration = BooleanField('Allow New User Registrations?')
    submit = SubmitField('Save Settings')

class EmailSettingsForm(FlaskForm):
    MAIL_SERVER = StringField('Mail Server', validators=[Optional()])
    MAIL_PORT = IntegerField('Mail Port', validators=[Optional()])
    MAIL_USE_TLS = BooleanField('Use TLS/SSL')
    MAIL_USERNAME = StringField('Mail Username', validators=[Optional()])
    MAIL_PASSWORD = PasswordField('Mail Password', validators=[Optional()])
    MAIL_FROM = StringField('Mail From Address', validators=[Optional(), Email()])
    MAIL_SUPPRESS_SEND = BooleanField('Suppress Email Sending (for development)')
    ENABLE_PASSWORD_RESET = BooleanField('Enable Password Reset Feature')
    submit = SubmitField('Save Email Settings')