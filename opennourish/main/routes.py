from flask import Blueprint, render_template, request, redirect, url_for, send_from_directory, current_app, jsonify
from flask_login import current_user
from models import db, Food, UnifiedPortion
from sqlalchemy.orm import sessionmaker
import subprocess
import tempfile
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@main_bp.route('/food/<int:fdc_id>')
def food_detail(fdc_id):
    q = request.args.get('q')
    current_app.logger.debug(f"Debug: In food_detail, received q: {q}")
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404

    # Manually fetch portions for this USDA food
    # Manually fetch portions for this USDA food
    DefaultSession = sessionmaker(bind=db.get_engine(bind=None))
    default_session = DefaultSession()

    try:
        portions = default_session.query(UnifiedPortion).filter_by(fdc_id=fdc_id).all()
    finally:
        default_session.close()

    return render_template('food_detail.html', food=food, search_term=q, portions=portions)

@main_bp.route('/upc/<barcode>')
def upc_search(barcode):
    food_row = db.session.execute(
        db.select(Food).filter_by(upc=barcode)
    ).first()

    if food_row:
        food_obj = food_row[0]
        
        # Query for portions related to this fdc_id
        portions = UnifiedPortion.query.filter_by(fdc_id=food_obj.fdc_id).all()
        portions_data = [
            {'id': p.id, 'description': p.full_description_str} 
            for p in portions
        ]

        return jsonify({
            'status': 'found',
            'fdc_id': food_obj.fdc_id,
            'description': food_obj.description,
            'detail_url': url_for('main.food_detail', fdc_id=food_obj.fdc_id),
            'portions': portions_data,
            'nutrition_label_svg_url': url_for('main.nutrition_label_svg', fdc_id=food_obj.fdc_id)
        })
    else:
        return jsonify({'status': 'not_found'}), 404

from opennourish.utils import generate_nutrition_label_pdf, generate_nutrition_label_svg

@main_bp.route('/generate_nutrition_label/<int:fdc_id>')
def generate_nutrition_label(fdc_id):
    return generate_nutrition_label_pdf(fdc_id)

@main_bp.route('/nutrition_label_svg/<int:fdc_id>')
def nutrition_label_svg(fdc_id):
    return generate_nutrition_label_svg(fdc_id)

@main_bp.route('/debug-proxy')
def debug_proxy():
    """
    A temporary route to debug ProxyFix by inspecting request headers and environment.
    """
    headers = dict(request.headers)
    environ = {key: value for key, value in request.environ.items() if key.upper() in [
        'wsgi.url_scheme'.upper(), 'HTTP_HOST', 'SERVER_NAME', 'SERVER_PORT', 
        'HTTP_X_FORWARDED_FOR', 'HTTP_X_FORWARDED_PROTO', 'HTTP_X_FORWARDED_HOST',
        'HTTP_X_FORWARDED_PORT', 'HTTP_X_FORWARDED_PREFIX'
    ]}
    
    debug_info = {
        "message": "ProxyFix Debug Information",
        "request.url": request.url,
        "request.url_root": request.url_root,
        "request.host_url": request.host_url,
        "request.host": request.host,
        "request.scheme": request.scheme,
        "request.headers": headers,
        "request.environ": environ
    }

    # Using the app logger to print the dictionary as a formatted string
    current_app.logger.info(f"PROXY_DEBUG: {debug_info}")

    return debug_info
