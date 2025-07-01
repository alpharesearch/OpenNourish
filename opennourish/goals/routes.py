from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from . import bp
from .forms import GoalForm
from models import db, UserGoal

@bp.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    user_goal = UserGoal.query.filter_by(user_id=current_user.id).first()
    form = GoalForm(obj=user_goal)

    if form.validate_on_submit():
        if user_goal:
            form.populate_obj(user_goal)
        else:
            user_goal = UserGoal(user_id=current_user.id)
            form.populate_obj(user_goal)
            db.session.add(user_goal)
        
        db.session.commit()
        flash('Goals updated!', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('goals/goals.html', form=form)