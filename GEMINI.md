# OpenNourish Project Guidelines for Gemini

This file provides context and guidelines for the Gemini CLI agent when working on the OpenNourish project.

## 1. Project Overview
OpenNourish is a lightweight, open-source web application for personal nutrition tracking. Its core purpose is to allow users to log their daily food intake, create custom recipes, and track their progress against personal goals. The application uses a static USDA nutritional database and a dynamic user database.

## 2. Key Technologies
- **Containerization:** Docker, Docker Compose
- **Language:** Python
- **Web Framework:** Flask
- **Database:** SQLite (two separate files)
- **Database ORM:** Flask-SQLAlchemy
- **Database Migrations:** Flask-Migrate (using Alembic)
- **Forms:** Flask-WTF
- **Authentication:** Flask-Login
- **Frontend:** Jinja2, Bootstrap 5, Chart.js
- **Environment Management:** Conda (preferred)

## 3. Development Setup
To set up the development environment:
1.  Create and activate the Conda environment: `conda create --name opennourish python=3.9 && conda activate opennourish`
2.  Install Python dependencies: `pip install -r requirements.txt`
3.  Place the downloaded USDA CSV files into a directory named `usda_data/` in the project root.
4.  Generate the static USDA database: `python import_usda_data.py`
5.  Initialize and migrate the user database: `flask db init` (first time only), then `flask db upgrade`

Alternatively, use Docker for development:
1.  Ensure Docker and Docker Compose (v2.x) are installed.
2.  Follow the "Initial Database Setup" steps in `README.md` to prepare `user_data.db` and `usda_data.db` on your host.
3.  Build the Docker image: `docker compose build`
4.  Run the application: `docker compose up -d`
5.  Access at `http://localhost:8081`.

## 4. Running the Application
To run the Flask development server:
1. Set the FLASK_APP environment variable: `export FLASK_APP=app.py` (Linux/macOS) or `$env:FLASK_APP="app.py"` (PowerShell)
2. Run the Flask application: `flask run`

## 5. Database Management
- **Primary Database Files:** `user_data.db` (for all dynamic, user-specific data) and `usda_data.db` (for the static USDA FoodData Central). These files should never be committed to version control.
- **Static DB Creation:** `usda_data.db` is created and managed exclusively by the `import_usda_data.py` script.
- **User DB Schema Migrations:** All changes to the user database schema (i.e., modifying `models.py` for tables without a `__bind_key__`) MUST be managed using **Flask-Migrate (Alembic)**.
  - To generate a new migration after changing a model: `flask db migrate -m "A short message describing the change"`
  - To apply the migration to the database: `flask db upgrade`

### 8.1. Cross-Database Queries
- **Challenge:** A common challenge in this project is querying relationships between the user database (`user_data.db`) and the static USDA database (`usda_data.db`). Standard SQLAlchemy eager loading strategies like `joinedload` or `selectinload` can fail, as they may attempt to join tables across different database files, resulting in `sqlite3.OperationalError: no such table`.
- **Solution:** To handle these cross-database relationships, you must use a manual, two-step query process. First, query the primary database (usually the user database) to retrieve the main objects. Then, extract the foreign keys from the results and perform a second, separate query against the second database (usually the USDA database) to fetch the related objects. Finally, manually attach the related objects to the main objects in your Python code. This approach ensures that each query is sent to the correct database, avoiding the "no such table" error.

## 6. Code Style and Project Structure
- **Python:** Follow **PEP 8** for all Python code.
- **Application Factory:** The project uses the application factory pattern (`create_app` function). Blueprints are registered within this factory.
- **Blueprints:** All features are organized into Flask Blueprints within the `opennourish/` directory (e.g., `opennourish/auth`, `opennourish/tracking`).
- **Configuration:** Store application configuration (like `SECRET_KEY`) in a `config.py` file.
- **Templates & Static Files:** Templates are in `templates/`, and static files (CSS, JS) are in `static/`.

## 7. Design Directives & UI Conventions
To maintain a consistent and professional look and feel, all generated HTML templates should adhere to these Bootstrap 5 conventions.
- **Primary Actions (Submit, Save, Create, Add):** Buttons for primary actions should always use the main theme color.
  - **Class:** `btn btn-outline-primary`  `btn-outline-success`
- **Secondary Actions (Cancel, Go Back):** Buttons for secondary or less important actions.
  - **Class:** `btn btn-outline-secondary`
- **Destructive Actions (Delete, Remove):** Buttons that trigger a deletion or other irreversible action must be clearly marked in red. Confirmation pop-ups (e.g., JavaScript `confirm()`) should NOT be used for these actions, as an undo system will be implemented.
  - **Class:** `btn btn-outline-danger`
- **Other Actions:** Buttons for other actions.
  - **Class:** `btn-outline-success`
- **Success Feedback:** Use green for success alerts and messages (e.g., after a form is saved).
  - **Class:** `alert alert-success`
- **Flash Messages:** User feedback and notifications must be handled using Flask's flashing system.
  - **Logic:** In the Python routes, always provide a category when calling the `flash()` function (e.g., `flash('Message here', 'success')`). The standard categories should be:
    - `'success'` for positive actions (e.g., item saved).
    - `'danger'` for errors or failed actions (e.g., form validation failed).
    - `'warning'` for non-critical alerts.
    - `'info'` for neutral information.
  - **Template:** All flashed messages should be rendered in the `base.html` template, typically right after the navbar and before the main content block. This ensures they appear consistently on every page. The rendering logic must loop through the messages and use the message's category to apply the corresponding Bootstrap alert class.
- **Informational Links/Buttons:** Use for non-critical actions like "View Details" or "Edit".
  - **Class:** `btn btn-outline-info` or `btn btn-outline-primary`
- **Forms:** All forms should be rendered cleanly. Each form field should have a proper `<label>` and be wrapped in a `div class="mb-3"` for correct spacing. Validation errors should be displayed prominently.
  - **Separate Forms for Actions:** For clarity and to prevent unintended side effects, each distinct action (e.g., saving data, deleting a record) should be handled by its own `<form>` element. Do not nest forms or use a single form for multiple, unrelated actions. This ensures that submitting one action does not inadvertently trigger another, and simplifies backend processing.
- **Tables:** All tables should use Bootstrap's `table-striped` class for improved readability.
  - **Class:** `table table-striped`
- **Charts:** All charts should be generated using Chart.js. They should be responsive and include clear labels and titles.

## 8. Testing
- **Framework:** Testing is done using the **pytest** framework.
- **Test Directory:** All tests are located in the `tests/` directory.
- **Running Tests:**
- - To run only the fast application tests: `pytest -m "not integration"` (use this!)
  - To run all tests: `pytest` (very slow!)
- **Database Safety:**
  - Standard application tests (`not integration`) **must** use an in-memory SQLite database to ensure they are fast and do not touch the real database files.
  - The `integration` test verifies the full USDA data import process. It is slow and should be run intentionally.
- **Test Creation:** When generating new application tests, ensure they use a fixture that configures the app for testing and provides a test client.