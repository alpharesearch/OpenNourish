from flask import Blueprint

database_bp = Blueprint('database', __name__, template_folder='templates')

from . import routes
