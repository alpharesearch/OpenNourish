import pytest
from flask import url_for
from models import User, db


@pytest.fixture
def users(app_with_db):
    with app_with_db.app_context():
        user1 = User(
            username="testuser1",
            email="testuser1@example.com",
            is_verified=False,
            is_private=True,
            has_completed_onboarding=False,
        )
        user1.set_password("password")
        user2 = User(
            username="testuser2",
            email="testuser2@example.com",
            is_verified=True,
            is_private=False,
            has_completed_onboarding=True,
        )
        user2.set_password("password")
        db.session.add_all([user1, user2])
        db.session.commit()
        return [user1.id, user2.id]


@pytest.fixture
def users2(app_with_db):
    with app_with_db.app_context():
        user1 = User(
            username="testuser3",
            email="testuser3@example.com",
            is_verified=False,
            is_private=True,
            has_completed_onboarding=True,
        )
        user1.set_password("password")
        user2 = User(
            username="testuser4",
            email="testuser4@example.com",
            is_verified=True,
            is_private=False,
            has_completed_onboarding=True,
        )
        user2.set_password("password")
        db.session.add_all([user1, user2])
        db.session.commit()
        return [user1.id, user2.id]


def test_list_users(admin_client, users):
    client, _, _ = admin_client
    response = client.get(url_for("admin.users"))
    assert response.status_code == 200
    with client.application.app_context():
        for user_id in users:
            user = db.session.get(User, user_id)
            assert user.username in response.data.decode()


def test_verify_user(admin_client, users):
    client, _, _ = admin_client
    user_to_verify_id = users[0]
    with client.application.app_context():
        user_to_verify = db.session.get(User, user_to_verify_id)
        assert not user_to_verify.is_verified
    response = client.post(
        url_for("admin.verify_user", user_id=user_to_verify_id), follow_redirects=True
    )
    assert response.status_code == 200
    with client.application.app_context():
        verified_user = db.session.get(User, user_to_verify_id)
        assert verified_user.is_verified


def test_unverify_user(admin_client, users):
    client, _, _ = admin_client
    user_to_unverify_id = users[1]
    with client.application.app_context():
        user_to_unverify = db.session.get(User, user_to_unverify_id)
        assert user_to_unverify.is_verified
    response = client.post(
        url_for("admin.unverify_user", user_id=user_to_unverify_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        unverified_user = db.session.get(User, user_to_unverify_id)
        assert not unverified_user.is_verified


def test_make_user_public(admin_client, users):
    client, _, _ = admin_client
    user_to_make_public_id = users[0]
    with client.application.app_context():
        user_to_make_public = db.session.get(User, user_to_make_public_id)
        assert user_to_make_public.is_private
    response = client.post(
        url_for("admin.make_user_public", user_id=user_to_make_public_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        public_user = db.session.get(User, user_to_make_public_id)
        assert not public_user.is_private


def test_make_user_private(admin_client, users):
    client, _, _ = admin_client
    user_to_make_private_id = users[1]
    with client.application.app_context():
        user_to_make_private = db.session.get(User, user_to_make_private_id)
        assert not user_to_make_private.is_private
    response = client.post(
        url_for("admin.make_user_private", user_id=user_to_make_private_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        private_user = db.session.get(User, user_to_make_private_id)
        assert private_user.is_private


def test_complete_onboarding(admin_client, users):
    client, _, _ = admin_client
    user_to_complete_id = users[0]
    with client.application.app_context():
        user_to_complete = db.session.get(User, user_to_complete_id)
        assert not user_to_complete.has_completed_onboarding
    response = client.post(
        url_for("admin.complete_onboarding", user_id=user_to_complete_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        completed_user = db.session.get(User, user_to_complete_id)
        assert completed_user.has_completed_onboarding


def test_reset_onboarding(admin_client, users):
    client, _, _ = admin_client
    user_to_reset_id = users[1]
    with client.application.app_context():
        user_to_reset = db.session.get(User, user_to_reset_id)
        assert user_to_reset.has_completed_onboarding
    response = client.post(
        url_for("admin.reset_onboarding", user_id=user_to_reset_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        reset_user = db.session.get(User, user_to_reset_id)
        assert not reset_user.has_completed_onboarding


def test_make_key_user(admin_client, users):
    client, _, _ = admin_client
    user_to_make_key_id = users[0]
    with client.application.app_context():
        user_to_make_key = db.session.get(User, user_to_make_key_id)
        assert not user_to_make_key.is_key_user
    response = client.post(
        url_for("admin.make_key_user", user_id=user_to_make_key_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        key_user = db.session.get(User, user_to_make_key_id)
        assert key_user.is_key_user


def test_remove_key_user(admin_client, users):
    client, _, _ = admin_client
    user_to_remove_key_id = users[1]
    with client.application.app_context():
        user_to_remove_key = db.session.get(User, user_to_remove_key_id)
        user_to_remove_key.is_key_user = True
        db.session.commit()
        assert user_to_remove_key.is_key_user
    response = client.post(
        url_for("admin.remove_key_user", user_id=user_to_remove_key_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.application.app_context():
        not_key_user = db.session.get(User, user_to_remove_key_id)
        assert not not_key_user.is_key_user


def test_list_users_not_admin(auth_client_with_user):
    client, _ = auth_client_with_user
    response = client.get(url_for("admin.users"), follow_redirects=False)
    assert response.status_code == 302
    assert response.location == url_for("dashboard.index", _external=False)


def test_verify_user_not_admin(auth_client_onboarded, users2):
    client = auth_client_onboarded
    user_to_verify_id = users2[0]
    with client.application.app_context():
        user_to_verify = db.session.get(User, user_to_verify_id)
        assert not user_to_verify.is_verified
    response = client.post(
        url_for("admin.verify_user", user_id=user_to_verify_id), follow_redirects=True
    )
    assert response.status_code == 200
    assert url_for("dashboard.index") in response.request.path
    with client.application.app_context():
        verified_user = db.session.get(User, user_to_verify_id)
        assert not verified_user.is_verified
