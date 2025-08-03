from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    current_app,
    jsonify,
    flash,
)
from flask_login import current_user
from models import db, Food, UnifiedPortion
from sqlalchemy.orm import sessionmaker
import os
from opennourish.utils import generate_nutrition_label_pdf, generate_nutrition_label_svg

main_bp = Blueprint("main", __name__)


@main_bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@main_bp.route("/food/<int:fdc_id>")
def food_detail(fdc_id):
    q = request.args.get("q")
    current_app.logger.debug(f"Debug: In food_detail, received q: {q}")
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404

    # Manually fetch portions for this USDA food
    # Manually fetch portions for this USDA food
    DefaultSession = sessionmaker(bind=db.get_engine(bind=None))
    default_session = DefaultSession()

    try:
        portions = (
            default_session.query(UnifiedPortion)
            .filter_by(fdc_id=fdc_id)
            .order_by(
                UnifiedPortion.seq_num.asc().nulls_last(),
                UnifiedPortion.gram_weight.asc(),
            )
            .all()
        )

        # Ensure all portions have a seq_num
        if any(p.seq_num is None for p in portions):
            portions_to_update = sorted(portions, key=lambda p: p.gram_weight)
            for i, p in enumerate(portions_to_update):
                p.seq_num = i + 1
            db.session.commit()
            flash(
                "Assigned sequence numbers to all portions. Please try again.", "info"
            )

    finally:
        default_session.close()

    return render_template(
        "food_detail.html", food=food, search_term=q, portions=portions
    )


@main_bp.route("/upc/<barcode>")
def upc_search(barcode):
    food_row = db.session.execute(db.select(Food).filter_by(upc=barcode)).first()

    if food_row:
        food_obj = food_row[0]

        # Query for portions related to this fdc_id
        portions = food_obj.portions
        portions_data = [
            {"id": p.id, "description": p.full_description_str} for p in portions
        ]

        return jsonify(
            {
                "status": "found",
                "fdc_id": food_obj.fdc_id,
                "description": food_obj.description,
                "detail_url": url_for("main.food_detail", fdc_id=food_obj.fdc_id),
                "portions": portions_data,
                "nutrition_label_svg_url": url_for(
                    "main.nutrition_label_svg", fdc_id=food_obj.fdc_id
                ),
            }
        )
    else:
        return jsonify({"status": "not_found"}), 404


@main_bp.route("/generate_nutrition_label/<int:fdc_id>")
def generate_nutrition_label(fdc_id):
    return generate_nutrition_label_pdf(fdc_id)


@main_bp.route("/nutrition_label_svg/<int:fdc_id>")
def nutrition_label_svg(fdc_id):
    return generate_nutrition_label_svg(fdc_id)
