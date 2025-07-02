# OpenNourish Project Guidelines for Gemini

This file provides context and guidelines for the Gemini CLI agent when working on the OpenNourish project.

## 1. Project Overview
OpenNourish is a lightweight, open-source web application for personal nutrition tracking. Its core purpose is to allow users to log their daily food intake and create custom cooking recipes using a comprehensive nutritional database. The application is built upon the USDA FoodData Central dataset.

## 2. Key Technologies
- **Language:** Python
- **Web Framework:** Flask
- **Database:** SQLite (`opennourish.db`)
- **Database ORM:** Flask-SQLAlchemy
- **Templating:** Jinja2
- **Data Source:** USDA FoodData Central (CSV files)
- **Environment Management:** Conda (preferred)

## 3. Development Setup
To set up the development environment:
1.  Create and activate the Conda environment: `conda create --name opennourish python=3.9 && conda activate opennourish`
2.  Install Python dependencies: `pip install -r requirements.txt`
3.  Place the downloaded USDA CSV files into a directory named `usda_data/` in the project root.
4.  Generate the SQLite database from the CSV files: `python import_usda_data.py`

## 4. Running the Application
To run the Flask development server:
`flask run`

## 5. Database Management
- **Primary Database Files:** `user_data.db` (for user-specific data) and `usda_data.db` (for USDA FoodData Central). These should not be committed to version control.
- **Initial Schema Definition:** The database schema is defined in `schema_usda.sql` and `schema_user.sql`. These files are used by the import script to create the initial tables.
- **Data Import:** The `import_usda_data.py` script is responsible for creating and populating `usda_data.db` from scratch. It should be run once during setup.
- **Application Models:** Flask-SQLAlchemy models that map to the database tables are defined in `models.py`.
- **Database Migrations (Alembic):**
  - To generate a new migration script after changing models: `FLASK_APP=app.py alembic revision --autogenerate -m "Your message here"`
  - To apply pending migrations to the database: `FLASK_APP=app.py alembic upgrade head`
  - If you need to stamp the database with a specific revision without running migrations (e.g., after manual schema changes): `FLASK_APP=app.py alembic stamp <revision_id_or_head>`

## 6. Code Style and Conventions
- Follow **PEP 8** for all Python code.
- **Project Structure:** Use Flask Blueprints to organize routes into logical modules (e.g., `auth`, `tracking`, `recipes`) as the application grows.
- **Configuration:** Store application configuration (like `SECRET_KEY`) in a separate `config.py` file.
- **Templates:** All Jinja2 templates should be stored in the `templates/` directory.
- **Static Files:** CSS, JavaScript, and images should be stored in the `static/` directory.
- **Comments:** Add clear, concise comments to explain complex logic, especially in database queries and business logic.

## 7. Testing
- **Framework:** Testing is done using the **pytest** framework.
- **Test Directory:** All tests are located in the `tests/` directory.
- **Running Tests:**
  - To run all tests, including slow integration tests, use: `pytest`
  - To run only the fast unit tests and exclude the full database import test, use: `pytest -m "not integration"`
- **Database Safety:**
  - Standard tests (`pytest -m "not integration"`) are designed to **never** touch the real `user_data.db` or `usda_data.db` files. They use a temporary, in-memory database to ensure data integrity.
  - The `integration` test (`test_database_import.py`) performs a full, time-consuming import of the USDA data into a temporary database. It is crucial for verifying the data import process but should be run intentionally.
- **Test Creation:** When generating new tests, create separate files for models, routes, and utilities (e.g., `test_models.py`, `test_routes.py`). Ensure that any test involving the database uses the `client` fixture to maintain isolation from the real databases.
