from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Optional

class AdminSettingsForm(FlaskForm):
    allow_registration = BooleanField('Allow New User Registrations?')
    submit = SubmitField('Save Settings')

from wtforms import RadioField

class EmailSettingsForm(FlaskForm):
    MAIL_CONFIG_SOURCE = RadioField('Configuration Source', choices=[('database', 'Database'), ('environment', 'Environment Variables')], default='database', validators=[DataRequired()])
    MAIL_SERVER = StringField('Mail Server', validators=[Optional()])
    MAIL_PORT = IntegerField('Mail Port', validators=[Optional()])
    MAIL_SECURITY_PROTOCOL = RadioField('Security Protocol', choices=[('none', 'None'), ('tls', 'TLS'), ('ssl', 'SSL')], default='tls', validators=[DataRequired()])
    MAIL_USERNAME = StringField('Mail Username', validators=[Optional()])
    MAIL_PASSWORD = PasswordField('Mail Password', validators=[Optional()])
    MAIL_FROM = StringField('Mail From Address', validators=[Optional(), Email()])
    MAIL_SUPPRESS_SEND = BooleanField('Suppress Email Sending (for development)')
    ENABLE_PASSWORD_RESET = BooleanField('Enable Password Reset Feature')
    ENABLE_EMAIL_VERIFICATION = BooleanField('Enable Email Verification Feature')
    submit = SubmitField('Save Email Settings')