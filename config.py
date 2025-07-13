import os
import secrets
from dotenv import load_dotenv
import json

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

class Config:
    SECRET_KEY = get_or_create_secret_key(persistent_dir)
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application. Please set it in your .env file or environment variables.")

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
    DIET_PRESETS = {
        'SAD': {'protein': 0.15, 'carbs': 0.50, 'fat': 0.35},
        'Keto': {'protein': 0.20, 'carbs': 0.05, 'fat': 0.75},
        'Paleo': {'protein': 0.30, 'carbs': 0.30, 'fat': 0.40},
        'Mediterranean': {'protein': 0.20, 'carbs': 0.40, 'fat': 0.40}
    }
    CORE_NUTRIENT_IDS = {
        'calories': 1008,
        'protein': 1003,
        'carbs': 1005,
        'fat': 1004,
        'saturated_fat': 1258,
        'trans_fat': 1257,
        'cholesterol': 1253,
        'sodium': 1093,
        'fiber': 1079,
        'sugars': 2000,
        'vitamin_d': 1110,
        'calcium': 1087,
        'iron': 1089,
        'potassium': 1092
    }
