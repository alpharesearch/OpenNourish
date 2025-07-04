from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import exercise_bp
from .forms import ExerciseLogForm
from models import db, ExerciseLog, CheckIn
from datetime import date

@exercise_bp.route('/exercise/log', methods=['GET', 'POST'])
@login_required
def log_exercise():
    form = ExerciseLogForm()
    if form.validate_on_submit():
        calories_burned = 0
        if form.activity.data:
            activity = form.activity.data
            # Fetch the user's most recent weight
            last_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
            if not last_checkin:
                flash('Please add a weight check-in before logging an exercise.', 'danger')
                return redirect(url_for('tracking.check_in'))
            
            user_weight_kg = last_checkin.weight_kg
            calories_burned = (activity.met_value * user_weight_kg * 3.5) / 200 * form.duration_minutes.data
            manual_description = None
        else:
            calories_burned = form.calories_burned.data
            manual_description = form.manual_description.data

        exercise_log = ExerciseLog(
            user_id=current_user.id,
            log_date=date.today(),
            activity_id=form.activity.data.id if form.activity.data else None,
            manual_description=manual_description,
            duration_minutes=form.duration_minutes.data,
            calories_burned=calories_burned
        )
        db.session.add(exercise_log)
        db.session.commit()
        flash('Exercise logged successfully!', 'success')
        return redirect(url_for('exercise.exercise_history'))
    return render_template('exercise/log_exercise.html', form=form)

@exercise_bp.route('/exercise/history')
@login_required
def exercise_history():
    page = request.args.get('page', 1, type=int)
    logs = ExerciseLog.query.filter_by(user_id=current_user.id).order_by(ExerciseLog.log_date.desc()).paginate(page=page, per_page=10)
    return render_template('exercise/history.html', logs=logs)

@exercise_bp.route('/exercise/edit/<int:log_id>', methods=['GET', 'POST'])
@login_required
def edit_exercise(log_id):
    exercise_log = ExerciseLog.query.get_or_404(log_id)
    if exercise_log.user_id != current_user.id:
        flash('You do not have permission to edit this exercise log.', 'danger')
        return redirect(url_for('exercise.exercise_history'))

    form = ExerciseLogForm(obj=exercise_log)
    if form.validate_on_submit():
        exercise_log.duration_minutes = form.duration_minutes.data
        
        if form.activity.data:
            exercise_log.activity_id = form.activity.data.id
            exercise_log.manual_description = None
            last_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
            if not last_checkin:
                flash('Please add a weight check-in before logging an exercise.', 'danger')
                return redirect(url_for('tracking.check_in'))
            user_weight_kg = last_checkin.weight_kg
            exercise_log.calories_burned = (form.activity.data.met_value * user_weight_kg * 3.5) / 200 * form.duration_minutes.data
        else:
            exercise_log.activity_id = None
            exercise_log.manual_description = form.manual_description.data
            exercise_log.calories_burned = form.calories_burned.data

        db.session.commit()
        flash('Exercise log updated successfully!', 'success')
        return redirect(url_for('exercise.exercise_history'))
    
    return render_template('exercise/log_exercise.html', form=form)

@exercise_bp.route('/exercise/delete/<int:log_id>', methods=['POST'])
@login_required
def delete_exercise(log_id):
    exercise_log = ExerciseLog.query.get_or_404(log_id)
    if exercise_log.user_id != current_user.id:
        flash('You do not have permission to delete this exercise log.', 'danger')
        return redirect(url_for('exercise.exercise_history'))
    
    db.session.delete(exercise_log)
    db.session.commit()
    flash('Exercise log deleted successfully!', 'success')
    return redirect(url_for('exercise.exercise_history'))
