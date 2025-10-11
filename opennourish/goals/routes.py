from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from . import bp
from .forms import GoalForm
from models import db, UserGoal, CheckIn
from opennourish.utils import (
    calculate_bmr,
    calculate_bmi,
    lbs_to_kg,
    kg_to_lbs,
    cm_to_in,
    in_to_cm,
)
from config import Config
from opennourish.decorators import onboarding_required


@bp.route("/", methods=["GET", "POST"])
@login_required
@onboarding_required
def goals():
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    form = GoalForm(obj=user_goal)

    # Fetch latest check-in for BMR calculation and initial form population
    latest_checkin = (
        CheckIn.query.filter_by(user_id=current_user.id)
        .order_by(CheckIn.checkin_date.desc())
        .first()
    )

    if form.validate_on_submit():
        # Update UserGoal
        if not user_goal:
            user_goal = UserGoal(user_id=current_user.id)
            db.session.add(user_goal)

        # Save the user's choices
        user_goal.goal_modifier = form.goal_modifier.data
        user_goal.diet_preset = form.diet_preset.data

        # Directly save the nutritional values from the form
        if form.calories.data is not None:
            user_goal.calories = form.calories.data
        if form.protein.data is not None:
            user_goal.protein = form.protein.data
        if form.carbs.data is not None:
            user_goal.carbs = form.carbs.data
        if form.fat.data is not None:
            user_goal.fat = form.fat.data

        # Update Exercise Goals
        if form.calories_burned_goal_weekly.data is not None:
            user_goal.calories_burned_goal_weekly = (
                form.calories_burned_goal_weekly.data
            )
        if form.exercises_per_week_goal.data is not None:
            user_goal.exercises_per_week_goal = form.exercises_per_week_goal.data
        if form.minutes_per_exercise_goal.data is not None:
            user_goal.minutes_per_exercise_goal = form.minutes_per_exercise_goal.data

        # Update Body Composition Goals
        if current_user.measurement_system == "us":
            if form.weight_goal_lbs.data is not None:
                user_goal.weight_goal_kg = lbs_to_kg(form.weight_goal_lbs.data)
            if form.waist_in_goal.data is not None:
                user_goal.waist_cm_goal = in_to_cm(form.waist_in_goal.data)
        else:
            if form.weight_goal_kg.data is not None:
                user_goal.weight_goal_kg = form.weight_goal_kg.data
            if form.waist_cm_goal.data is not None:
                user_goal.waist_cm_goal = form.waist_cm_goal.data
        if form.body_fat_percentage_goal.data is not None:
            user_goal.body_fat_percentage_goal = form.body_fat_percentage_goal.data
        if form.default_fasting_hours.data is not None:
            user_goal.default_fasting_hours = form.default_fasting_hours.data

        db.session.commit()
        flash("Goals updated!", "success")
        return redirect(url_for("goals.goals"))

    # Pre-populate form for GET request
    if request.method == "GET" and user_goal:
        form.goal_modifier.data = user_goal.goal_modifier
        form.diet_preset.data = user_goal.diet_preset
        form.calories.data = user_goal.calories
        form.protein.data = user_goal.protein
        form.carbs.data = user_goal.carbs
        form.fat.data = user_goal.fat
        form.calories_burned_goal_weekly.data = user_goal.calories_burned_goal_weekly
        form.exercises_per_week_goal.data = user_goal.exercises_per_week_goal
        form.minutes_per_exercise_goal.data = user_goal.minutes_per_exercise_goal
        form.default_fasting_hours.data = user_goal.default_fasting_hours
        if current_user.measurement_system == "us":
            form.weight_goal_lbs.data = kg_to_lbs(user_goal.weight_goal_kg)
            form.waist_in_goal.data = cm_to_in(user_goal.waist_cm_goal)
        else:
            form.weight_goal_kg.data = user_goal.weight_goal_kg
            form.waist_cm_goal.data = user_goal.waist_cm_goal
        form.body_fat_percentage_goal.data = user_goal.body_fat_percentage_goal

    # Calculate BMR for display (using data from User model and latest check-in)
    bmr, formula_name = None, None
    weight_for_bmr = latest_checkin.weight_kg if latest_checkin else None
    if all(
        [weight_for_bmr, current_user.height_cm, current_user.age, current_user.gender]
    ):
        bmr, formula_name = calculate_bmr(
            weight_kg=weight_for_bmr,
            height_cm=current_user.height_cm,
            age=current_user.age,
            gender=current_user.gender,
            body_fat_percentage=latest_checkin.body_fat_percentage
            if latest_checkin
            else None,
        )

    # Calculate BMI for display
    bmi = None
    if latest_checkin and latest_checkin.weight_kg and current_user.height_cm:
        bmi = calculate_bmi(latest_checkin.weight_kg, current_user.height_cm)

    # Calculate Target BMI
    target_bmi = None
    if user_goal and user_goal.weight_goal_kg and current_user.height_cm:
        target_bmi = calculate_bmi(user_goal.weight_goal_kg, current_user.height_cm)

    latest_waist_cm = latest_checkin.waist_cm if latest_checkin else None

    return render_template(
        "goals/goals.html",
        form=form,
        bmr=bmr,
        bmi=bmi,
        target_bmi=target_bmi,
        formula_name=formula_name,
        diet_presets=Config.DIET_PRESETS,
        latest_waist_cm=latest_waist_cm,
    )


@bp.route("/calculate-bmr", methods=["POST"])
@login_required
def calculate_bmr_api():
    data = request.get_json()
    bmr, formula = calculate_bmr(
        weight_kg=data.get("weight_kg"),
        height_cm=data.get("height_cm"),
        age=data.get("age"),
        gender=data.get("gender"),
        body_fat_percentage=data.get("body_fat_percentage"),
    )
    if bmr:
        response = {"bmr": bmr, "formula": formula}
        return jsonify(response)
    return jsonify({"error": "Could not calculate BMR with the provided data."}), 400
