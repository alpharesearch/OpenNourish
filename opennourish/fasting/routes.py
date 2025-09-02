from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from models import db, FastingSession
from . import fasting_bp
from .forms import EditFastForm
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from opennourish.utils import prepare_undo_and_delete

FASTING_INDEX_ROUTE = "fasting.index"


@fasting_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    per_page = 10  # Or any other number you prefer

    active_fast = FastingSession.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()

    completed_fasts_pagination = (
        FastingSession.query.filter_by(user_id=current_user.id, status="completed")
        .order_by(FastingSession.start_time.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Form for the currently active fast
    edit_form = EditFastForm()
    if active_fast:
        edit_form.start_time.data = active_fast.start_time

    # Create a dictionary of forms for the history section
    forms = {
        fast.id: EditFastForm(obj=fast) for fast in completed_fasts_pagination.items
    }

    return render_template(
        "fasting/fasting.html",
        active_fast=active_fast,
        completed_fasts=completed_fasts_pagination,
        now=datetime.now(timezone.utc),
        form=edit_form,
        forms=forms,
    )


@fasting_bp.route("/start", methods=["POST"])
@login_required
def start_fast():
    active_fast = FastingSession.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()
    if active_fast:
        flash("You already have an active fast.", "warning")
        return redirect(url_for(FASTING_INDEX_ROUTE))

    duration_str = request.form.get("duration")
    try:
        # Convert to float first to handle inputs like '16.5', then to int to truncate
        duration_hours = int(float(duration_str))
    except (ValueError, TypeError):
        duration_hours = (
            current_user.goals.default_fasting_hours if current_user.goals else 16
        )

    new_fast = FastingSession(
        user_id=current_user.id,
        start_time=datetime.now(timezone.utc),
        planned_duration_hours=duration_hours,
    )
    db.session.add(new_fast)
    db.session.commit()
    flash("Fasting period started!", "success")
    return redirect(url_for(FASTING_INDEX_ROUTE))


@fasting_bp.route("/end", methods=["POST"])
@login_required
def end_fast():
    active_fast = FastingSession.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()
    if not active_fast:
        flash("No active fast to end.", "warning")
        return redirect(url_for(FASTING_INDEX_ROUTE))

    active_fast.end_time = datetime.now(timezone.utc)
    active_fast.status = "completed"
    db.session.commit()
    flash("Fasting period completed!", "success")
    return redirect(url_for(FASTING_INDEX_ROUTE))


@fasting_bp.route("/edit_start_time", methods=["POST"])
@login_required
def edit_start_time():
    active_fast = FastingSession.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()
    if not active_fast:
        flash("No active fast to edit.", "warning")
        return redirect(url_for(FASTING_INDEX_ROUTE))

    form = EditFastForm()
    if form.validate_on_submit():
        # Convert naive datetime from form to user's timezone, then to UTC
        user_tz = ZoneInfo(current_user.timezone)
        local_start_time = form.start_time.data.replace(tzinfo=user_tz)
        utc_start_time = local_start_time.astimezone(ZoneInfo("UTC"))

        if utc_start_time > datetime.now(timezone.utc):
            flash("Start time cannot be in the future.", "danger")
        else:
            active_fast.start_time = utc_start_time.replace(
                tzinfo=None
            )  # Store as naive UTC
            db.session.commit()
            flash("Fast start time updated successfully.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", "danger")

    return redirect(url_for(FASTING_INDEX_ROUTE))


@fasting_bp.route("/update_fast/<int:fast_id>", methods=["POST"])
@login_required
def update_fast(fast_id):
    fast = db.session.get(FastingSession, fast_id)
    if not fast or fast.user_id != current_user.id:
        flash("Fast not found.", "danger")
        return redirect(url_for(FASTING_INDEX_ROUTE))

    form = EditFastForm()
    if form.validate_on_submit():
        user_tz = ZoneInfo(current_user.timezone)

        # Handle start time
        local_start_time = form.start_time.data.replace(tzinfo=user_tz)
        utc_start_time = local_start_time.astimezone(ZoneInfo("UTC"))

        # Handle end time
        utc_end_time = None
        if form.end_time.data:
            local_end_time = form.end_time.data.replace(tzinfo=user_tz)
            utc_end_time = local_end_time.astimezone(ZoneInfo("UTC"))

        if utc_start_time and utc_end_time and utc_start_time >= utc_end_time:
            flash("End time must be after start time.", "danger")
        else:
            fast.start_time = utc_start_time.replace(tzinfo=None)
            fast.end_time = utc_end_time.replace(tzinfo=None) if utc_end_time else None
            db.session.commit()
            flash("Fast updated successfully.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", "danger")

    return redirect(url_for(FASTING_INDEX_ROUTE))


@fasting_bp.route("/delete_fast/<int:fast_id>", methods=["POST"])
@login_required
def delete_fast(fast_id):
    fast = db.session.get(FastingSession, fast_id)
    if fast and fast.user_id == current_user.id:
        page = request.args.get("page", 1, type=int)
        redirect_info = {"endpoint": FASTING_INDEX_ROUTE, "params": {"page": page}}
        prepare_undo_and_delete(
            fast, "fasting_session", redirect_info, success_message="Fast deleted."
        )
    else:
        flash("Fast not found or you do not have permission to delete it.", "danger")
    return redirect(url_for(FASTING_INDEX_ROUTE))
