from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
from models import User, db
from .forms import SettingsForm, ChangePasswordForm
from opennourish.utils import ft_in_to_cm, cm_to_ft_in
from . import settings_bp

@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
def settings():
    settings_form = SettingsForm(obj=current_user)
    password_form = ChangePasswordForm()

    if settings_form.validate_on_submit() and 'submit_settings' in request.form:
        user = db.session.get(User, current_user.id)
        
        # Handle measurement system first
        system = settings_form.measurement_system.data
        user.measurement_system = system

        # Handle height conversion
        if system == 'us':
            feet = settings_form.height_ft.data
            inches = settings_form.height_in.data
            if feet is not None and inches is not None:
                user.height_cm = ft_in_to_cm(feet, inches)
        else: # metric
            if settings_form.height_cm.data is not None:
                user.height_cm = settings_form.height_cm.data

        user.age = settings_form.age.data
        user.gender = settings_form.gender.data
        user.navbar_preference = settings_form.navbar_preference.data
        user.diary_default_view = settings_form.diary_default_view.data
        user.theme_preference = settings_form.theme_preference.data
        user.meals_per_day = int(settings_form.meals_per_day.data)
        
        db.session.commit()
        flash('Your settings have been updated.', 'success')
        return redirect(url_for('settings.settings'))

    if password_form.validate_on_submit() and 'submit_password' in request.form:
        user = db.session.get(User, current_user.id)
        user.set_password(password_form.password.data)
        db.session.commit()
        flash('Your password has been changed.', 'success')
        return redirect(url_for('settings.settings'))

    # Pre-populate form fields for GET request
    if request.method == 'GET':
        settings_form.age.data = current_user.age
        settings_form.gender.data = current_user.gender
        settings_form.measurement_system.data = current_user.measurement_system
        
        if current_user.height_cm is not None:
            if current_user.measurement_system == 'us':
                feet, inches = cm_to_ft_in(current_user.height_cm)
                settings_form.height_ft.data = feet
                settings_form.height_in.data = inches
            else:
                settings_form.height_cm.data = round(current_user.height_cm, 1)

    return render_template(
        'settings/settings.html',
        title='Settings',
        settings_form=settings_form,
        password_form=password_form
    )

@settings_bp.route('/restart-onboarding', methods=['POST'])
@login_required
def restart_onboarding():
    current_user.has_completed_onboarding = False
    db.session.commit()
    flash('You have restarted the onboarding wizard.', 'info')
    return redirect(url_for('onboarding.step1'))