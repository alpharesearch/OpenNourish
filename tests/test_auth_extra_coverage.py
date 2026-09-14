"""Extra coverage for ``opennourish/auth/routes.py``.

``tests/test_auth.py`` and ``tests/test_email_verification.py`` cover the main
flows; the tests here fill the remaining branches: rejected logins, the
authenticated short-circuits, the admin-bootstrap rules, and both redirect
targets of the verification routes.
"""

import jwt
import pytest
from flask import url_for

from models import db, User


def _make_user(app, username, **kwargs):
    """Create a user with a known password and return its id."""
    with app.app_context():
        user = User(username=username, email=f"{username}@example.com", **kwargs)
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        return user.id


def _login_session(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _token(app, user_id, purpose, **kwargs):
    with app.app_context():
        return db.session.get(User, user_id).get_token(purpose=purpose, **kwargs)


def _is_verified(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().is_verified


def _is_admin(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().is_admin


@pytest.fixture
def enable_email_verification(app_with_db):
    app_with_db.config["ENABLE_EMAIL_VERIFICATION"] = True


@pytest.fixture
def enable_password_reset(app_with_db):
    app_with_db.config["ENABLE_PASSWORD_RESET"] = True


# --- login ---


def test_login_rejects_wrong_password(client, app_with_db):
    """An existing account with the wrong password gets the generic flash."""
    _make_user(app_with_db, "rightpass")

    response = client.post(
        url_for("auth.login"),
        data={"username_or_email": "rightpass", "password": "wrong"},
        follow_redirects=True,
    )

    assert b"Invalid username or password" in response.data
    assert b'href="/auth/logout"' not in response.data


def test_login_rejects_unknown_account(client):
    """An unknown identifier produces the same flash as a wrong password."""
    response = client.post(
        url_for("auth.login"),
        data={"username_or_email": "ghost", "password": "password"},
        follow_redirects=True,
    )

    assert b"Invalid username or password" in response.data


def test_login_rejects_disabled_account(client, app_with_db):
    """A disabled account is turned away even with the right password."""
    _make_user(app_with_db, "disabled", is_active=False)

    response = client.post(
        url_for("auth.login"),
        data={"username_or_email": "disabled", "password": "password"},
        follow_redirects=True,
    )

    assert b"This account has been disabled." in response.data
    assert b'href="/auth/logout"' not in response.data


def test_login_with_email_and_remember_me_honours_next(client, app_with_db):
    """E-mail login, remember-me, and a safe relative next target."""
    user_id = _make_user(app_with_db, "emaillogin")

    response = client.post(
        "/auth/login?next=/goals",
        data={
            "username_or_email": "emaillogin@example.com",
            "password": "password",
            "remember_me": "y",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/goals")
    # The remember flag is consumed by Flask-Login's after_request hook, which
    # leaves a remember_token cookie behind instead of a session key.
    assert "remember_token" in response.headers.get("Set-Cookie", "")
    with client.session_transaction() as sess:
        assert sess["_user_id"] == str(user_id)


def test_login_rejects_open_redirect_next(client, app_with_db):
    """An absolute next target is replaced by the app's own index."""
    _make_user(app_with_db, "redirectme")

    response = client.post(
        "/auth/login?next=https://evil.example.com/phish",
        data={"username_or_email": "redirectme", "password": "password"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "evil.example.com" not in response.headers["Location"]


def test_login_grants_admin_from_environment(client, app_with_db, monkeypatch):
    """A login whose username matches INITIAL_ADMIN_USERNAME becomes admin."""
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "czarny")
    _make_user(app_with_db, "czarny")

    response = client.post(
        url_for("auth.login"),
        data={"username_or_email": "czarny", "password": "password"},
        follow_redirects=True,
    )

    assert b"You have been granted administrator privileges." in response.data
    assert _is_admin(app_with_db, "czarny") is True


def test_login_of_signed_in_user_is_redirected_to_index(auth_client):
    """An authenticated visitor never sees the login form again."""
    response = auth_client.get(url_for("auth.login"), follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_logout_ends_the_session(auth_client):
    """logout clears the identity and returns to the index."""
    response = auth_client.get(url_for("auth.logout"), follow_redirects=False)

    assert response.status_code == 302
    with auth_client.session_transaction() as sess:
        assert "_user_id" not in sess


# --- register ---


def test_register_redirects_signed_in_user(auth_client):
    """Registration is closed to an already authenticated visitor."""
    response = auth_client.get(url_for("auth.register"), follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_first_registrant_becomes_admin(client, app_with_db, monkeypatch):
    """With no INITIAL_ADMIN_USERNAME the first account gets admin."""
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)

    response = client.post(
        url_for("auth.register"),
        data={
            "username": "firstone",
            "email": "firstone@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _is_admin(app_with_db, "firstone") is True


def test_register_keeps_later_users_plain(client, app_with_db, monkeypatch):
    """With INITIAL_ADMIN_USERNAME set, nobody else is elevated."""
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "chosenadmin")

    for username in ("chosenadmin", "latecomer"):
        response = client.post(
            url_for("auth.register"),
            data={
                "username": username,
                "email": f"{username}@example.com",
                "password": "password",
                "password2": "password",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        client.get(url_for("auth.logout"))

    assert _is_admin(app_with_db, "chosenadmin") is True
    assert _is_admin(app_with_db, "latecomer") is False


def test_register_sends_verification_mail(
    client, app_with_db, enable_email_verification
):
    """Enabling verification mails the new account and says so."""
    response = client.post(
        url_for("auth.register"),
        data={
            "username": "mailme",
            "email": "mailme@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert _is_verified(app_with_db, "mailme") is False
    # The verification mail is queued through the shared Mail instance.
    from opennourish import mail

    assert mail.send_message.call_count == 1


def test_register_with_existing_goals_lands_on_dashboard(client, mocker):
    """A returning account that already has goals skips the goal wizard."""

    class StubQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return object()

    class StubUserGoal:
        query = StubQuery()

    mocker.patch("opennourish.auth.routes.UserGoal", StubUserGoal)

    response = client.post(
        url_for("auth.register"),
        data={
            "username": "returning",
            "email": "returning@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]


def test_register_without_goals_lands_on_goal_wizard(client):
    """A brand-new account is sent to the goal wizard instead."""
    response = client.post(
        url_for("auth.register"),
        data={
            "username": "brandnew",
            "email": "brandnew@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/goals" in response.headers["Location"]


def test_register_rejects_duplicate_email(client, app_with_db):
    """A taken e-mail address fails form validation and re-renders the form."""
    _make_user(app_with_db, "taken")

    response = client.post(
        url_for("auth.register"),
        data={
            "username": "freshname",
            "email": "taken@example.com",
            "password": "password",
            "password2": "password",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Please use a different email address." in response.data


def test_register_rejects_password_mismatch(client):
    """A mismatched confirmation password re-renders the form without a new user."""
    response = client.post(
        url_for("auth.register"),
        data={
            "username": "mismatch",
            "email": "mismatch@example.com",
            "password": "password",
            "password2": "other",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Field must be equal" in response.data


# --- password reset ---


def test_reset_password_request_disabled(client):
    """With the feature off the route bounces back to the login page."""
    response = client.post(
        url_for("auth.reset_password_request"),
        data={"email": "whoever@example.com"},
        follow_redirects=True,
    )

    assert b"Password reset feature is currently disabled." in response.data


def test_reset_password_request_redirects_signed_in_user(
    auth_client, enable_password_reset
):
    """A signed-in user is sent to the index instead."""
    response = auth_client.get(
        url_for("auth.reset_password_request"), follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_reset_password_request_unknown_email(
    client, app_with_db, enable_password_reset, mocker
):
    """An unknown address is reported and no mail is sent."""
    send = mocker.patch("opennourish.auth.routes.send_password_reset_email")

    response = client.post(
        url_for("auth.reset_password_request"),
        data={"email": "nobody@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Email address not found." in response.data
    assert send.call_count == 0


def test_reset_password_redirects_signed_in_user(auth_client, app_with_db):
    """A signed-in user cannot consume a reset link."""
    user_id = _make_user(app_with_db, "signedin_reset")
    token = _token(app_with_db, user_id, "reset-password")

    response = auth_client.get(
        url_for("auth.reset_password", token=token), follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_reset_password_rejects_expired_token(
    client, app_with_db, enable_password_reset
):
    """An expired token is invalid and redirects to the request form."""
    user_id = _make_user(app_with_db, "expired")
    token = _token(app_with_db, user_id, "reset-password", expires_in=-30)

    response = client.get(
        url_for("auth.reset_password", token=token), follow_redirects=True
    )

    assert b"That is an invalid or expired token" in response.data
    assert "/auth/reset_password_request" in response.request.path


def test_reset_password_rejects_foreign_signature(client, app_with_db):
    """A token signed with another SECRET_KEY is rejected."""
    user_id = _make_user(app_with_db, "forged")
    forged = jwt.encode(
        {"reset-password": user_id}, "a-different-key", algorithm="HS256"
    )

    response = client.get(
        url_for("auth.reset_password", token=forged), follow_redirects=True
    )

    assert b"That is an invalid or expired token" in response.data


# --- verification e-mail ---


def test_send_verification_requires_login(client):
    """An anonymous POST cannot request a verification mail."""
    response = client.post(
        url_for("auth.send_verification_email_route"), follow_redirects=True
    )

    assert b"Please log in to send a verification email." in response.data


def test_send_verification_requires_feature(auth_client_onboarded):
    """With verification disabled the user is sent to the index."""
    response = auth_client_onboarded.post(
        url_for("auth.send_verification_email_route"), follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_send_verification_for_verified_user(
    client, app_with_db, enable_email_verification
):
    """An already verified account is told so and sent to settings."""
    user_id = _make_user(app_with_db, "verified", is_verified=True)
    _login_session(client, user_id)

    response = client.post(
        url_for("auth.send_verification_email_route"), follow_redirects=False
    )

    assert response.status_code == 302
    assert "/settings" in response.headers["Location"]


def test_send_verification_for_onboarded_user(
    app_with_db, enable_email_verification, mocker
):
    """An onboarded user returns to settings after a new mail."""
    send = mocker.patch("opennourish.auth.routes.send_verification_email")
    user_id = _make_user(app_with_db, "onboarded_verify", has_completed_onboarding=True)

    with app_with_db.test_client() as client:
        _login_session(client, user_id)
        response = client.post(
            url_for("auth.send_verification_email_route"), follow_redirects=False
        )

    assert response.status_code == 302
    assert "/settings" in response.headers["Location"]
    assert send.call_count == 1


def test_send_verification_for_new_user(app_with_db, enable_email_verification, mocker):
    """A user who has not finished onboarding is returned to step 1."""
    mocker.patch("opennourish.auth.routes.send_verification_email")
    user_id = _make_user(app_with_db, "fresh_verify")

    with app_with_db.test_client() as client:
        _login_session(client, user_id)
        response = client.post(
            url_for("auth.send_verification_email_route"), follow_redirects=False
        )

    assert response.status_code == 302
    assert "/onboarding" in response.headers["Location"]


def test_verify_email_rejects_invalid_token(client):
    """A junk token sends the visitor back to the login page."""
    response = client.get(
        url_for("auth.verify_email", token="not-a-real-token"), follow_redirects=True
    )

    assert b"That is an invalid or expired verification link." in response.data
    assert "/auth/login" in response.request.path


def test_verify_email_rejects_expired_token(client, app_with_db):
    """An expired verification link is handled like a forged one."""
    user_id = _make_user(app_with_db, "expired_verify")
    token = _token(app_with_db, user_id, "verify-email", expires_in=-30)

    response = client.get(
        url_for("auth.verify_email", token=token), follow_redirects=True
    )

    assert b"That is an invalid or expired verification link." in response.data
    assert _is_verified(app_with_db, "expired_verify") is False


def test_verify_email_lands_onboarded_user_on_dashboard(app_with_db):
    """Verifying an onboarded account redirects to the dashboard."""
    user_id = _make_user(app_with_db, "done_onboarding", has_completed_onboarding=True)
    token = _token(app_with_db, user_id, "verify-email")

    with app_with_db.test_client() as client:
        response = client.get(
            url_for("auth.verify_email", token=token), follow_redirects=False
        )

    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]
    assert _is_verified(app_with_db, "done_onboarding") is True


def test_verify_email_lands_new_user_on_onboarding(app_with_db):
    """A brand-new account is pushed into onboarding after verifying."""
    user_id = _make_user(app_with_db, "new_signup")
    token = _token(app_with_db, user_id, "verify-email")

    with app_with_db.test_client() as client:
        response = client.get(
            url_for("auth.verify_email", token=token), follow_redirects=False
        )

    assert response.status_code == 302
    assert "/onboarding" in response.headers["Location"]
    assert _is_verified(app_with_db, "new_signup") is True


def test_verify_email_for_already_verified_user(app_with_db):
    """Re-visiting the link while signed in reports the current state."""
    user_id = _make_user(app_with_db, "already_ok", is_verified=True)
    token = _token(app_with_db, user_id, "verify-email")

    with app_with_db.test_client() as client:
        _login_session(client, user_id)
        response = client.get(
            url_for("auth.verify_email", token=token), follow_redirects=True
        )

    assert b"Your email is already verified." in response.data
