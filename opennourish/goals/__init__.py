from flask import Blueprint

bp = Blueprint("goals", __name__)

from opennourish.goals import routes
