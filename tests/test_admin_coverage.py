"""Coverage tests for opennourish/admin/routes.py beyond the privilege tests.

Focus areas per opennourish/admin/AGENTS.md: the email-settings encryption
round-trip, the environment-reload branch, validation errors, the
user-toggle not-found branches, and the cleanup in-use/safe split.
"""

from datetime import date
import re

from cryptography.fernet import Fernet

from models import db, DailyLog, MyFood, MyMeal, Recipe, SystemSetting
from opennourish.utils import decrypt_value, encrypt_value

TOGGLE_ACTIONS = [
    "make-key-user",
    "remove-key-user",
    "disable",
    "enable",
    "verify",
    "unverify",
    "make-public",
    "make-private",
    "complete_onboarding",
    "reset_onboarding",
]


def test_email_settings_get_populates_from_db_and_env_section(admin_client):
    client, _user, app = admin_client
    # create_app(dict) never calls from_object(Config), so the test app has
    # no ENCRYPTION_KEY; the route reads it from the config.
    app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    with app.app_context():
        db.session.add_all(
            [
                SystemSetting(key="MAIL_CONFIG_SOURCE", value="database"),
                SystemSetting(key="MAIL_SERVER", value="smtp.db.test"),
                SystemSetting(key="MAIL_PORT", value="2525"),
                SystemSetting(key="MAIL_USE_TLS", value="True"),
                SystemSetting(key="MAIL_USERNAME", value="mailer"),
                SystemSetting(
                    key="MAIL_PASSWORD",
                    value=encrypt_value(
                        "correct horse battery staple",
                        app.config["ENCRYPTION_KEY"],
                    ),
                ),
            ]
        )
        db.session.commit()

    response = client.get("/admin/email", follow_redirects=True)
    assert response.status_code == 200
    assert b"smtp.db.test" in response.data
    assert b"2525" in response.data
    assert b"mailer" in response.data
    # The stored password must never be echoed back into the form.
    assert b"correct horse" not in response.data


def test_email_settings_post_encrypts_password_and_reloads(admin_client):
    client, _user, app = admin_client
    app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    password = "correct horse battery staple"
    response = client.post(
        "/admin/email",
        data={
            "MAIL_CONFIG_SOURCE": "database",
            "MAIL_SECURITY_PROTOCOL": "tls",
            "MAIL_SERVER": "smtp.db.test",
            "MAIL_PORT": "587",
            "MAIL_USERNAME": "mailer",
            "MAIL_PASSWORD": password,
            "MAIL_FROM": "noreply@example.com",
            "MAIL_SUPPRESS_SEND": "true",
            "submit": "Save Email Settings",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        stored = SystemSetting.query.filter_by(key="MAIL_PASSWORD").first()
        assert stored is not None
        assert stored.value != password
        decrypted = decrypt_value(stored.value, app.config["ENCRYPTION_KEY"])
        assert decrypted == password
        assert SystemSetting.query.filter_by(key="MAIL_USE_TLS").first().value == "True"
    # Config reloads with the plaintext value for the running app.
    assert app.config["MAIL_PASSWORD"] == password
    assert app.config["MAIL_SERVER"] == "smtp.db.test"

    # Second POST exercises the update-existing-setting branch.
    response = client.post(
        "/admin/email",
        data={
            "MAIL_CONFIG_SOURCE": "database",
            "MAIL_SECURITY_PROTOCOL": "ssl",
            "MAIL_SERVER": "smtp.db.test",
            "MAIL_PORT": "465",
            "MAIL_SUPPRESS_SEND": "true",
            "submit": "Save Email Settings",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert SystemSetting.query.filter_by(key="MAIL_USE_SSL").first().value == "True"
        assert (
            SystemSetting.query.filter_by(key="MAIL_USE_TLS").first().value == "False"
        )
        assert SystemSetting.query.filter_by(key="MAIL_PORT").first().value == "465"


def test_email_settings_post_rejects_missing_mail_fields(admin_client):
    client, _user, _app = admin_client
    response = client.post(
        "/admin/email",
        data={
            "MAIL_CONFIG_SOURCE": "database",
            "MAIL_SECURITY_PROTOCOL": "tls",
            "ENABLE_PASSWORD_RESET": "true",
            "submit": "Save Email Settings",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Mail Server is required when enabling email features." in response.data
    assert b"Mail Port is required when enabling email features." in response.data
    assert b"Mail From Address is required when enabling email features." in (
        response.data
    )


def test_email_settings_post_environment_source_reloads_from_env(
    admin_client, monkeypatch
):
    client, _user, app = admin_client
    monkeypatch.setenv("MAIL_SERVER", "smtp.env.test")
    monkeypatch.setenv("MAIL_PORT", "2587")
    monkeypatch.setenv("MAIL_FROM", "noreply@env.test")
    response = client.post(
        "/admin/email",
        data={
            "MAIL_CONFIG_SOURCE": "environment",
            "MAIL_SECURITY_PROTOCOL": "none",
            "submit": "Save Email Settings",
        },
    )
    assert response.status_code == 302
    assert app.config["MAIL_CONFIG_SOURCE"] == "environment"
    assert app.config["MAIL_SERVER"] == "smtp.env.test"
    assert app.config["MAIL_PORT"] == 2587
    with app.app_context():
        source = SystemSetting.query.filter_by(key="MAIL_CONFIG_SOURCE").first()
        assert source.value == "environment"


def test_admin_settings_updates_existing_setting(admin_client):
    client, _user, app = admin_client
    # First POST creates the row, second one updates it.
    client.post("/admin/settings", data={"allow_registration": "true", "submit": "x"})
    client.post("/admin/settings", data={"submit": "x"})
    with app.app_context():
        setting = SystemSetting.query.filter_by(key="allow_registration").first()
        assert setting is not None
        assert setting.value == "False"

    response = client.get("/admin/settings")
    assert response.status_code == 200
    # A stored False must render the checkbox unchecked (not the default True).
    assert b"checked" not in response.data


def test_user_toggle_routes_flash_when_user_missing(admin_client):
    client, _user, _app = admin_client
    for action in TOGGLE_ACTIONS:
        response = client.post(f"/admin/users/999999/{action}", follow_redirects=True)
        assert response.status_code == 200, action
        assert b"User not found." in response.data, action


def test_cleanup_lists_in_use_and_safe_orphans_and_run_deletes(admin_client):
    client, user, app = admin_client
    with app.app_context():
        referenced_orphan_food = MyFood(
            user_id=None, description="Orphan Referenced Food", calories_per_100g=1
        )
        db.session.add(referenced_orphan_food)
        db.session.commit()
        db.session.add(
            DailyLog(
                user_id=user.id,
                log_date=date.today(),
                meal_name="Breakfast",
                my_food_id=referenced_orphan_food.id,
                amount_grams=10,
            )
        )
        db.session.add(Recipe(user_id=None, name="Orphan Safe Recipe"))
        db.session.add(MyMeal(user_id=None, name="Orphan Safe Meal"))
        db.session.commit()

    response = client.get("/admin/cleanup")
    assert response.status_code == 200
    assert b"Orphan Referenced Food" in response.data
    assert b"Orphan Safe Recipe" in response.data

    # Run: referenced orphan food must survive; recipe and meal must go.
    response = client.post("/admin/cleanup/run", follow_redirects=True)
    assert response.status_code == 200
    assert (
        b"Removed 0 orphaned food items, 1 orphaned recipes, and 1 orphaned meals."
        in (response.data)
    )
    with app.app_context():
        assert Recipe.query.filter_by(name="Orphan Safe Recipe").first() is None
        assert MyMeal.query.filter_by(name="Orphan Safe Meal").first() is None
        assert MyFood.query.filter_by(description="Orphan Referenced Food").first()

        # Drop the reference, then the food is safe to delete too.
        DailyLog.query.delete()
        db.session.commit()

    response = client.post("/admin/cleanup/run", follow_redirects=True)
    assert (
        b"Removed 1 orphaned food items, 0 orphaned recipes, and 0 orphaned meals."
        in (response.data)
    )
    with app.app_context():
        assert MyFood.query.filter_by(description="Orphan Referenced Food").first() is (
            None
        )


def test_email_settings_ssl_protocol_populates_from_db(admin_client):
    client, _user, app = admin_client
    app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    with app.app_context():
        db.session.add_all(
            [
                SystemSetting(key="MAIL_CONFIG_SOURCE", value="database"),
                SystemSetting(key="MAIL_USE_SSL", value="True"),
            ]
        )
        db.session.commit()
    response = client.get("/admin/email")
    assert response.status_code == 200
    # MAIL_USE_TLS absent, MAIL_USE_SSL True -> the ssl radio must be checked.
    # Attribute order is WTForms-controlled; match either order.
    assert re.search(
        rb'<input[^>]*value="ssl"[^>]*\bchecked|\bchecked[^>]*value="ssl"',
        response.data,
    ), "ssl radio not checked"


def test_email_settings_invalid_email_short_circuits_custom_validate(admin_client):
    client, _user, app = admin_client
    app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    # A syntactically invalid MAIL_FROM makes the parent validate() fail, so the
    # custom database-source requirements never run; nothing must be stored.
    response = client.post(
        "/admin/email",
        data={
            "MAIL_CONFIG_SOURCE": "database",
            "MAIL_SECURITY_PROTOCOL": "tls",
            "MAIL_SERVER": "smtp.db.test",
            "MAIL_PORT": "587",
            "MAIL_FROM": "not-an-email",
            "submit": "Save Email Settings",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid email address." in response.data
    with app.app_context():
        assert SystemSetting.query.filter_by(key="MAIL_FROM").first() is None
