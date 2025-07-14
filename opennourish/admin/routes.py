from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required
from opennourish.decorators import admin_required
from . import admin_bp
from .forms import AdminSettingsForm
import json
import os

from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required
from opennourish.decorators import admin_required
from . import admin_bp
from .forms import AdminSettingsForm
import json
import os
from models import db, User, Recipe, MyFood, DailyLog, ExerciseLog, SystemSetting

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