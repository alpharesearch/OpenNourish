from flask import Blueprint

exercise_bp = Blueprint('exercise', __name__)

from . import routes
