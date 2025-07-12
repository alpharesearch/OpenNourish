import os
from dotenv import load_dotenv
import json

basedir = os.path.abspath(os.path.dirname(__file__))
# Define the path for data that needs to persist across container restarts
persistent_dir = os.path.join(basedir, 'persistent')
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

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
