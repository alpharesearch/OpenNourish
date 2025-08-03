# tests/test_database_import.py

import pytest
import subprocess
import os
import sqlite3

IMPORT_SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "import_usda_data.py"
)


@pytest.fixture(scope="module")
def real_database(tmp_path_factory):
    """
    A pytest fixture that runs the real import script into a temporary database.
    """
    # Create a temporary directory for the database
    db_dir = tmp_path_factory.mktemp("test_db")
    db_path = db_dir / "opennourish.db"

    # Setup: Run the actual import script, passing the temporary db path
    print(f"Running import script: {IMPORT_SCRIPT_PATH} with db: {db_path}...")
    result = subprocess.run(
        ["python", IMPORT_SCRIPT_PATH, "--db_file", str(db_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"Import script failed with error: {result.stderr}"
    assert db_path.exists(), "Database file was not created by the import script."
    print("Import script finished successfully.")

    yield db_path  # Pass the path to the test

    # Teardown: tmp_path_factory handles cleanup automatically


@pytest.mark.integration
def test_full_usda_data_import(real_database):
    """
    Performs spot checks on the real, imported database.
    """
    db_path = real_database  # Get the temporary database path from the fixture
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT description FROM foods WHERE description = ?", ("Butter, Salted",)
        )
        food_result = cursor.fetchone()
        assert food_result is not None
