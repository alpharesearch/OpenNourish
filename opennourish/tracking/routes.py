from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import tracking_bp
from .forms import CheckInForm
from models import db, CheckIn
from opennourish.utils import lbs_to_kg, in_to_cm, kg_to_lbs, cm_to_in, get_display_weight, get_display_waist

@tracking_bp.route('/check-in/new', methods=['GET', 'POST'])
@login_required
def new_check_in():
    form = CheckInForm()
    if form.validate_on_submit():
        weight_kg = None
        waist_cm = None
        if current_user.measurement_system == 'us':
            weight_kg = lbs_to_kg(form.weight_lbs.data)
            if form.waist_in.data:
                waist_cm = in_to_cm(form.waist_in.data)
        else:
            weight_kg = form.weight_kg.data
            waist_cm = form.waist_cm.data

        checkin = CheckIn.query.filter_by(user_id=current_user.id, checkin_date=form.checkin_date.data).first()
        if checkin:
            checkin.weight_kg = weight_kg
            checkin.body_fat_percentage = form.body_fat_percentage.data
            checkin.waist_cm = waist_cm
            flash('Your check-in has been updated.', 'success')
        else:
            checkin = CheckIn(
                user_id=current_user.id,
                checkin_date=form.checkin_date.data,
                weight_kg=weight_kg,
                body_fat_percentage=form.body_fat_percentage.data,
                waist_cm=waist_cm
            )
            db.session.add(checkin)
            flash('Your check-in has been recorded.', 'success')
        db.session.commit()
        return redirect(url_for('tracking.progress'))
    return render_template('tracking/check_in.html', form=form, title='Submit Your Check-In')

@tracking_bp.route('/progress')
@login_required
def progress():
    page = request.args.get('page', 1, type=int)
    check_ins_pagination = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).paginate(page=page, per_page=10)
    
    # Wrapper class to handle display units
    class CheckInDisplay:
        def __init__(self, check_in, system):
            self.check_in = check_in
            self.weight = get_display_weight(check_in.weight_kg, system)
            self.waist = get_display_waist(check_in.waist_cm, system)
            self.unit_labels = {'weight': 'lbs' if system == 'us' else 'kg', 'waist': 'in' if system == 'us' else 'cm'}

    check_ins_display = [CheckInDisplay(ci, current_user.measurement_system) for ci in check_ins_pagination.items]
    
    return render_template('tracking/progress.html', check_ins=check_ins_display, pagination=check_ins_pagination, title='Your Progress')

@tracking_bp.route('/check-in/<int:check_in_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_check_in(check_in_id):
    check_in = CheckIn.query.get_or_404(check_in_id)
    if check_in.user_id != current_user.id:
        flash('Entry not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('tracking.progress'))
    
    form = CheckInForm(obj=check_in)
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
    
    if request.method == 'GET':
        if current_user.measurement_system == 'us':
            form.weight_lbs.data = kg_to_lbs(check_in.weight_kg)
            if check_in.waist_cm:
                form.waist_in.data = cm_to_in(check_in.waist_cm)
        else:
            form.weight_kg.data = check_in.weight_kg
            form.waist_cm.data = check_in.waist_cm

    return render_template('tracking/edit_check_in.html', form=form, title='Edit Check-In')

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
