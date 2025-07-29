from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from . import exercise_bp
from .forms import ExerciseLogForm
from .utils import get_user_weight_kg, calculate_calories_burned
from models import db, ExerciseLog, UserGoal, ExerciseActivity
from datetime import date, timedelta
from opennourish.time_utils import get_user_today, get_start_of_week

@exercise_bp.route('/log', methods=['GET', 'POST'])
@login_required
def log_exercise():
    form = ExerciseLogForm()
    form.activity.query = ExerciseActivity.query.order_by(ExerciseActivity.name).all()

    if form.validate_on_submit():
        user_weight_kg = get_user_weight_kg()
        if user_weight_kg is None:
            return redirect(url_for('tracking.progress'))

        calories_burned = 0
        manual_description = None
        activity_id = None

        if form.activity.data:
            activity = form.activity.data
            calories_burned = calculate_calories_burned(activity, form.duration_minutes.data, user_weight_kg)
            activity_id = activity.id
        else:
            calories_burned = form.calories_burned.data if form.calories_burned.data is not None else 0
            manual_description = form.manual_description.data
            activity_id = None # Explicitly set to None for manual entries

        exercise_log = ExerciseLog(
            user_id=current_user.id,
            log_date=form.log_date.data,
            activity_id=activity_id,
            manual_description=manual_description,
            duration_minutes=form.duration_minutes.data,
            calories_burned=calories_burned
        )
        db.session.add(exercise_log)
        db.session.commit()
        flash('Exercise logged successfully!', 'success')
        return redirect(url_for('.log_exercise'))

    if request.method == 'GET':
        form.log_date.data = get_user_today()

    page = request.args.get('page', 1, type=int)
    logs = ExerciseLog.query.filter_by(user_id=current_user.id).order_by(ExerciseLog.log_date.desc()).paginate(page=page, per_page=10)
    
    forms = {}
    for item in logs.items:
        edit_form = ExerciseLogForm(obj=item, prefix=f"form-{item.id}")
        edit_form.activity.query = ExerciseActivity.query.order_by(ExerciseActivity.name).all()
        forms[item.id] = edit_form

    # --- Weekly Exercise Goal Progress ---
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    weekly_progress = {
        'calories_burned': 0,
        'exercises': 0,
        'minutes': 0
    }
    start_of_week, end_of_week = None, None
    if user_goal:
        today = get_user_today()
        start_of_week = get_start_of_week(today, current_user.week_start_day)
        end_of_week = start_of_week + timedelta(days=6)

        weekly_logs = ExerciseLog.query.filter(
            ExerciseLog.user_id == current_user.id,
            ExerciseLog.log_date >= start_of_week,
            ExerciseLog.log_date <= end_of_week
        ).all()

        if weekly_logs:
            weekly_progress['calories_burned'] = sum(log.calories_burned for log in weekly_logs)
            weekly_progress['exercises'] = len(weekly_logs)
            weekly_progress['minutes'] = sum(log.duration_minutes for log in weekly_logs)

    # Prepare data for dynamic calorie calculation on the frontend
    user_weight_kg = get_user_weight_kg(user_id=current_user.id)
    activities = ExerciseActivity.query.all()
    activity_met_values = {activity.id: activity.met_value for activity in activities}

    return render_template('exercise/log_exercise.html', 
                           form=form, 
                           logs=logs, 
                           forms=forms,
                           title='Exercise Log',
                           user_goal=user_goal,
                           weekly_progress=weekly_progress,
                           start_of_week=start_of_week,
                           end_of_week=end_of_week,
                           user_weight_kg=user_weight_kg,
                           activity_met_values=activity_met_values)

@exercise_bp.route('/<int:log_id>/edit', methods=['POST'])
@login_required
def edit_exercise(log_id):
    exercise_log = db.session.get(ExerciseLog, log_id)
    if not exercise_log:
        abort(404)
    if exercise_log.user_id != current_user.id:
        flash('You do not have permission to edit this exercise log.', 'danger')
        return redirect(url_for('.log_exercise'))

    form = ExerciseLogForm(prefix=f"form-{exercise_log.id}")
    form.activity.query = ExerciseActivity.query.order_by(ExerciseActivity.name).all()
    
    if form.validate_on_submit():
        user_weight_kg = get_user_weight_kg()
        if user_weight_kg is None:
            return redirect(url_for('tracking.progress'))

        exercise_log.log_date = form.log_date.data
        exercise_log.duration_minutes = form.duration_minutes.data
        
        if form.activity.data:
            activity = form.activity.data
            exercise_log.activity_id = activity.id
            exercise_log.manual_description = None
            exercise_log.calories_burned = calculate_calories_burned(activity, form.duration_minutes.data, user_weight_kg)
        else:
            exercise_log.activity_id = None
            exercise_log.manual_description = form.manual_description.data
            # If calories_burned is not provided in the form, it will be None, causing an error
            # We default to 0 and flash a message to the user
            if form.calories_burned.data is None:
                exercise_log.calories_burned = 0
                flash('Please enter the calories burned for manual entries.', 'warning')
            else:
                exercise_log.calories_burned = form.calories_burned.data

        db.session.commit()
        flash('Exercise log updated successfully!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return redirect(url_for('.log_exercise', page=request.args.get('page', 1, type=int)))

@exercise_bp.route('/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_exercise(log_id):
    exercise_log = db.session.get(ExerciseLog, log_id)
    if not exercise_log:
        abort(404)
    if exercise_log.user_id != current_user.id:
        flash('You do not have permission to delete this exercise log.', 'danger')
        return redirect(url_for('.log_exercise'))
    
    db.session.delete(exercise_log)
    db.session.commit()
    flash('Exercise log deleted successfully!', 'success')
    return redirect(url_for('.log_exercise', page=request.args.get('page', 1, type=int)))