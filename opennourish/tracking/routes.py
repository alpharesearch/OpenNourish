from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import tracking_bp
from .forms import CheckInForm
from models import db, CheckIn
from opennourish.utils import lbs_to_kg, in_to_cm, kg_to_lbs, cm_to_in
from datetime import date

@tracking_bp.route('/progress', methods=['GET', 'POST'])
@login_required
def progress():
    form = CheckInForm()
    if form.validate_on_submit():
        weight_kg, waist_cm = None, None
        if current_user.measurement_system == 'us':
            weight_kg = lbs_to_kg(form.weight_lbs.data)
            if form.waist_in.data:
                waist_cm = in_to_cm(form.waist_in.data)
        else:
            weight_kg = form.weight_kg.data
            waist_cm = form.waist_cm.data
        
        checkin = CheckIn(
            user_id=current_user.id,
            checkin_date=form.checkin_date.data,
            weight_kg=weight_kg,
            body_fat_percentage=form.body_fat_percentage.data,
            waist_cm=waist_cm
        )
        db.session.add(checkin)
        db.session.commit()
        flash('Your check-in has been recorded.', 'success')
        return redirect(url_for('tracking.progress'))

    page = request.args.get('page', 1, type=int)
    check_ins_pagination = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).paginate(page=page, per_page=10)
    
    forms = {}
    for item in check_ins_pagination.items:
        edit_form = CheckInForm(obj=item, prefix=f"form-{item.id}")

        if edit_form.body_fat_percentage.data is not None:
            edit_form.body_fat_percentage.data = round(edit_form.body_fat_percentage.data, 2)

        if current_user.measurement_system == 'us':
            converted_weight_lbs = kg_to_lbs(item.weight_kg)
            edit_form.weight_lbs.data = round(converted_weight_lbs, 2) if converted_weight_lbs is not None else None

            converted_waist_in = cm_to_in(item.waist_cm)
            edit_form.waist_in.data = round(converted_waist_in, 2) if converted_waist_in is not None else None
        else:
            edit_form.weight_kg.data = round(item.weight_kg, 2) if item.weight_kg is not None else None
            edit_form.waist_cm.data = round(item.waist_cm, 2) if item.waist_cm is not None else None
        
        forms[item.id] = edit_form

    return render_template('tracking/progress.html', 
                           form=form, 
                           check_ins=check_ins_pagination, 
                           forms=forms,
                           title='Your Progress')

@tracking_bp.route('/check-in/<int:check_in_id>/update', methods=['POST'])
@login_required
def update_check_in(check_in_id):
    check_in = CheckIn.query.get_or_404(check_in_id)
    if check_in.user_id != current_user.id:
        flash('Entry not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('tracking.progress'))
    
    form = CheckInForm(request.form, prefix=f"form-{check_in.id}")
    if form.validate_on_submit():
        if current_user.measurement_system == 'us':
            check_in.weight_kg = lbs_to_kg(form.weight_lbs.data)
            if form.waist_in.data:
                check_in.waist_cm = in_to_cm(form.waist_in.data)
        else:
            check_in.weight_kg = form.weight_kg.data
            check_in.waist_cm = form.waist_cm.data
            
        check_in.checkin_date = form.checkin_date.data
        check_in.body_fat_percentage = form.body_fat_percentage.data
        db.session.commit()
        flash('Your check-in has been updated.', 'success')
    return redirect(url_for('tracking.progress'))

@tracking_bp.route('/check-in/<int:check_in_id>/delete', methods=['POST'])
@login_required
def delete_check_in(check_in_id):
    check_in = CheckIn.query.get_or_404(check_in_id)
    if check_in.user_id != current_user.id:
        flash('Entry not found or you do not have permission to delete it.', 'danger')
        return redirect(url_for('tracking.progress'))
    db.session.delete(check_in)
    db.session.commit()
    flash('Your check-in has been deleted.', 'success')
    return redirect(url_for('tracking.progress'))
