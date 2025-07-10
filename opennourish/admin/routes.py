from flask import render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required
from opennourish.decorators import admin_required
from . import admin_bp
from .forms import AdminSettingsForm
import json
import os

@admin_bp.route('/', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    form = AdminSettingsForm()
    settings_file = os.path.join(current_app.instance_path, 'settings.json')
    os.makedirs(current_app.instance_path, exist_ok=True)

    if form.validate_on_submit():
        # Handle POST request to save settings
        allow_registration_value = form.allow_registration.data

        # Read existing settings or create an empty dict if file doesn't exist
        settings_data = {}
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                try:
                    settings_data = json.load(f)
                except json.JSONDecodeError:
                    # Handle empty or invalid JSON file
                    settings_data = {}

        # Update the specific setting
        settings_data['ALLOW_REGISTRATION'] = allow_registration_value

        # Write updated settings back to the file
        with open(settings_file, 'w') as f:
            json.dump(settings_data, f, indent=4)
        
        
        flash('Settings saved!', 'success')
        return redirect(url_for('admin.settings'))

    elif request.method == 'GET':
        # Handle GET request to populate form
        settings_data = {}
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                try:
                    settings_data = json.load(f)
                except json.JSONDecodeError:
                    settings_data = {}

        # Set the checkbox value from settings_data, defaulting to True
        form.allow_registration.data = settings_data.get('ALLOW_REGISTRATION', True)

    return render_template('admin/settings.html', form=form)