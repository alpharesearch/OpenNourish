from flask import Blueprint

my_foods_bp = Blueprint('my_foods', __name__, template_folder='templates')

from . import routes