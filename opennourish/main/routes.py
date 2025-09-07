from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    send_from_directory,
    current_app,
    jsonify,
)
from datetime import datetime, timezone
from flask_login import current_user
from models import db, Food
import os
from opennourish.utils import (
    ensure_portion_sequence,
)
from opennourish.typst_utils import (
    generate_nutrition_label_pdf,
    generate_nutrition_label_svg,
)

main_bp = Blueprint("main", __name__)

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
    food = db.session.get(Food, fdc_id)
    if not food:
        return "Food not found", 404

    # Ensure portions have sequence numbers before passing to the template
    ensure_portion_sequence([food])

    # The template will handle sorting by seq_num
    portions = food.portions

    return render_template(
        "food_detail.html",
        food=food,
        search_term=q,
        portions=portions,
        timestamp=datetime.now(timezone.utc).timestamp(),
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
