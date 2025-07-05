from flask import render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from . import tracking_bp
from .forms import CheckInForm
from models import db, CheckIn
from datetime import date

@tracking_bp.route('/check-in/new', methods=['GET', 'POST'])
@login_required
def new_check_in():
    form = CheckInForm()
    if form.validate_on_submit():
        checkin = CheckIn.query.filter_by(user_id=current_user.id, checkin_date=form.checkin_date.data).first()
        if checkin:
            checkin.weight_kg = form.weight_kg.data
            checkin.body_fat_percentage = form.body_fat_percentage.data
            checkin.waist_cm = form.waist_cm.data
            flash('Your check-in has been updated.', 'success')
        else:
            checkin = CheckIn(
                user_id=current_user.id,
                checkin_date=form.checkin_date.data,
                weight_kg=form.weight_kg.data,
                body_fat_percentage=form.body_fat_percentage.data,
                waist_cm=form.waist_cm.data
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
    check_ins = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).paginate(page=page, per_page=10)
    return render_template('tracking/progress.html', check_ins=check_ins, title='Your Progress')

@tracking_bp.route('/check-in/<int:check_in_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_check_in(check_in_id):
    check_in = CheckIn.query.get_or_404(check_in_id)
    if check_in.user_id != current_user.id:
        flash('Entry not found or you do not have permission to edit it.', 'danger')
        return redirect(url_for('tracking.progress'))
    form = CheckInForm(obj=check_in)
    if form.validate_on_submit():
        check_in.checkin_date = form.checkin_date.data
        check_in.weight_kg = form.weight_kg.data
        check_in.body_fat_percentage = form.body_fat_percentage.data
        check_in.waist_cm = form.waist_cm.data
        db.session.commit()
        flash('Your check-in has been updated.', 'success')
        return redirect(url_for('tracking.progress'))
    return render_template('tracking/edit_check_in.html', form=form)

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
