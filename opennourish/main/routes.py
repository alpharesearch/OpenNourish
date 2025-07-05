from flask import Blueprint, render_template, request, redirect, url_for, send_file
from flask_login import current_user
from models import db, Food
import subprocess
import tempfile
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@main_bp.route('/food/<int:fdc_id>')
def food_detail(fdc_id):
    q = request.args.get('q')
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404
    return render_template('food_detail.html', food=food, search_term=q)

@main_bp.route('/upc/<barcode>')
def upc_search(barcode):
    q = request.args.get('q')
    food = db.session.execute(
        db.select(Food).filter_by(upc=barcode)
    ).first()
    if food:
        return redirect(url_for('main.food_detail', fdc_id=food[0].fdc_id, q=q))
    else:
        return "UPC not found", 404

from opennourish.utils import generate_nutrition_label_pdf, generate_nutrition_label_svg

@main_bp.route('/generate_nutrition_label/<int:fdc_id>')
def generate_nutrition_label(fdc_id):
    return generate_nutrition_label_pdf(fdc_id)

@main_bp.route('/nutrition_label_svg/<int:fdc_id>')
def nutrition_label_svg(fdc_id):
    return generate_nutrition_label_svg(fdc_id)
