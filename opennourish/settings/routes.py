from flask import render_template, flash, redirect, url_for
from flask_login import current_user, login_required
from models import User, db
from .forms import ChangePasswordForm
from . import settings_bp



@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
def settings():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = User.query.get(current_user.id)
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been changed.')
        return redirect(url_for('settings.settings'))
    return render_template('settings/settings.html', title='Settings', form=form)