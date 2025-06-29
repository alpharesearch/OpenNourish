# tests/test_database_import.py

import pytest
import subprocess
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'opennourish.db')
IMPORT_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'import_usda_data.py')

@pytest.fixture(scope="module")
def real_database():
    """
    A pytest fixture that runs the real import script.
    It ensures a clean database state before the test run.
    """

    # Setup: Run the actual import script
    print(f"Running import script: {IMPORT_SCRIPT_PATH} with db: {DB_PATH}...")
    result = subprocess.run(
        ["python", IMPORT_SCRIPT_PATH, str(DB_PATH)],
        capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, f"Import script failed with error: {result.stderr}"
    assert os.path.exists(DB_PATH), "Database file was not created by the import script."
    print("Import script finished successfully.")

    yield DB_PATH # Pass the path to the test

    # Teardown: Do not remove the database, as requested by the user

@pytest.mark.integration
def test_full_usda_data_import(real_database):
    """
    Performs spot checks on the real, imported database.
    """
    db_path = real_database # Get the database path from the fixture
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT description FROM foods WHERE description = ?", ('Butter, salted',))
        food_result = cursor.fetchone()
        assert food_result is not None

