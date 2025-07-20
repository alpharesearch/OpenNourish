from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
from models import db, User, Friendship, DailyLog, ExerciseLog
from . import friends_bp
from datetime import datetime, timedelta
from sqlalchemy import func

@friends_bp.route('/', methods=['GET'])
@login_required
def friends_page():
    today = datetime.now().date()
    # Calculate the start of the current week (Monday)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Get all accepted friends, including the current user for the scoreboard
    all_users_for_scoreboard = [current_user] + list(current_user.friends)

    scoreboard_data = []
    for user in all_users_for_scoreboard:
        diary_logs_count = DailyLog.query.filter(
            DailyLog.user_id == user.id,
            DailyLog.log_date >= start_of_week,
            DailyLog.log_date <= end_of_week
        ).count()

        exercise_logs_count = ExerciseLog.query.filter(
            ExerciseLog.user_id == user.id,
            ExerciseLog.log_date >= start_of_week,
            ExerciseLog.log_date <= end_of_week
        ).count()

        scoreboard_data.append({
            'username': user.username,
            'diary_logs': diary_logs_count,
            'exercise_logs': exercise_logs_count,
            'total_activity': diary_logs_count + exercise_logs_count,
            'meals_per_day': user.meals_per_day
        })

    # Sort the scoreboard data by total activity in descending order
    scoreboard_data.sort(key=lambda x: x['total_activity'], reverse=True)

    return render_template(
        'friends/friends.html',
        friends=current_user.friends,
        pending_sent=current_user.pending_requests_sent,
        pending_received=current_user.pending_requests_received,
        scoreboard=scoreboard_data,
        start_of_week=start_of_week,
        end_of_week=end_of_week
    )

@friends_bp.route('/add', methods=['POST'])
@login_required
def add_friend():
    if current_app.config.get('ENABLE_EMAIL_VERIFICATION', False) and not current_user.is_verified:
        flash('Please verify your email address to send friend requests.', 'warning')
        return redirect(url_for('friends.friends_page'))

    username = request.form.get('username')
    if not username:
        flash('Username is required.', 'danger')
        return redirect(url_for('friends.friends_page'))

    user_to_add = User.query.filter_by(username=username).first()

    if not user_to_add:
        flash('User not found.', 'danger')
        return redirect(url_for('friends.friends_page'))

    if user_to_add == current_user:
        flash('You cannot add yourself as a friend.', 'warning')
        return redirect(url_for('friends.friends_page'))

    existing_friendship = Friendship.query.filter(
        ((Friendship.requester_id == current_user.id) & (Friendship.receiver_id == user_to_add.id)) |
        ((Friendship.requester_id == user_to_add.id) & (Friendship.receiver_id == current_user.id))
    ).first()

    if existing_friendship:
        flash('Friendship already exists or is pending.', 'warning')
        return redirect(url_for('friends.friends_page'))

    new_friendship = Friendship(requester_id=current_user.id, receiver_id=user_to_add.id)
    db.session.add(new_friendship)
    db.session.commit()
    flash(f'Friend request sent to {username}.', 'success')
    return redirect(url_for('friends.friends_page'))

@friends_bp.route('/request/<int:request_id>/accept', methods=['POST'])
@login_required
def accept_request(request_id):
    friend_request = db.session.get(Friendship, request_id)
    if not friend_request:
        flash('Friend request not found.', 'danger')
        return redirect(url_for('friends.friends_page'))
    if friend_request.receiver_id != current_user.id:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('friends.friends_page'))
    
    friend_request.status = 'accepted'
    db.session.commit()
    flash('Friend request accepted.', 'success')
    return redirect(url_for('friends.friends_page'))

@friends_bp.route('/request/<int:request_id>/decline', methods=['POST'])
@login_required
def decline_request(request_id):
    friend_request = db.session.get(Friendship, request_id)
    if not friend_request:
        flash('Friend request not found.', 'danger')
        return redirect(url_for('friends.friends_page'))
    if friend_request.receiver_id != current_user.id and friend_request.requester_id != current_user.id:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('friends.friends_page'))

    db.session.delete(friend_request)
    db.session.commit()
    flash('Friend request declined.', 'success')
    return redirect(url_for('friends.friends_page'))

@friends_bp.route('/friendship/<int:friend_id>/remove', methods=['POST'])
@login_required
def remove_friend(friend_id):
    friendship = Friendship.query.filter(
        (Friendship.status == 'accepted') &
        (((Friendship.requester_id == current_user.id) & (Friendship.receiver_id == friend_id)) |
         ((Friendship.requester_id == friend_id) & (Friendship.receiver_id == current_user.id)))
    ).first_or_404()

    db.session.delete(friendship)
    db.session.commit()
    flash('Friend removed.', 'success')
    return redirect(url_for('friends.friends_page'))
