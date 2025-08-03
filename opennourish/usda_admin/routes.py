from flask import request, flash, redirect, url_for
from . import usda_admin_bp
from models import db, UnifiedPortion, Food
from flask_login import login_required
from opennourish.decorators import key_user_required


@usda_admin_bp.route("/usda_portion/add", methods=["POST"])
@login_required
@key_user_required
def add_usda_portion():
    fdc_id = request.form.get("fdc_id", type=int)
    amount = request.form.get("amount", type=float)
    measure_unit = request.form.get("measure_unit_description")
    portion_description = request.form.get("portion_description")
    modifier = request.form.get("modifier")
    gram_weight = request.form.get("gram_weight", type=float)

    if not all([fdc_id, gram_weight]):
        flash("Gram weight is a required field.", "danger")
        return redirect(url_for("main.food_detail", fdc_id=fdc_id))

    food = db.session.get(Food, fdc_id)
    if not food:
        flash("USDA Food not found.", "danger")
        return redirect(url_for("search.search"))

    new_portion = UnifiedPortion(
        fdc_id=fdc_id,
        amount=amount,
        measure_unit_description=measure_unit,
        portion_description=portion_description,
        modifier=modifier,
        gram_weight=gram_weight,
    )
    db.session.add(new_portion)
    db.session.commit()
    flash("Portion added successfully.", "success")
    return redirect(url_for("main.food_detail", fdc_id=fdc_id))


@usda_admin_bp.route("/usda_portion/<int:portion_id>/edit", methods=["POST"])
@login_required
@key_user_required
def edit_usda_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or not portion.fdc_id:
        flash("USDA portion not found.", "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    portion.amount = request.form.get("amount", type=float)
    portion.measure_unit_description = request.form.get("measure_unit_description")
    portion.portion_description = request.form.get("portion_description")
    portion.modifier = request.form.get("modifier")
    portion.gram_weight = request.form.get("gram_weight", type=float)
    portion.was_imported = False  # Mark as user-modified

    if not portion.gram_weight:
        flash("Gram weight is a required field.", "danger")
        return redirect(url_for("main.food_detail", fdc_id=portion.fdc_id))

    db.session.commit()
    flash("Portion updated successfully.", "success")
    return redirect(url_for("main.food_detail", fdc_id=portion.fdc_id))


@usda_admin_bp.route("/usda_portion/<int:portion_id>/delete", methods=["POST"])
@login_required
@key_user_required
def delete_usda_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or not portion.fdc_id:
        flash("USDA portion not found.", "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    fdc_id = portion.fdc_id
    db.session.delete(portion)
    db.session.commit()
    flash("Portion deleted successfully.", "success")
    return redirect(url_for("main.food_detail", fdc_id=fdc_id))


@usda_admin_bp.route("/usda_portion/<int:portion_id>/move_up", methods=["POST"])
@login_required
@key_user_required
def move_usda_portion_up(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or not portion_to_move.fdc_id:
        flash("USDA portion not found.", "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    if portion_to_move.seq_num is None:
        # Assign sequence numbers to all portions of this food if any are missing
        portions = (
            UnifiedPortion.query.filter_by(fdc_id=portion_to_move.fdc_id)
            .order_by(UnifiedPortion.gram_weight)
            .all()
        )
        for i, p in enumerate(portions):
            p.seq_num = i + 1
        db.session.commit()
        flash("Assigned sequence numbers to all portions. Please try again.", "info")
        return redirect(url_for("main.food_detail", fdc_id=portion_to_move.fdc_id))

    # Find the portion with the next lower seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.fdc_id == portion_to_move.fdc_id,
            UnifiedPortion.seq_num < portion_to_move.seq_num,
        )
        .order_by(UnifiedPortion.seq_num.desc())
        .first()
    )

    if portion_to_swap_with:
        # Swap seq_num values
        portion_to_move.seq_num, portion_to_swap_with.seq_num = (
            portion_to_swap_with.seq_num,
            portion_to_move.seq_num,
        )
        db.session.commit()
        flash("Portion moved up.", "success")
    else:
        flash("Portion is already at the top.", "info")

    return redirect(url_for("main.food_detail", fdc_id=portion_to_move.fdc_id))


@usda_admin_bp.route("/usda_portion/<int:portion_id>/move_down", methods=["POST"])
@login_required
@key_user_required
def move_usda_portion_down(portion_id):
    portion_to_move = db.session.get(UnifiedPortion, portion_id)
    if not portion_to_move or not portion_to_move.fdc_id:
        flash("USDA portion not found.", "danger")
        return redirect(request.referrer or url_for("dashboard.index"))

    # Find the portion with the next higher seq_num
    portion_to_swap_with = (
        UnifiedPortion.query.filter(
            UnifiedPortion.fdc_id == portion_to_move.fdc_id,
            UnifiedPortion.seq_num > portion_to_move.seq_num,
        )
        .order_by(UnifiedPortion.seq_num.asc())
        .first()
    )

    if portion_to_swap_with:
        # Swap seq_num values
        portion_to_move.seq_num, portion_to_swap_with.seq_num = (
            portion_to_swap_with.seq_num,
            portion_to_move.seq_num,
        )
        db.session.commit()
        flash("Portion moved down.", "success")
    else:
        flash("Portion is already at the bottom.", "info")

    return redirect(url_for("main.food_detail", fdc_id=portion_to_move.fdc_id))
