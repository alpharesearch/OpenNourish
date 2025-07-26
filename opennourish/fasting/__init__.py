from flask import Blueprint

fasting_bp = Blueprint('fasting', __name__, template_folder='templates')

from . import routes
