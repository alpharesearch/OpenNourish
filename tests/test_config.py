import pytest
import importlib.util
from config import get_or_create_secret_key, get_setting_from_db
from models import db, SystemSetting
from opennourish.utils import encrypt_value
from cryptography.fernet import Fernet

# --- Tests for get_or_create_secret_key ---


def test_get_or_create_secret_key_from_env(monkeypatch, tmp_path):
    """
    Tests that the secret key is correctly read from an environment variable,
    ignoring any file that might exist.
    """
    secret_from_env = "supersecretfromenv"
    monkeypatch.setenv("SECRET_KEY", secret_from_env)

    # Create a dummy file to ensure the environment variable takes precedence
    key_file = tmp_path / "secret_key.txt"
    key_file.write_text("secretfromfile")

    key = get_or_create_secret_key(tmp_path)
    assert key == secret_from_env


def test_get_or_create_secret_key_from_file(monkeypatch, tmp_path):
    """
    Tests that the secret key is correctly read from a file when no
    environment variable is set.
    """
    # Ensure env var is not set
    monkeypatch.delenv("SECRET_KEY", raising=False)

    secret_from_file = "supersecretfromfile"
    key_file = tmp_path / "secret_key.txt"
    key_file.write_text(secret_from_file)

    key = get_or_create_secret_key(tmp_path)
    assert key == secret_from_file


def test_get_or_create_secret_key_generates_new(monkeypatch, tmp_path):
    """
    Tests that a new secret key is generated and saved if neither an
    environment variable nor a file exists.
    """
    # Ensure env var is not set
    monkeypatch.delenv("SECRET_KEY", raising=False)

    key_file = tmp_path / "secret_key.txt"
    assert not key_file.exists()

    key = get_or_create_secret_key(tmp_path)
    assert key is not None
    assert len(key) == 48  # 24 bytes hex-encoded
    assert key_file.exists()
    assert key_file.read_text() == key


# --- Tests for get_setting_from_db ---


def test_get_setting_from_db_decrypted(app_with_db, monkeypatch):
    """
    Tests that a setting can be correctly decrypted from the database.
    """
    # Generate a valid Fernet key for the test
    encryption_key = Fernet.generate_key()
    monkeypatch.setenv("ENCRYPTION_KEY", encryption_key.decode())

    original_value = "my_secret_password"
    encrypted_value = encrypt_value(original_value, encryption_key)

    with app_with_db.app_context():
        setting = SystemSetting(key="MAIL_PASSWORD", value=encrypted_value)
        db.session.add(setting)
        db.session.commit()

        decrypted_value = get_setting_from_db(
            app_with_db, "MAIL_PASSWORD", decrypt=True
        )
        assert decrypted_value == original_value


def test_get_setting_from_db_decryption_error(app_with_db, monkeypatch):
    """
    Tests that a decryption error is handled gracefully and returns the default value.
    """
    # Use a valid key to encrypt, but then try to decrypt with a different key
    good_key = Fernet.generate_key()
    bad_key = Fernet.generate_key()

    encrypted_value = encrypt_value("some_value", good_key)

    # Set the environment to use the "bad" key for decryption
    monkeypatch.setenv("ENCRYPTION_KEY", bad_key.decode())

    with app_with_db.app_context():
        setting = SystemSetting(key="MAIL_PASSWORD", value=encrypted_value)
        db.session.add(setting)
        db.session.commit()

        # It should return the default value (in this case, 'fallback') on error
        decrypted_value = get_setting_from_db(
            app_with_db, "MAIL_PASSWORD", decrypt=True, default="fallback"
        )
        assert decrypted_value == "fallback"


# --- Tests for Config class initialization ---


def run_config_test(tmp_path, monkeypatch, secret_key_val, enc_key_val):
    """Helper function to dynamically load a modified config."""

    # Create a temporary config file with controlled values
    config_content = f"""
import os
class Config:
    SECRET_KEY = {secret_key_val!r}
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application.")
    ENCRYPTION_KEY = {enc_key_val!r}
    if not ENCRYPTION_KEY:
        raise ValueError("No ENCRYPTION_KEY set for Flask application.")
"""
    config_path = tmp_path / "temp_config.py"
    config_path.write_text(config_content)

    # Dynamically import the temporary config file
    spec = importlib.util.spec_from_file_location("temp_config", config_path)
    temp_config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(temp_config_module)
    return temp_config_module.Config


def test_config_raises_error_if_no_secret_key(tmp_path, monkeypatch):
    """
    Tests that the Config class raises a ValueError if no SECRET_KEY can be found.
    """
    with pytest.raises(ValueError, match="No SECRET_KEY set"):
        run_config_test(
            tmp_path, monkeypatch, secret_key_val=None, enc_key_val="some_key"
        )


def test_config_raises_error_if_no_encryption_key(tmp_path, monkeypatch):
    """
    Tests that the Config class raises a ValueError if ENCRYPTION_KEY is not set.
    """
    with pytest.raises(ValueError, match="No ENCRYPTION_KEY set"):
        run_config_test(
            tmp_path, monkeypatch, secret_key_val="some_key", enc_key_val=None
        )


def test_config_loads_successfully(tmp_path, monkeypatch):
    """
    Tests that the Config class loads without error when both keys are present.
    """
    try:
        run_config_test(
            tmp_path,
            monkeypatch,
            secret_key_val="some_key",
            enc_key_val="some_other_key",
        )
    except ValueError:
        pytest.fail("Config class raised ValueError unexpectedly.")
