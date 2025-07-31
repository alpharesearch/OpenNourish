from flask import Blueprint

usda_admin_bp = Blueprint('usda_admin', __name__)

from . import routes
