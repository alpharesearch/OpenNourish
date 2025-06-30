# tests/conftest.py

import pytest
import os
import sys

# Add project root to path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from models import Food # Or whatever your models are named

@pytest.fixture(scope='session')
def app_with_db():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_BINDS'] = {
        'usda': 'sqlite:///:memory:'
    }
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture(scope='module')
def client(app_with_db):
    with app_with_db.test_client() as client:
        yield client