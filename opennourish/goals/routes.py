from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from . import bp
from .forms import GoalForm
from models import db, UserGoal, CheckIn, User
from opennourish.utils import (
    calculate_bmr, calculate_goals_from_preset,
    ft_in_to_cm, cm_to_ft_in, lbs_to_kg, kg_to_lbs
)
from config import Config
from datetime import date

@bp.route('/calculate-bmr', methods=['POST'])
@login_required
def calculate_bmr_route():
    data = request.get_json()
    
    age_str = data.get('age')
    gender = data.get('gender')
    body_fat_str = data.get('body_fat_percentage')
    diet_preset = data.get('diet_preset')
    
    height_cm, weight_kg, age, body_fat_percentage = None, None, None, None

    # --- Safely parse and convert all inputs ---
    try:
        if age_str:
            age = int(age_str)

        if body_fat_str:
            body_fat_percentage = float(body_fat_str)

        if current_user.measurement_system == 'us':
            height_ft_str = data.get('height_ft')
            height_in_str = data.get('height_in')
            weight_lbs_str = data.get('weight_lbs')
            
            if height_ft_str and height_in_str:
                height_cm = ft_in_to_cm(float(height_ft_str), float(height_in_str))
            if weight_lbs_str:
                weight_kg = lbs_to_kg(float(weight_lbs_str))
        else:
            height_cm_str = data.get('height_cm')
            weight_kg_str = data.get('weight_kg')
            
            if height_cm_str:
                height_cm = float(height_cm_str)
            if weight_kg_str:
                weight_kg = float(weight_kg_str)

    except (ValueError, TypeError):
        # If any conversion fails, the variable remains None, 
        # and the all() check below will correctly fail.
        pass

    # --- Check if we have everything we need ---
    if not all([age, gender, height_cm, weight_kg]):
        return jsonify({'error': 'Missing or invalid required fields'}), 400

    # --- Perform the calculation ---
    bmr, formula_name = calculate_bmr(
        weight_kg=weight_kg,
        height_cm=height_cm,
        age=age,
        gender=gender,
        body_fat_percentage=body_fat_percentage
    )
    
    response_data = {'bmr': bmr, 'formula': formula_name}

    if bmr and diet_preset:
        adjusted_goals = calculate_goals_from_preset(bmr, diet_preset)
        if adjusted_goals:
            response_data['adjusted_goals'] = adjusted_goals

    return jsonify(response_data)

@bp.route('/', methods=['GET', 'POST'])
@login_required
def goals():
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    form = GoalForm(obj=user_goal)
    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()

    if form.validate_on_submit():
        # Update User model fields
        user = db.session.get(User, current_user.id)
        user.age = form.age.data
        user.gender = form.gender.data

        weight_kg = None
        if current_user.measurement_system == 'us':
            user.height_cm = ft_in_to_cm(form.height_ft.data, form.height_in.data)
            if form.weight_lbs.data:
                weight_kg = lbs_to_kg(form.weight_lbs.data)
        else:
            user.height_cm = form.height_cm.data
            if form.weight_kg.data:
                weight_kg = form.weight_kg.data
        
        # Create a new CheckIn if weight is provided
        if weight_kg:
            new_checkin = CheckIn(
                user_id=current_user.id,
                checkin_date=date.today(),
                weight_kg=weight_kg,
                body_fat_percentage=form.body_fat_percentage.data or 0.0,
                waist_cm=0.0 # Default value
            )
            db.session.add(new_checkin)
            flash('New check-in entry created!', 'info')
            latest_checkin = new_checkin

        # Update UserGoal
        if not user_goal:
            user_goal = UserGoal(user_id=current_user.id)
            db.session.add(user_goal)

        weight_for_bmr = weight_kg or (latest_checkin.weight_kg if latest_checkin else None)
        
        if form.diet_preset.data:
            if all([weight_for_bmr, user.height_cm, user.age, user.gender]):
                bmr, _ = calculate_bmr(
                    weight_kg=weight_for_bmr,
                    height_cm=user.height_cm,
                    age=user.age,
                    gender=user.gender,
                    body_fat_percentage=form.body_fat_percentage.data
                )
                if bmr:
                    goals = calculate_goals_from_preset(bmr, form.diet_preset.data)
                    user_goal.calories = goals['calories']
                    user_goal.protein = goals['protein']
                    user_goal.carbs = goals['carbs']
                    user_goal.fat = goals['fat']
            else:
                flash('Cannot calculate goals from preset without complete personal information.', 'danger')
        else:
            user_goal.calories = form.calories.data
            user_goal.protein = form.protein.data
            user_goal.carbs = form.carbs.data
            user_goal.fat = form.fat.data

        # Update Exercise Goals
        user_goal.calories_burned_goal_weekly = form.calories_burned_goal_weekly.data
        user_goal.exercises_per_week_goal = form.exercises_per_week_goal.data
        user_goal.minutes_per_exercise_goal = form.minutes_per_exercise_goal.data
        
        db.session.commit()
        flash('Goals and personal info updated!', 'success')
        return redirect(url_for('goals.goals'))

    # Pre-populate form for GET request
    if request.method == 'GET':
        form.age.data = current_user.age
        form.gender.data = current_user.gender
        
        if current_user.measurement_system == 'us':
            if current_user.height_cm:
                form.height_ft.data, form.height_in.data = cm_to_ft_in(current_user.height_cm)
            if latest_checkin and latest_checkin.weight_kg:
                form.weight_lbs.data = kg_to_lbs(latest_checkin.weight_kg)
        else:
            form.height_cm.data = current_user.height_cm
            if latest_checkin and latest_checkin.weight_kg:
                form.weight_kg.data = latest_checkin.weight_kg
        
        if latest_checkin:
            form.body_fat_percentage.data = latest_checkin.body_fat_percentage

    # Calculate BMR for display
    bmr, formula_name = None, None
    weight_for_bmr = latest_checkin.weight_kg if latest_checkin else None
    if all([weight_for_bmr, current_user.height_cm, current_user.age, current_user.gender]):
        bmr, formula_name = calculate_bmr(
            weight_kg=weight_for_bmr,
            height_cm=current_user.height_cm,
            age=current_user.age,
            gender=current_user.gender,
            body_fat_percentage=latest_checkin.body_fat_percentage if latest_checkin else None
        )

    return render_template('goals/goals.html', form=form, bmr=bmr, formula_name=formula_name, latest_checkin=latest_checkin, diet_presets=Config.DIET_PRESETS)