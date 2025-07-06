from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from . import bp
from .forms import GoalForm
from models import db, UserGoal, CheckIn, User
from opennourish.utils import calculate_bmr
from config import Config

@bp.route('/', methods=['GET', 'POST'])
@login_required
def goals():
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    form = GoalForm(obj=user_goal)

    # Populate age, gender, height from current_user for GET requests
    if request.method == 'GET':
        form.age.data = current_user.age
        form.gender.data = current_user.gender
        form.height_cm.data = current_user.height_cm

    bmr = None
    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
    
    # Determine weight and height for BMR calculation
    weight_for_bmr = None
    height_for_bmr = None

    if latest_checkin:
        weight_for_bmr = latest_checkin.weight_kg
    elif form.weight_kg.data:
        weight_for_bmr = form.weight_kg.data

    if current_user.height_cm:
        height_for_bmr = current_user.height_cm
    elif form.height_cm.data:
        height_for_bmr = form.height_cm.data

    if weight_for_bmr and height_for_bmr and current_user.age and current_user.gender:
        bmr = calculate_bmr(
            weight_kg=weight_for_bmr,
            height_cm=height_for_bmr,
            age=current_user.age,
            gender=current_user.gender
        )

    if form.validate_on_submit():
        # Update User model fields
        current_user.age = form.age.data
        current_user.gender = form.gender.data
        current_user.height_cm = form.height_cm.data
        db.session.add(current_user) # Add current_user to session to track changes

        # Create a new CheckIn entry if no latest_checkin exists and weight is provided
        if not latest_checkin and form.weight_kg.data:
            from datetime import date
            new_checkin = CheckIn(
                user_id=current_user.id,
                checkin_date=date.today(),
                weight_kg=form.weight_kg.data,
                body_fat_percentage=form.body_fat_percentage.data if form.body_fat_percentage.data else 0.0,
                waist_cm=0.0 # Default or calculate if needed
            )
            db.session.add(new_checkin)
            flash('New check-in entry created!', 'info')

        # Handle diet preset selection
        if form.diet_preset.data and form.diet_preset.data in Config.DIET_PRESETS:
            preset = Config.DIET_PRESETS[form.diet_preset.data]
            form.calories.data = preset['calories']
            form.protein.data = preset['protein']
            form.carbs.data = preset['carbs']
            form.fat.data = preset['fat']

        # Handle diet preset selection
        if form.diet_preset.data and form.diet_preset.data in Config.DIET_PRESETS:
            preset = Config.DIET_PRESETS[form.diet_preset.data]
            form.calories.data = preset['calories']
            form.protein.data = preset['protein']
            form.carbs.data = preset['carbs']
            form.fat.data = preset['fat']

        # Update UserGoal model fields
        if user_goal:
            pass # Populate after preset application
        else:
            user_goal = UserGoal(user_id=current_user.id)
            db.session.add(user_goal)

        form.populate_obj(user_goal) # Populate after preset application
        
        db.session.commit()
        flash('Goals and personal info updated!', 'success')

        # Re-calculate BMR after saving, as user's age/gender/height might have changed
        # Also update latest_checkin if a new one was created
        latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
        if current_user.age and current_user.gender and current_user.height_cm and (latest_checkin and latest_checkin.weight_kg):
            bmr = calculate_bmr(
                weight_kg=latest_checkin.weight_kg,
                height_cm=current_user.height_cm,
                age=current_user.age,
                gender=current_user.gender
            )
        return render_template('goals/goals.html', form=form, bmr=bmr, latest_checkin_exists=bool(latest_checkin), diet_presets=Config.DIET_PRESETS)

    return render_template('goals/goals.html', form=form, bmr=bmr, latest_checkin_exists=bool(latest_checkin), diet_presets=Config.DIET_PRESETS)