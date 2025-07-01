from flask import render_template
from flask_login import login_required, current_user
from . import dashboard_bp
from models import DailyLog, Food
from datetime import date

@dashboard_bp.route('/')
@login_required
def index():
    daily_logs = DailyLog.query.filter_by(user_id=current_user.id, log_date=date.today()).all()
    
    # This is inefficient, but will work for now.
    # A better solution would be to join the tables in the query.
    food_names = {}
    for log in daily_logs:
        if log.fdc_id:
            food = Food.query.get(log.fdc_id)
            if food:
                food_names[log.id] = food.description

    return render_template('dashboard.html', daily_logs=daily_logs, food_names=food_names)