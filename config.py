import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'user_data.db')
    SQLALCHEMY_BINDS = {
        'usda': os.environ.get('USDA_DATABASE_URL') or
                'sqlite:///' + os.path.join(basedir, 'usda_data.db')
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
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

