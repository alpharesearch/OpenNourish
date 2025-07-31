from flask import render_template, request, flash, redirect, url_for, current_app
from . import usda_admin_bp
from models import db, UnifiedPortion, Food
from flask_login import login_required, current_user
from opennourish.decorators import key_user_required

@usda_admin_bp.route('/usda_portion/add', methods=['POST'])
@login_required
@key_user_required
def add_usda_portion():
    fdc_id = request.form.get('fdc_id', type=int)
    amount = request.form.get('amount', type=float)
    measure_unit = request.form.get('measure_unit_description')
    portion_description = request.form.get('portion_description')
    modifier = request.form.get('modifier')
    gram_weight = request.form.get('gram_weight', type=float)

    if not all([fdc_id, amount, measure_unit, gram_weight]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('main.food_detail', fdc_id=fdc_id))

    food = db.session.get(Food, fdc_id)
    if not food:
        flash('USDA Food not found.', 'danger')
        return redirect(url_for('search.search'))

    new_portion = UnifiedPortion(
        fdc_id=fdc_id,
        amount=amount,
        measure_unit_description=measure_unit,
        portion_description=portion_description,
        modifier=modifier,
        gram_weight=gram_weight
    )
    db.session.add(new_portion)
    db.session.commit()
    flash('Portion added successfully.', 'success')
    return redirect(url_for('main.food_detail', fdc_id=fdc_id))

@usda_admin_bp.route('/usda_portion/<int:portion_id>/edit', methods=['POST'])
@login_required
@key_user_required
def edit_usda_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or not portion.fdc_id:
        flash('USDA portion not found.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    portion.amount = request.form.get('amount', type=float)
    portion.measure_unit_description = request.form.get('measure_unit_description')
    portion.portion_description = request.form.get('portion_description')
    portion.modifier = request.form.get('modifier')
    portion.gram_weight = request.form.get('gram_weight', type=float)

    if not all([portion.amount, portion.measure_unit_description, portion.gram_weight]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('main.food_detail', fdc_id=portion.fdc_id))
    
    db.session.commit()
    flash('Portion updated successfully.', 'success')
    return redirect(url_for('main.food_detail', fdc_id=portion.fdc_id))

@usda_admin_bp.route('/usda_portion/<int:portion_id>/delete', methods=['POST'])
@login_required
@key_user_required
def delete_usda_portion(portion_id):
    portion = db.session.get(UnifiedPortion, portion_id)
    if not portion or not portion.fdc_id:
        flash('USDA portion not found.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    fdc_id = portion.fdc_id
    db.session.delete(portion)
    db.session.commit()
    flash('Portion deleted successfully.', 'success')
    return redirect(url_for('main.food_detail', fdc_id=fdc_id))
