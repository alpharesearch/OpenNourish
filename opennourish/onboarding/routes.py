from flask import render_template, redirect, url_for, flash, session, request, current_app
from flask_login import login_required, current_user
from models import db, User, UserGoal, CheckIn # Import CheckIn model
from .forms import MeasurementSystemForm, PersonalInfoForm, InitialGoalsForm
from opennourish.utils import ft_in_to_cm, lbs_to_kg, kg_to_lbs, cm_to_ft_in, calculate_bmr, calculate_goals_from_preset, in_to_cm, cm_to_in
from datetime import date # Import date
from . import onboarding_bp # Import the blueprint from __init__.py
from config import Config # Import Config

@onboarding_bp.route('/step1', methods=['GET', 'POST'])
@login_required
def step1():
    if current_user.has_completed_onboarding:
        return redirect(url_for('dashboard.index'))

    form = MeasurementSystemForm()
    if form.validate_on_submit():
        current_user.email = form.email.data
        current_user.measurement_system = form.measurement_system.data
        current_user.theme_preference = form.theme_preference.data
        db.session.commit()
        return redirect(url_for('onboarding.step2'))
    
    # Pre-populate form for GET requests
    form.email.data = current_user.email
    form.measurement_system.data = current_user.measurement_system
    form.theme_preference.data = current_user.theme_preference

    return render_template('onboarding/step1.html', form=form, current_app=current_app)

@onboarding_bp.route('/step2', methods=['GET', 'POST'])
@login_required
def step2():
    if current_user.has_completed_onboarding:
        return redirect(url_for('dashboard.index'))

    form = PersonalInfoForm()
    if form.validate_on_submit():
        current_user.age = form.age.data
        current_user.gender = form.gender.data

        # Handle height conversion and update User model
        if current_user.measurement_system == 'us':
            current_user.height_cm = ft_in_to_cm(form.height_ft.data, form.height_in.data)
        else:
            current_user.height_cm = form.height_cm.data
        
        # Handle weight and body fat by creating a CheckIn entry
        weight_kg_from_form = None
        if current_user.measurement_system == 'us':
            if form.weight_lbs.data:
                weight_kg_from_form = lbs_to_kg(form.weight_lbs.data)
        else:
            if form.weight_kg.data:
                weight_kg_from_form = form.weight_kg.data

        if weight_kg_from_form is not None:
            # Create a new CheckIn entry for the initial weight and body fat
            new_checkin = CheckIn(
                user_id=current_user.id,
                checkin_date=date.today(),
                weight_kg=weight_kg_from_form,
                body_fat_percentage=form.body_fat_percentage.data or 0.0, # Default to 0.0 if not provided
                waist_cm=in_to_cm(form.waist_in.data) if current_user.measurement_system == 'us' else form.waist_cm.data or 0.0 # Handle waist
            )
            db.session.add(new_checkin)

        db.session.commit()
        return redirect(url_for('onboarding.step3'))

    # Pre-populate form for GET requests
    form.age.data = current_user.age
    form.gender.data = current_user.gender
    
    # Fetch latest check-in for pre-population of weight and body fat
    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()

    if current_user.measurement_system == 'us':
        if current_user.height_cm:
            ft, inch = cm_to_ft_in(current_user.height_cm)
            form.height_ft.data = ft
            form.height_in.data = inch
        if latest_checkin and latest_checkin.weight_kg:
            form.weight_lbs.data = kg_to_lbs(latest_checkin.weight_kg)
        if latest_checkin and latest_checkin.waist_cm:
            form.waist_in.data = cm_to_in(latest_checkin.waist_cm)
    else:
        form.height_cm.data = current_user.height_cm
        if latest_checkin and latest_checkin.weight_kg:
            form.weight_kg.data = latest_checkin.weight_kg
        if latest_checkin and latest_checkin.waist_cm:
            form.waist_cm.data = latest_checkin.waist_cm

    if latest_checkin:
        form.body_fat_percentage.data = latest_checkin.body_fat_percentage

    return render_template('onboarding/step2.html', form=form, measurement_system=current_user.measurement_system)

@onboarding_bp.route('/step3', methods=['GET', 'POST'])
@login_required
def step3():
    if current_user.has_completed_onboarding:
        return redirect(url_for('dashboard.index'))

    form = InitialGoalsForm()
    form.diet_preset.choices = [('', 'Select a Preset...')] + [(preset, preset.replace('_', ' ').title()) for preset in Config.DIET_PRESETS.keys()]
    
    # Calculate BMR and initial goals for display
    bmr, formula_name = None, None
    initial_goals = None

    latest_checkin = CheckIn.query.filter_by(user_id=current_user.id).order_by(CheckIn.checkin_date.desc()).first()
    weight_for_bmr = latest_checkin.weight_kg if latest_checkin else None
    body_fat_percentage = latest_checkin.body_fat_percentage if latest_checkin else None

    if all([weight_for_bmr, current_user.height_cm, current_user.age, current_user.gender]):
        bmr, formula_name = calculate_bmr(
            weight_kg=weight_for_bmr,
            height_cm=current_user.height_cm,
            age=current_user.age,
            gender=current_user.gender,
            body_fat_percentage=body_fat_percentage
        )
        if bmr:
            # Default to a balanced preset if no other is chosen
            initial_goals = calculate_goals_from_preset(bmr, 'balanced')

    if form.validate_on_submit():
        user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
        if not user_goal:
            user_goal = UserGoal(user_id=current_user.id)
            db.session.add(user_goal)

        user_goal.calories = form.calories.data
        user_goal.protein = form.protein.data
        user_goal.carbs = form.carbs.data
        user_goal.fat = form.fat.data

        if current_user.measurement_system == 'us':
            user_goal.weight_goal_kg = lbs_to_kg(form.weight_goal_lbs.data)
        else:
            user_goal.weight_goal_kg = form.weight_goal_kg.data

        current_user.has_completed_onboarding = True
        db.session.commit()
        flash('Onboarding complete! Welcome to OpenNourish.', 'success')
        return redirect(url_for('dashboard.index'))

    # Pre-populate form for GET requests
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    if user_goal:
        form.calories.data = user_goal.calories
        form.protein.data = user_goal.protein
        form.carbs.data = user_goal.carbs
        form.fat.data = user_goal.fat
        if current_user.measurement_system == 'us':
            form.weight_goal_lbs.data = kg_to_lbs(user_goal.weight_goal_kg)
        else:
            form.weight_goal_kg.data = user_goal.weight_goal_kg
    elif initial_goals: # Pre-populate with calculated initial goals if no existing user_goal
        form.calories.data = initial_goals['calories']
        form.protein.data = initial_goals['protein']
        form.carbs.data = initial_goals['carbs']
        form.fat.data = initial_goals['fat']

    return render_template('onboarding/step3.html', form=form, measurement_system=current_user.measurement_system, bmr=bmr, formula_name=formula_name, diet_presets=Config.DIET_PRESETS, initial_goals=initial_goals)
