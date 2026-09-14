"""Coverage tests for the real config.py module-level guards and helpers."""

import importlib

import pytest

import config as config_module
from config import Config, get_setting_from_db
from models import db, SystemSetting


def test_get_setting_from_db_plain_value_and_default(app_with_db):
    with app_with_db.app_context():
        db.session.add(SystemSetting(key="MAIL_SERVER", value="smtp.plain.test"))
        db.session.commit()

    assert get_setting_from_db(app_with_db, "MAIL_SERVER", default="none") == (
        "smtp.plain.test"
    )
    assert get_setting_from_db(app_with_db, "MAIL_MISSING", default="fallback") == (
        "fallback"
    )


def test_allow_registration_property_reads_db(app_with_db):
    with app_with_db.app_context():
        assert Config().ALLOW_REGISTRATION is True

        db.session.add(SystemSetting(key="allow_registration", value="False"))
        db.session.commit()
        assert Config().ALLOW_REGISTRATION is False


def test_config_raises_without_encryption_key(monkeypatch):
    """Re-importing config with ENCRYPTION_KEY unset must raise ValueError."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="No ENCRYPTION_KEY"):
        importlib.reload(config_module)

    # Restore a healthy module state for any later import in the session.
    monkeypatch.undo()
    importlib.reload(config_module)
