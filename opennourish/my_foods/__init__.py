from flask import Blueprint

my_foods_bp = Blueprint('my_foods', __name__)

from . import routes