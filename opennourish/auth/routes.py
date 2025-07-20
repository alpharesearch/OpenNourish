from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from urllib.parse import urlsplit
from . import auth_bp
from .forms import LoginForm, RegistrationForm, ResetPasswordRequestForm, ResetPasswordForm
from models import db, User, UserGoal, SystemSetting
from opennourish.utils import get_allow_registration_status, send_password_reset_email, send_verification_email
import os

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(
            (User.username == form.username_or_email.data) | 
            (User.email == form.username_or_email.data)
        ).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('This account has been disabled.', 'warning')
            return redirect(url_for('auth.login'))

        # Retroactively grant admin rights if username matches INITIAL_ADMIN_USERNAME and they are not already an admin.
        admin_from_env = os.getenv('INITIAL_ADMIN_USERNAME')
        if admin_from_env and user.username == admin_from_env and not user.is_admin:
            user.is_admin = True
            db.session.commit()
            flash('You have been granted administrator privileges.', 'success')

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form, 
                           enable_password_reset=current_app.config.get('ENABLE_PASSWORD_RESET', False))

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if not get_allow_registration_status():
        current_app.logger.debug(f"ALLOW_REGISTRATION is {get_allow_registration_status()}. Redirecting to login.")
        flash('New user registration is currently disabled.', 'danger')
        return redirect(url_for('auth.login'))
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)

        # Grant admin rights based on environment variable or if it's the first user
        admin_from_env = os.getenv('INITIAL_ADMIN_USERNAME')
        if admin_from_env:
            if user.username == admin_from_env:
                user.is_admin = True
        else:
            # No environment variable set, so make the first registered user an admin
            if User.query.count() == 0:
                user.is_admin = True

        db.session.add(user)
        db.session.commit()

        # Flash appropriate message
        if user.is_admin:
            flash('Congratulations, you are now a registered user and have been granted administrator privileges!', 'success')
        else:
            flash('Congratulations, you are now a registered user!', 'success')

        # Send verification email
        if current_app.config.get('ENABLE_EMAIL_VERIFICATION', False):
            token = user.get_token(purpose='verify-email')
            send_verification_email(user, token)
            flash('A verification email has been sent to your email address.', 'info')

        login_user(user)  # Log in the user after registration
        
        # After registration, check if the user has existing goals
        user_goal = UserGoal.query.filter_by(user_id=user.id).first()
        if user_goal:
            return redirect(url_for('dashboard.index'))
        else:
            return redirect(url_for('goals.goals'))
    return render_template('register.html', title='Register', form=form)

@auth_bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if not current_app.config.get('ENABLE_PASSWORD_RESET', False):
        flash('Password reset feature is currently disabled.', 'warning')
        return redirect(url_for('auth.login'))

    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = user.get_token(purpose='reset-password')
            send_password_reset_email(user, token)
            flash('Check your email for the instructions to reset your password')
            return redirect(url_for('auth.login'))
        else:
            flash('Email address not found.', 'danger')
    return render_template('reset_password_request.html', title='Reset Password', form=form)

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_token(token, purpose='reset-password')
    if not user:
        flash('That is an invalid or expired token', 'danger')
        return redirect(url_for('auth.reset_password_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_password.html', title='Reset Password', form=form)

@auth_bp.route('/send-verification-email', methods=['POST'])
def send_verification_email_route():
    if not current_user.is_authenticated:
        flash('Please log in to send a verification email.', 'danger')
        return redirect(url_for('auth.login'))

    if not current_app.config.get('ENABLE_EMAIL_VERIFICATION', False):
        flash('Email verification is not enabled.', 'warning')
        return redirect(url_for('main.index'))

    if current_user.is_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('settings.settings'))

    token = current_user.get_token(purpose='verify-email')
    send_verification_email(current_user, token)
    flash('A new verification email has been sent to your email address.', 'success')
    if current_user.has_completed_onboarding:
        return redirect(url_for('settings.settings'))
    else:
        return redirect(url_for('onboarding.step1'))

@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    user = User.verify_token(token, purpose='verify-email')

    if not user:
        flash('That is an invalid or expired verification link.', 'danger')
        return redirect(url_for('auth.login'))

    # If user is already logged in and verified, just redirect
    if current_user.is_authenticated and current_user.id == user.id and user.is_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('dashboard.index'))

    user.is_verified = True
    db.session.commit()
    db.session.refresh(user) # Refresh the user object to reflect the updated is_verified status
    login_user(user) # Re-login the user to refresh current_user proxy
    flash('Your email address has been verified!', 'success')
    if user.has_completed_onboarding:
        return redirect(url_for('dashboard.index', _external=True))
    else:
        return redirect(url_for('onboarding.step1', _external=True))