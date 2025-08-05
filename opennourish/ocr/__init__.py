from flask import Blueprint

ocr_bp = Blueprint("ocr", __name__)

from . import routes
