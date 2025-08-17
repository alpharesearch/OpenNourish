from flask import Blueprint

undo_bp = Blueprint("undo", __name__)

from . import routes
