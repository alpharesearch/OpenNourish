"""Coverage + regression tests for opennourish/fasting/routes.py.

Regression contract (opennourish/AGENTS.md Work Guidance): the fasting routes
must never raise on a stored timezone the system cannot load (settings used to
store arbitrary strings); they fall back to UTC via resolve_timezone.
"""

from datetime import datetime, timedelta

from models import db, FastingSession, User


def _set_timezone(app, username, value):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        user.timezone = value
        db.session.commit()


def _active_fast(app, username, hours_ago=3, planned=16):
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(hours=hours_ago),
            planned_duration_hours=planned,
            status="active",
        )
        db.session.add(fast)
        db.session.commit()
        return fast.id


def test_index_empty_and_with_history(auth_client, app_with_db):
    response = auth_client.get("/fasting/")
    assert response.status_code == 200

    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        db.session.add(
            FastingSession(
                user_id=user.id,
                start_time=datetime.utcnow() - timedelta(hours=20),
                end_time=datetime.utcnow() - timedelta(hours=2),
                planned_duration_hours=18,
                status="completed",
            )
        )
        db.session.commit()
    response = auth_client.get("/fasting/", follow_redirects=True)
    assert response.status_code == 200


def test_start_fast_uses_duration_then_goal_default_then_16(auth_client, app_with_db):
    auth_client.post("/fasting/start", data={"duration": "18.5"})
    with app_with_db.app_context():
        fast = FastingSession.query.one()
        assert fast.planned_duration_hours == 18

    # A second start is refused while one is active.
    response = auth_client.post("/fasting/start", follow_redirects=True)
    assert b"You already have an active fast." in response.data
    assert FastingSession.query.count() == 1

    # Garbage duration falls back to the goal default (fixture goal: 16).
    auth_client.post("/fasting/end")
    response = auth_client.post("/fasting/start", data={"duration": "abc"})
    assert response.status_code == 302
    with app_with_db.app_context():
        assert FastingSession.query.count() == 2
        assert (
            FastingSession.query.order_by(FastingSession.id.desc())
            .first()
            .planned_duration_hours
            == 16
        )


def test_end_fast_without_active(auth_client):
    response = auth_client.post("/fasting/end", follow_redirects=True)
    assert b"No active fast to end." in response.data


def test_edit_start_time_requires_active_fast(auth_client):
    response = auth_client.post(
        "/fasting/edit_start_time",
        data={"start_time": "2026-01-01T08:00"},
        follow_redirects=True,
    )
    assert b"No active fast to edit." in response.data


def test_edit_start_time_rejects_future_and_invalid(auth_client, app_with_db):
    fast_id = _active_fast(app_with_db, "testuser")
    future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    auth_client.post("/fasting/edit_start_time", data={"start_time": future})
    with app_with_db.app_context():
        fast = db.session.get(FastingSession, fast_id)
        # Rejected: still ~3 hours ago, not tomorrow.
        assert fast.start_time > datetime.utcnow() - timedelta(hours=4)

    response = auth_client.post(
        "/fasting/edit_start_time", data={"start_time": ""}, follow_redirects=True
    )
    assert b"Error in Start Time" in response.data


def test_edit_start_time_survives_garbage_timezone(auth_client, app_with_db):
    """A corrupted stored timezone must not crash the timezone conversion."""
    fast_id = _active_fast(app_with_db, "testuser")
    _set_timezone(app_with_db, "testuser", "Not/AZone")
    past = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    response = auth_client.post(
        "/fasting/edit_start_time",
        data={"start_time": past},
        follow_redirects=True,
    )
    assert b"Fast start time updated successfully." in response.data
    with app_with_db.app_context():
        assert db.session.get(FastingSession, fast_id).start_time is not None


def test_update_fast_validation_and_edges(auth_client, app_with_db):
    response = auth_client.post(
        "/fasting/update_fast/999999",
        data={"start_time": "2026-01-01T08:00"},
        follow_redirects=True,
    )
    assert b"Fast not found." in response.data

    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(hours=5),
            planned_duration_hours=16,
            status="completed",
        )
        db.session.add(fast)
        db.session.commit()
        fast_id = fast.id

    # End before start is rejected.
    response = auth_client.post(
        "/fasting/update_fast/{}".format(fast_id),
        data={
            "start_time": "2026-01-02T12:00",
            "end_time": "2026-01-02T09:00",
        },
        follow_redirects=True,
    )
    assert b"End time must be after start time." in response.data

    # Valid pair is stored (UTC = user-local minus offset; timezone is UTC here).
    response = auth_client.post(
        "/fasting/update_fast/{}".format(fast_id),
        data={
            "start_time": "2026-01-02T08:00",
            "end_time": "2026-01-02T12:00",
        },
        follow_redirects=True,
    )
    assert b"Fast updated successfully." in response.data
    with app_with_db.app_context():
        stored = db.session.get(FastingSession, fast_id)
        assert stored.start_time == datetime(2026, 1, 2, 8, 0)
        assert stored.end_time == datetime(2026, 1, 2, 12, 0)

    # Missing required field flashes the validation errors.
    response = auth_client.post(
        "/fasting/update_fast/{}".format(fast_id),
        data={"start_time": "", "end_time": ""},
        follow_redirects=True,
    )
    assert b"Error in Start Time" in response.data


def test_update_fast_survives_garbage_timezone(auth_client, app_with_db):
    _set_timezone(app_with_db, "testuser", "garbage//zone")
    with app_with_db.app_context():
        user = User.query.filter_by(username="testuser").one()
        fast = FastingSession(
            user_id=user.id,
            start_time=datetime.utcnow() - timedelta(hours=5),
            planned_duration_hours=16,
            status="active",
        )
        db.session.add(fast)
        db.session.commit()
        fast_id = fast.id
    response = auth_client.post(
        "/fasting/update_fast/{}".format(fast_id),
        data={"start_time": "2026-01-02T08:00"},
        follow_redirects=True,
    )
    assert b"Fast updated successfully." in response.data


def test_delete_fast_owner_and_stranger(auth_client_two_users, app_with_db):
    client_two, user_one, user_two = auth_client_two_users
    # A fast belonging to user_one: user_two must not be able to delete it.
    with app_with_db.app_context():
        stranger = User(username="stranger", email="stranger@example.com")
        stranger.set_password("password")
        db.session.add(stranger)
        db.session.commit()
        foreign_fast = FastingSession(
            user_id=stranger.id,
            start_time=datetime.utcnow() - timedelta(hours=2),
            planned_duration_hours=16,
            status="active",
        )
        own_fast = FastingSession(
            user_id=user_one.id,
            start_time=datetime.utcnow() - timedelta(hours=2),
            planned_duration_hours=16,
            status="active",
        )
        db.session.add_all([foreign_fast, own_fast])
        db.session.commit()
        foreign_id = foreign_fast.id
        own_id = own_fast.id

    response = client_two.post(
        f"/fasting/delete_fast/{foreign_id}", follow_redirects=True
    )
    assert (
        b"Fast not found or you do not have permission to delete it." in response.data
    )
    with app_with_db.app_context():
        assert db.session.get(FastingSession, foreign_id) is not None

    response = client_two.post(f"/fasting/delete_fast/{own_id}", follow_redirects=True)
    assert b"Fast deleted." in response.data
    with app_with_db.app_context():
        assert db.session.get(FastingSession, own_id) is None
