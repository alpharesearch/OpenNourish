import os
from dotenv import load_dotenv
import json

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # Load ALLOW_REGISTRATION from instance/settings.json, then environment, then default
    _settings_file = os.path.join(basedir, 'instance', 'settings.json')
    _allow_registration_from_file = None
    if os.path.exists(_settings_file):
        with open(_settings_file, 'r') as f:
            try:
                settings_data = json.load(f)
                _allow_registration_from_file = settings_data.get('ALLOW_REGISTRATION')
            except json.JSONDecodeError:
                pass # File is empty or invalid JSON, proceed to environment variable

    if _allow_registration_from_file is not None:
        ALLOW_REGISTRATION = _allow_registration_from_file
    else:
        ALLOW_REGISTRATION = os.environ.get('ALLOW_REGISTRATION', 'True').lower() in ('true', '1', 't')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'user_data.db')
    SQLALCHEMY_BINDS = {
        'usda': os.environ.get('USDA_DATABASE_URL') or
                'sqlite:///' + os.path.join(basedir, 'usda_data.db')
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

