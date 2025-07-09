from flask import Blueprint

diary_bp = Blueprint('diary', __name__)

from . import routes
