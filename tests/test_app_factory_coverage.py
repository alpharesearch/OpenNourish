"""Coverage tests for the ``create_app`` factory in ``opennourish/__init__.py``.

These exercise the branches the feature blueprints never take: the
``from_object`` configuration path, the database-backed mail settings, the
registered template filter, and every Flask CLI command nested in the factory.
"""

import os

from cryptography.fernet import Fernet

from models import (
    db,
    ExerciseActivity,
    FoodCategory,
    SystemSetting,
    UnifiedPortion,
    User,
)
from opennourish import DEFAULT_MAIL_FROM, create_app

TEST_APP_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    "SQLALCHEMY_BINDS": {"usda": "sqlite:///:memory:"},
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "SECRET_KEY": "test_secret_key",
    "WTF_CSRF_ENABLED": False,
    "SERVER_NAME": "localhost.localdomain:5000",
}


def _make_usda_layout(tmp_path, monkeypatch, app, files):
    """Point ``app.root_path`` at a throwaway package dir and drop the given CSV
    files into ``<tmp_path>/persistent/usda_data``, which the seeders resolve
    relative to ``root_path``."""
    opennourish_dir = tmp_path / "opennourish"
    opennourish_dir.mkdir(exist_ok=True)
    usda_data_dir = tmp_path / "persistent" / "usda_data"
    usda_data_dir.mkdir(parents=True, exist_ok=True)
    for name, contents in files.items():
        (usda_data_dir / name).write_text(contents)
    monkeypatch.setattr(app, "root_path", str(opennourish_dir))


PORTION_CSV_HEADER = "id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight\n"


def test_create_app_accepts_object_style_config():
    """create_app(dict) merges a dict, anything else goes through from_object."""

    class ObjectStyleConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_BINDS = {"usda": "sqlite:///:memory:"}
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SECRET_KEY = "object_style_key"
        WTF_CSRF_ENABLED = False
        SERVER_NAME = "localhost.localdomain:5000"
        MAIL_SUPPRESS_SEND = False

    app = create_app(ObjectStyleConfig)

    assert app.config["SECRET_KEY"] == "object_style_key"
    assert app.config["SERVER_NAME"] == "localhost.localdomain:5000"
    assert app.testing is True
    assert app.config["MAIL_CONFIG_SOURCE"] == "environment"


def test_create_app_reads_mail_settings_from_database(tmp_path, monkeypatch):
    """MAIL_CONFIG_SOURCE=database loads and decrypts every mail setting."""
    encryption_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", encryption_key)

    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'cov_users.db'}",
        "SQLALCHEMY_BINDS": {"usda": f"sqlite:///{tmp_path / 'cov_usda.db'}"},
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SECRET_KEY": "test_secret_key",
    }

    from opennourish.utils import encrypt_value

    seed_app = create_app(config)
    with seed_app.app_context():
        db.create_all()
        settings = {
            "MAIL_CONFIG_SOURCE": "database",
            "MAIL_SERVER": "smtp.internal.example",
            "MAIL_PORT": "2525",
            "MAIL_USE_TLS": "True",
            "MAIL_USE_SSL": "False",
            "MAIL_USERNAME": "mailer",
            "MAIL_PASSWORD": encrypt_value("s3cret", encryption_key),
            "MAIL_FROM": "",
            "MAIL_SUPPRESS_SEND": "False",
            "ENABLE_PASSWORD_RESET": "True",
            "ENABLE_EMAIL_VERIFICATION": "True",
        }
        for key, value in settings.items():
            db.session.add(SystemSetting(key=key, value=value))
        db.session.commit()

    app = create_app(config)

    assert app.config["MAIL_CONFIG_SOURCE"] == "database"
    assert app.config["MAIL_SERVER"] == "smtp.internal.example"
    assert app.config["MAIL_PORT"] == 2525
    assert app.config["MAIL_USE_TLS"] is True
    assert app.config["MAIL_USE_SSL"] is False
    assert app.config["MAIL_USERNAME"] == "mailer"
    assert app.config["MAIL_PASSWORD"] == "s3cret"
    # An empty MAIL_FROM row falls back to the shipped default address.
    assert app.config["MAIL_FROM"] == DEFAULT_MAIL_FROM
    assert app.config["ENABLE_PASSWORD_RESET"] is True
    assert app.config["ENABLE_EMAIL_VERIFICATION"] is True
    assert app.config["USE_CREDENTIALS"] is True
    assert os.environ["ENCRYPTION_KEY"] == encryption_key


def test_create_app_uses_credentials_from_environment(monkeypatch):
    """With a username and password in the environment USE_CREDENTIALS flips on."""
    monkeypatch.setenv("MAIL_USERNAME", "env-user")
    monkeypatch.setenv("MAIL_PASSWORD", "env-password")

    app = create_app(dict(TEST_APP_CONFIG))

    assert app.config["MAIL_CONFIG_SOURCE"] == "environment"
    assert app.config["MAIL_USERNAME"] == "env-user"
    assert app.config["USE_CREDENTIALS"] is True


def test_nl2br_template_filter(app_with_db):
    """The factory registers the nl2br filter used across the templates."""
    with app_with_db.app_context():
        assert app_with_db.jinja_env.filters["nl2br"]("a\nb") == "a<br>b"


def test_init_user_db_command(app_with_db):
    """``flask init-user-db`` is idempotent against an existing schema."""
    result = app_with_db.test_cli_runner().invoke(args=["init-user-db"])

    assert result.exit_code == 0
    assert "Initialized the user database." in result.output


def test_seed_exercise_activities_command(app_with_db):
    """``flask seed-exercise-activities`` seeds and then skips."""
    runner = app_with_db.test_cli_runner()

    result = runner.invoke(args=["seed-exercise-activities"])
    assert "Default exercise activities added." in result.output

    with app_with_db.app_context():
        assert ExerciseActivity.query.count() == 6

    result = runner.invoke(args=["seed-exercise-activities"])
    assert "Exercise activities already exist. Skipping." in result.output


def test_seed_usda_portions_missing_csv(app_with_db, tmp_path, monkeypatch):
    """The portion seeder bails out with a clear message when the CSVs are absent."""
    _make_usda_layout(tmp_path, monkeypatch, app_with_db, {})

    result = app_with_db.test_cli_runner().invoke(args=["seed-usda-portions"])

    assert "Error: USDA data files (measure_unit.csv, food_portion.csv) not found" in (
        result.output
    )
    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 0


def test_seed_usda_portions_removes_duplicates_and_seeds_nothing(
    app_with_db, tmp_path, monkeypatch
):
    """Pre-existing duplicate imported portions are pruned even with nothing to import."""
    _make_usda_layout(
        tmp_path,
        monkeypatch,
        app_with_db,
        {
            "measure_unit.csv": "id,name\n",
            "food_portion.csv": PORTION_CSV_HEADER,
        },
    )

    with app_with_db.app_context():
        duplicated = dict(
            fdc_id=555,
            amount=1.0,
            measure_unit_description="cup",
            portion_description="slice",
            gram_weight=30.0,
            was_imported=True,
        )
        db.session.add_all([UnifiedPortion(**duplicated), UnifiedPortion(**duplicated)])
        db.session.commit()

    result = app_with_db.test_cli_runner().invoke(args=["seed-usda-portions"])

    assert "Removed 1 pre-existing duplicate imported portions." in result.output
    assert "No new USDA portions were found or needed to be added." in result.output
    with app_with_db.app_context():
        assert UnifiedPortion.query.count() == 0


def test_seed_usda_portions_drops_numeric_modifier(app_with_db, tmp_path, monkeypatch):
    """A numeric ``modifier`` in the CSV is discarded instead of stored."""
    _make_usda_layout(
        tmp_path,
        monkeypatch,
        app_with_db,
        {
            "measure_unit.csv": "id,name\n1000,cup\n",
            "food_portion.csv": PORTION_CSV_HEADER
            + "1,4242,1,1.0,1000,wedge,17,40.0\n",
        },
    )

    result = app_with_db.test_cli_runner().invoke(args=["seed-usda-portions"])
    assert "Successfully seeded 1 new USDA portions" in result.output

    with app_with_db.app_context():
        portion = UnifiedPortion.query.filter_by(fdc_id=4242).one()
        assert portion.modifier is None
        assert portion.measure_unit_description == "cup"


def test_deduplicate_portions_command_without_duplicates(app_with_db):
    """``flask deduplicate-portions`` reports when there is nothing to clean."""
    result = app_with_db.test_cli_runner().invoke(args=["deduplicate-portions"])

    assert "No duplicate portions found." in result.output


def test_seed_usda_categories_missing_csv(app_with_db, tmp_path, monkeypatch):
    """The category seeder reports a missing food_category.csv."""
    _make_usda_layout(tmp_path, monkeypatch, app_with_db, {})

    result = app_with_db.test_cli_runner().invoke(args=["seed-usda-categories"])

    assert "Error: USDA data file (food_category.csv) not found" in result.output
    with app_with_db.app_context():
        assert FoodCategory.query.count() == 0


def test_seed_usda_categories_header_only_csv(app_with_db, tmp_path, monkeypatch):
    """A header-only food_category.csv seeds nothing but does not crash."""
    _make_usda_layout(
        tmp_path,
        monkeypatch,
        app_with_db,
        {"food_category.csv": "id,code,description\n"},
    )

    result = app_with_db.test_cli_runner().invoke(args=["seed-usda-categories"])

    assert "No food categories found to seed." in result.output
    with app_with_db.app_context():
        assert FoodCategory.query.count() == 0


def test_manage_admin_command_branches(app_with_db):
    """``flask user manage-admin`` covers the missing user and both no-op branches."""
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        plain = User(username="plainuser", email="plainuser@example.com")
        plain.set_password("password")
        boss = User(username="bossuser", email="bossuser@example.com", is_admin=True)
        boss.set_password("password")
        db.session.add_all([plain, boss])
        db.session.commit()

    result = runner.invoke(args=["user", "manage-admin", "ghost", "--action", "grant"])
    assert "Error: User 'ghost' not found." in result.output

    result = runner.invoke(
        args=["user", "manage-admin", "bossuser", "--action", "grant"]
    )
    assert "User 'bossuser' already has admin privileges." in result.output

    result = runner.invoke(
        args=["user", "manage-admin", "plainuser", "--action", "revoke"]
    )
    assert "User 'plainuser' does not have admin privileges." in result.output

    result = runner.invoke(
        args=["user", "manage-admin", "plainuser", "--action", "grant"]
    )
    assert "Successfully granted admin privileges to 'plainuser'." in result.output
    with app_with_db.app_context():
        assert User.query.filter_by(username="plainuser").one().is_admin is True

    result = runner.invoke(
        args=["user", "manage-admin", "bossuser", "--action", "revoke"]
    )
    assert "Successfully revoked admin privileges from 'bossuser'." in result.output


def test_manage_key_user_command_branches(app_with_db):
    """``flask user manage-key-user`` covers the no-op and effective branches."""
    runner = app_with_db.test_cli_runner()

    with app_with_db.app_context():
        keeper = User(username="keeper", email="keeper@example.com", is_key_user=True)
        keeper.set_password("password")
        newcomer = User(username="newcomer", email="newcomer@example.com")
        newcomer.set_password("password")
        db.session.add_all([keeper, newcomer])
        db.session.commit()

    result = runner.invoke(
        args=["user", "manage-key-user", "ghost", "--action", "grant"]
    )
    assert "Error: User 'ghost' not found." in result.output

    result = runner.invoke(
        args=["user", "manage-key-user", "keeper", "--action", "grant"]
    )
    assert "User 'keeper' already has key user privileges." in result.output

    result = runner.invoke(
        args=["user", "manage-key-user", "newcomer", "--action", "revoke"]
    )
    assert "User 'newcomer' does not have key user privileges." in result.output

    result = runner.invoke(
        args=["user", "manage-key-user", "newcomer", "--action", "grant"]
    )
    assert "Successfully granted key user privileges to 'newcomer'." in result.output
    with app_with_db.app_context():
        assert User.query.filter_by(username="newcomer").one().is_key_user is True

    result = runner.invoke(
        args=["user", "manage-key-user", "keeper", "--action", "revoke"]
    )
    assert "Successfully revoked key user privileges from 'keeper'." in result.output


def test_login_required_redirects_to_login(client):
    """login_manager.login_view sends an anonymous visitor to auth.login."""
    response = client.get("/tracking/progress", follow_redirects=False)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    assert "next=" in response.headers["Location"]


def test_unknown_url_returns_404_page(client):
    """The factory registers no custom error handler, so Flask's default is served."""
    response = client.get("/no-such-page-anywhere")

    assert response.status_code == 404
    assert b"404 Not Found" in response.data


def test_seed_dev_data_command_is_gated_by_env_flag(app_with_db, monkeypatch):
    """``flask seed-dev-data`` refuses to run unless SEED_DEV_DATA is 'true'.

    The seeder creates an administrator called ``markus`` with password ``1``, so
    the guard is load-bearing for anyone pointing the app at a real database.
    """
    monkeypatch.setenv("SEED_DEV_DATA", "false")

    result = app_with_db.test_cli_runner().invoke(args=["seed-dev-data", "2"])

    assert (
        "SEED_DEV_DATA environment variable not set to 'true'. Skipping dev data seeding."
        in result.output
    )
    with app_with_db.app_context():
        assert User.query.count() == 0


def test_seed_dev_data_skips_a_non_empty_database(app_with_db, monkeypatch):
    """Even with the flag on, an existing account stops the dev seeder."""
    monkeypatch.setenv("SEED_DEV_DATA", "true")

    with app_with_db.app_context():
        existing = User(username="resident", email="resident@example.com")
        existing.set_password("password")
        db.session.add(existing)
        db.session.commit()

    result = app_with_db.test_cli_runner().invoke(args=["seed-dev-data", "2"])

    assert (
        "Database already contains users. Skipping dev data seeding." in result.output
    )
    with app_with_db.app_context():
        assert User.query.count() == 1
        assert User.query.filter_by(username="markus").first() is None
