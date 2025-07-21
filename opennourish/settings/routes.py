from flask import render_template, flash, redirect, url_for, request, current_app
from flask_login import current_user, login_required, logout_user
from models import User, db, MyFood, Recipe, UserGoal, CheckIn, DailyLog, ExerciseLog, Friendship
from .forms import SettingsForm, ChangePasswordForm, DeleteAccountConfirmForm
from opennourish.utils import ft_in_to_cm, cm_to_ft_in
from . import settings_bp

@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
def settings():
    settings_form = SettingsForm(obj=current_user)
    password_form = ChangePasswordForm()

    if settings_form.validate_on_submit() and 'submit_settings' in request.form:
        user = db.session.get(User, current_user.id)
        
        # Check if email has changed and unverify if so
        if user.email != settings_form.email.data:
            user.email = settings_form.email.data
            user.is_verified = False
            flash('Your email address has been changed and your email verification status has been reset. Please verify your new email.', 'warning')
        
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
        user.is_private = settings_form.is_private.data
        
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
        settings_form.email.data = current_user.email
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
        password_form=password_form,
        current_app=current_app
    )

@settings_bp.route('/restart-onboarding', methods=['POST'])
@login_required
def restart_onboarding():
    current_user.has_completed_onboarding = False
    db.session.commit()
    flash('You have restarted the onboarding wizard.', 'info')
    return redirect(url_for('onboarding.step1'))


@settings_bp.route('/delete_confirm')
@login_required
def delete_confirm():
    form = DeleteAccountConfirmForm()
    return render_template('settings/delete_confirm.html', title='Confirm Deletion', form=form)


@settings_bp.route('/delete', methods=['POST'])
@login_required
def delete_account():
    form = DeleteAccountConfirmForm()
    if form.validate_on_submit():
        user = db.session.get(User, current_user.id)
        if user.check_password(form.password.data):
            try:
                # Anonymize MyFood and Recipe records
                MyFood.query.filter_by(user_id=user.id).update({'user_id': None})
                Recipe.query.filter_by(user_id=user.id).update({'user_id': None})

                # Delete direct personal data
                UserGoal.query.filter_by(user_id=user.id).delete()
                CheckIn.query.filter_by(user_id=user.id).delete()
                DailyLog.query.filter_by(user_id=user.id).delete()
                ExerciseLog.query.filter_by(user_id=user.id).delete()

                # Delete social connections
                Friendship.query.filter(
                    (Friendship.requester_id == user.id) |
                    (Friendship.receiver_id == user.id)
                ).delete()

                # Delete the user
                db.session.delete(user)

                db.session.commit()
                logout_user()
                flash('Your account has been permanently deleted.', 'success')
                return redirect(url_for('main.index'))
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error deleting user account: {e}")
                flash('An error occurred during account deletion. Please try again.', 'danger')
                return redirect(url_for('settings.delete_confirm'))
        else:
            flash('Incorrect password.', 'danger')
    return render_template('settings/delete_confirm.html', title='Confirm Deletion', form=form)