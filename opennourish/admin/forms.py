from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField, PasswordField, SubmitField, RadioField
from wtforms.validators import DataRequired, Email, Optional, ValidationError

class AdminSettingsForm(FlaskForm):
    allow_registration = BooleanField('Allow New User Registrations?')
    submit = SubmitField('Save Settings')

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

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False

        if self.MAIL_CONFIG_SOURCE.data == 'database':
            # Only require mail server settings if either password reset or email verification is enabled
            if self.ENABLE_PASSWORD_RESET.data or self.ENABLE_EMAIL_VERIFICATION.data:
                if not self.MAIL_SERVER.data:
                    self.MAIL_SERVER.errors.append('Mail Server is required when enabling email features.')
                if not self.MAIL_PORT.data:
                    self.MAIL_PORT.errors.append('Mail Port is required when enabling email features.')
                if not self.MAIL_FROM.data:
                    self.MAIL_FROM.errors.append('Mail From Address is required when enabling email features.')

        return len(self.errors) == 0