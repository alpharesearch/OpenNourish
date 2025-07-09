from flask import Blueprint

friends_bp = Blueprint('friends', __name__, template_folder='templates')

from . import routes