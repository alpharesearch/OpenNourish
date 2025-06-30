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
- **Primary Database File:** `opennourish.db` is the main application database. It should not be committed to version control.
- **Initial Schema Definition:** The database schema is defined in `schema_usda.sql`. This file is used by the import script to create the tables.
- **Data Import:** The `import_usda_data.py` script is responsible for creating and populating the `opennourish.db` from scratch. It should be run once during setup.
- **Application Models:** Flask-SQLAlchemy models that map to the database tables are defined in `models.py`.

## 6. Code Style and Conventions
- Follow **PEP 8** for all Python code.
- **Project Structure:** Use Flask Blueprints to organize routes into logical modules (e.g., `auth`, `tracking`, `recipes`) as the application grows.
- **Configuration:** Store application configuration (like `SECRET_KEY`) in a separate `config.py` file.
- **Templates:** All Jinja2 templates should be stored in the `templates/` directory.
- **Static Files:** CSS, JavaScript, and images should be stored in the `static/` directory.
- **Comments:** Add clear, concise comments to explain complex logic, especially in database queries and business logic.

## 7. Testing
- Testing will be done using the **pytest** framework.
- Tests should be placed in a `tests/` directory.
- To run tests, use the command: `pytest`
- When generating tests, create separate files for models, routes, and utilities (e.g., `test_models.py`, `test_routes.py`).
