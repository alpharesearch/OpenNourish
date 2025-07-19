import os
import secrets
from dotenv import load_dotenv
import json
from models import db, SystemSetting
from constants import DIET_PRESETS, CORE_NUTRIENT_IDS

basedir = os.path.abspath(os.path.dirname(__file__))
# Define the path for data that needs to persist across container restarts
persistent_dir = os.path.join(basedir, 'persistent')
load_dotenv(os.path.join(basedir, '.env'))

def get_or_create_secret_key(persistent_path):
    """
    Checks for a secret key in the environment, then a file.
    If neither exists, generates and saves a new one.
    """
    # 1. Check environment variable first (highest priority)
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        print("INFO: Loading SECRET_KEY from environment variable.")
        return env_key
    
    # Ensure the persistent directory exists
    os.makedirs(persistent_path, exist_ok=True)
    key_file_path = os.path.join(persistent_path, 'secret_key.txt')

    # 2. Check for the key file
    if os.path.exists(key_file_path):
        print(f"INFO: Loading SECRET_KEY from {key_file_path}")
        with open(key_file_path, 'r') as f:
            return f.read().strip()
            
    # 3. If no key found, generate, save, and return a new one
    else:
        print(f"INFO: No SECRET_KEY found. Generating and saving a new one to {key_file_path}")
        new_key = secrets.token_hex(24) # 48-character hex string
        with open(key_file_path, 'w') as f:
            f.write(new_key)
        return new_key

from sqlalchemy import inspect

def get_setting_from_db(app, key, default=None, decrypt=False):
    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table('system_settings'):
            return default # Table doesn't exist yet, return default

        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            value = setting.value
            if decrypt and value:
                try:
                    from opennourish.utils import decrypt_value # Local import to avoid circular dependency
                    return decrypt_value(value, os.environ.get('ENCRYPTION_KEY'))
                except Exception as e:
                    print(f"Error decrypting setting {key}: {e}")
                    return default
            return value
        return default

class Config:
    SECRET_KEY = get_or_create_secret_key(persistent_dir)
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application. Please set it in your .env file or environment variables.")

    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
    if not ENCRYPTION_KEY:
        raise ValueError("No ENCRYPTION_KEY set for Flask application. Please set it in your .env file or environment variables.")

    # These will be loaded from the database after app context is available
    MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_FROM = os.environ.get('MAIL_FROM', 'no-reply@example.com')
    MAIL_SUPPRESS_SEND = os.environ.get('MAIL_SUPPRESS_SEND', 'True').lower() == 'true'
    ENABLE_PASSWORD_RESET = os.environ.get('ENABLE_PASSWORD_RESET', 'False').lower() == 'true'

    @property
    def ALLOW_REGISTRATION(self):
        from opennourish.utils import get_allow_registration_status
        return get_allow_registration_status()

    # Point the database URIs to the persistent directory
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(persistent_dir, 'user_data.db')
    SQLALCHEMY_BINDS = {
        'usda': os.environ.get('USDA_DATABASE_URL') or 'sqlite:///' + os.path.join(persistent_dir, 'usda_data.db')
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DIET_PRESETS = DIET_PRESETS
    CORE_NUTRIENT_IDS = CORE_NUTRIENT_IDS
