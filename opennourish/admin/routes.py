from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required
from opennourish.decorators import admin_required
from . import admin_bp
from .forms import AdminSettingsForm, EmailSettingsForm
import json
import os
from models import db, User, Recipe, MyFood, DailyLog, ExerciseLog, SystemSetting
from opennourish.utils import encrypt_value, decrypt_value

@admin_bp.route('/')
@login_required
@admin_required
def index():
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_users = db.session.query(User).count()
    total_recipes = db.session.query(Recipe).count()
    public_recipes = db.session.query(Recipe).filter_by(is_public=True).count()
    total_my_foods = db.session.query(MyFood).count()
    total_daily_logs = db.session.query(DailyLog).count()
    total_exercise_logs = db.session.query(ExerciseLog).count()
    recent_users = db.session.query(User).order_by(User.id.desc()).limit(5).all()

    context = {
        'total_users': total_users,
        'total_recipes': total_recipes,
        'public_recipes': public_recipes,
        'total_my_foods': total_my_foods,
        'total_daily_logs': total_daily_logs,
        'total_exercise_logs': total_exercise_logs,
        'recent_users': recent_users
    }
    return render_template('admin/dashboard.html', **context)

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    form = AdminSettingsForm()
    if form.validate_on_submit():
        # When the form is submitted and valid, update the setting
        allow_registration_setting = SystemSetting.query.filter_by(key='allow_registration').first()
        
        # The data from the BooleanField is True or False
        new_value = str(form.allow_registration.data)
        
        if not allow_registration_setting:
            # If the setting doesn't exist, create it
            allow_registration_setting = SystemSetting(key='allow_registration', value=new_value)
            db.session.add(allow_registration_setting)
        else:
            # If it exists, update its value
            allow_registration_setting.value = new_value
            
        db.session.commit()
        flash('Settings have been saved.', 'success')
        return redirect(url_for('admin.settings'))
    
    # For a GET request, populate the form with the current setting from the database
    allow_registration_setting = SystemSetting.query.filter_by(key='allow_registration').first()
    if allow_registration_setting:
        # The value in the DB is 'True' or 'False', so convert it back to a boolean for the form
        form.allow_registration.data = allow_registration_setting.value.lower() == 'true'
    else:
        # Default to True if the setting is not in the database yet
        form.allow_registration.data = True
        
    return render_template('admin/settings.html', title='Admin Settings', form=form)

@admin_bp.route('/email', methods=['GET', 'POST'])
@login_required
@admin_required
def email_settings():
    form = EmailSettingsForm()
    if form.validate_on_submit():
        # Always save the source selection
        source_setting = SystemSetting.query.filter_by(key='MAIL_CONFIG_SOURCE').first()
        if not source_setting:
            source_setting = SystemSetting(key='MAIL_CONFIG_SOURCE', value=form.MAIL_CONFIG_SOURCE.data)
            db.session.add(source_setting)
        else:
            source_setting.value = form.MAIL_CONFIG_SOURCE.data
        
        # These settings are only saved for 'database' mode, but we can save them anyway.
        # The app's startup logic in __init__.py will decide whether to use them.
        settings_to_save = {
            'MAIL_SERVER': form.MAIL_SERVER.data,
            'MAIL_PORT': str(form.MAIL_PORT.data) if form.MAIL_PORT.data is not None else '',
            'MAIL_SECURITY_PROTOCOL': form.MAIL_SECURITY_PROTOCOL.data,
            'MAIL_USERNAME': form.MAIL_USERNAME.data,
            'MAIL_PASSWORD': form.MAIL_PASSWORD.data,
            'MAIL_FROM': form.MAIL_FROM.data,
            'MAIL_SUPPRESS_SEND': str(form.MAIL_SUPPRESS_SEND.data),
            'ENABLE_PASSWORD_RESET': str(form.ENABLE_PASSWORD_RESET.data)
        }

        mail_use_tls = form.MAIL_SECURITY_PROTOCOL.data == 'tls'
        mail_use_ssl = form.MAIL_SECURITY_PROTOCOL.data == 'ssl'
        settings_to_save['MAIL_USE_TLS'] = str(mail_use_tls)
        settings_to_save['MAIL_USE_SSL'] = str(mail_use_ssl)

        for key, value in settings_to_save.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            value_to_save = value
            if key == 'MAIL_PASSWORD' and value:
                encrypted_value = encrypt_value(value, current_app.config['ENCRYPTION_KEY'])
                value_to_save = encrypted_value
            
            if not setting:
                setting = SystemSetting(key=key, value=value_to_save)
                db.session.add(setting)
            else:
                setting.value = value_to_save
        db.session.commit()

        # Immediately reload the app's config to reflect the changes
        current_app.config['MAIL_CONFIG_SOURCE'] = form.MAIL_CONFIG_SOURCE.data
        if current_app.config['MAIL_CONFIG_SOURCE'] == 'database':
            current_app.config.update(
                MAIL_SERVER=settings_to_save['MAIL_SERVER'],
                MAIL_PORT=int(settings_to_save['MAIL_PORT']) if settings_to_save['MAIL_PORT'] else 587,
                MAIL_USE_TLS=mail_use_tls,
                MAIL_USE_SSL=mail_use_ssl,
                MAIL_USERNAME=settings_to_save['MAIL_USERNAME'],
                MAIL_PASSWORD=settings_to_save['MAIL_PASSWORD'],
                MAIL_FROM=settings_to_save['MAIL_FROM'],
                MAIL_SUPPRESS_SEND=settings_to_save['MAIL_SUPPRESS_SEND'].lower() == 'true',
                ENABLE_PASSWORD_RESET=settings_to_save['ENABLE_PASSWORD_RESET'].lower() == 'true'
            )
        else: # Reload from environment
            current_app.config.update(
                MAIL_SERVER=os.getenv('MAIL_SERVER', ''),
                MAIL_PORT=int(os.getenv('MAIL_PORT', 587)),
                MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'False').lower() == 'true',
                MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'False').lower() == 'true',
                MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
                MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
                MAIL_FROM=os.getenv('MAIL_FROM', 'no-reply@example.com'),
                MAIL_SUPPRESS_SEND=os.getenv('MAIL_SUPPRESS_SEND', 'True').lower() == 'true',
                ENABLE_PASSWORD_RESET=os.getenv('ENABLE_PASSWORD_RESET', 'False').lower() == 'true'
            )

        flash('Email settings have been saved. A restart may be required for all changes to take effect.', 'success')
        return redirect(url_for('admin.email_settings'))

    # Populate form for GET requests, always showing the values from the database.
    from config import get_setting_from_db
    form.MAIL_CONFIG_SOURCE.data = get_setting_from_db(current_app, 'MAIL_CONFIG_SOURCE', 'environment')
    form.MAIL_SERVER.data = get_setting_from_db(current_app, 'MAIL_SERVER', '')
    form.MAIL_PORT.data = int(get_setting_from_db(current_app, 'MAIL_PORT', 587))
    
    if get_setting_from_db(current_app, 'MAIL_USE_TLS', 'False').lower() == 'true':
        form.MAIL_SECURITY_PROTOCOL.data = 'tls'
    elif get_setting_from_db(current_app, 'MAIL_USE_SSL', 'False').lower() == 'true':
        form.MAIL_SECURITY_PROTOCOL.data = 'ssl'
    else:
        form.MAIL_SECURITY_PROTOCOL.data = 'none'

    form.MAIL_USERNAME.data = get_setting_from_db(current_app, 'MAIL_USERNAME', '')
    form.MAIL_FROM.data = get_setting_from_db(current_app, 'MAIL_FROM', '')
    form.MAIL_SUPPRESS_SEND.data = get_setting_from_db(current_app, 'MAIL_SUPPRESS_SEND', 'False').lower() == 'true'
    form.ENABLE_PASSWORD_RESET.data = get_setting_from_db(current_app, 'ENABLE_PASSWORD_RESET', 'False').lower() == 'true'

    # Pass environment variables to the template for display purposes
    env_vars = {
        'MAIL_SERVER': os.getenv('MAIL_SERVER', 'Not Set'),
        'MAIL_PORT': os.getenv('MAIL_PORT', 'Not Set'),
        'MAIL_USE_TLS': os.getenv('MAIL_USE_TLS', 'Not Set'),
        'MAIL_USE_SSL': os.getenv('MAIL_USE_SSL', 'Not Set'),
        'MAIL_USERNAME': os.getenv('MAIL_USERNAME', 'Not Set'),
        'MAIL_PASSWORD': '********' if os.getenv('MAIL_PASSWORD') else 'Not Set',
        'MAIL_FROM': os.getenv('MAIL_FROM', 'Not Set'),
        'MAIL_SUPPRESS_SEND': os.getenv('MAIL_SUPPRESS_SEND', 'Not Set'),
        'ENABLE_PASSWORD_RESET': os.getenv('ENABLE_PASSWORD_RESET', 'Not Set'),
    }

    return render_template('admin/email_settings.html', title='Email Settings', form=form, env_vars=env_vars)