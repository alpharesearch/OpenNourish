from flask import Blueprint

diary_bp = Blueprint('diary', __name__, template_folder='templates')

from . import routes
