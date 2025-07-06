from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user, login_required
from . import bp
from .forms import GoalForm
from models import db, UserGoal, CheckIn, User
from opennourish.utils import calculate_bmr, calculate_goals_from_preset
from config import Config

@bp.route('/calculate-bmr', methods=['POST'])
@login_required
def calculate_bmr_route():
    data = request.get_json()
    age = data.get('age')
    gender = data.get('gender')
    height_cm = data.get('height_cm')
    weight_kg = data.get('weight_kg')
    body_fat_percentage = data.get('body_fat_percentage')
    diet_preset = data.get('diet_preset')

    from flask import current_app
    current_app.logger.debug(f"Received data for BMR calculation: {data}")
    if not all([age, gender, height_cm, weight_kg]):
        current_app.logger.debug(f"Missing required fields for BMR calculation: age={age}, gender={gender}, height_cm={height_cm}, weight_kg={weight_kg}")
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        bmr, formula_name = calculate_bmr(
            weight_kg=float(weight_kg),
            height_cm=float(height_cm),
            age=int(age),
            gender=gender,
            body_fat_percentage=float(body_fat_percentage) if body_fat_percentage else None
        )
        
        current_app.logger.debug(f"BMR calculation successful: bmr={bmr}, formula={formula_name}")
        response_data = {'bmr': bmr, 'formula': formula_name}

        if bmr and diet_preset:
            adjusted_goals = calculate_goals_from_preset(bmr, diet_preset)
            if adjusted_goals:
                response_data['adjusted_goals'] = adjusted_goals

        return jsonify(response_data)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid data types'}), 400

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
    formula_name = None
    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
    
    # Determine weight and height for BMR calculation
    weight_for_bmr = None
    height_for_bmr = None
    body_fat_for_bmr = None

    if latest_checkin:
        weight_for_bmr = latest_checkin.weight_kg
        body_fat_for_bmr = latest_checkin.body_fat_percentage
    elif form.weight_kg.data:
        weight_for_bmr = form.weight_kg.data
        body_fat_for_bmr = form.body_fat_percentage.data

    if current_user.height_cm:
        height_for_bmr = current_user.height_cm
    elif form.height_cm.data:
        height_for_bmr = form.height_cm.data

    if weight_for_bmr and height_for_bmr and current_user.age and current_user.gender:
        bmr, formula_name = calculate_bmr(
            weight_kg=weight_for_bmr,
            height_cm=height_for_bmr,
            age=current_user.age,
            gender=current_user.gender,
            body_fat_percentage=body_fat_for_bmr
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
            # After creating a new checkin, it becomes the latest one
            latest_checkin = new_checkin

        # Determine weight for BMR calculation from form or latest checkin
        weight_for_bmr = form.weight_kg.data
        if not weight_for_bmr and latest_checkin:
            weight_for_bmr = latest_checkin.weight_kg
        
        body_fat_for_bmr = form.body_fat_percentage.data
        if not body_fat_for_bmr and latest_checkin:
             body_fat_for_bmr = latest_checkin.body_fat_percentage

        # Update UserGoal model fields
        if not user_goal:
            user_goal = UserGoal(user_id=current_user.id)
            db.session.add(user_goal)

        # Handle diet preset selection
        if form.diet_preset.data and form.diet_preset.data in Config.DIET_PRESETS:
            # We need BMR to calculate goals from preset
            if weight_for_bmr and form.height_cm.data and form.age.data and form.gender.data:
                bmr, _ = calculate_bmr(
                    weight_kg=weight_for_bmr,
                    height_cm=form.height_cm.data,
                    age=form.age.data,
                    gender=form.gender.data,
                    body_fat_percentage=body_fat_for_bmr
                )
                if bmr:
                    goals = calculate_goals_from_preset(bmr, form.diet_preset.data)
                    user_goal.calories = goals['calories']
                    user_goal.protein = goals['protein']
                    user_goal.carbs = goals['carbs']
                    user_goal.fat = goals['fat']
                else:
                    flash('Could not calculate BMR, goals not updated from preset.', 'warning')
            else:
                flash('Cannot calculate goals from preset without complete personal information.', 'danger')
        else:
            user_goal.calories = form.calories.data
            user_goal.protein = form.protein.data
            user_goal.carbs = form.carbs.data
            user_goal.fat = form.fat.data
        
        db.session.commit()
        flash('Goals and personal info updated!', 'success')

        # Re-calculate BMR for display after saving
        if current_user.age and current_user.gender and current_user.height_cm and weight_for_bmr:
            bmr, formula_name = calculate_bmr(
                weight_kg=weight_for_bmr,
                height_cm=current_user.height_cm,
                age=current_user.age,
                gender=current_user.gender,
                body_fat_percentage=body_fat_for_bmr
            )
        return render_template('goals/goals.html', form=form, bmr=bmr, latest_checkin_exists=bool(latest_checkin), diet_presets=Config.DIET_PRESETS)

    return render_template('goals/goals.html', form=form, bmr=bmr, latest_checkin_exists=bool(latest_checkin), diet_presets=Config.DIET_PRESETS)