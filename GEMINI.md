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
6.  **Seed the USDA portions into the user database:** `flask seed-usda-portions`

## 4. Running the Application
- **For Development:** `flask run`
- **For Production (using Waitress):** `python serve.py`

## 5. Database Management
- **Primary Database Files:** `user_data.db` (for all dynamic, user-specific data) and `usda_data.db` (for the static USDA FoodData Central). These files should never be committed to version control.
- **Static DB Creation:** `usda_data.db` is created and managed exclusively by the `import_usda_data.py` script. It contains read-only data.
- **User DB Schema Migrations:** All changes to the user database schema (i.e., modifying `models.py` for tables without a `__bind_key__`) MUST be managed using **Flask-Migrate (Alembic)**.
  - To generate a new migration after changing a model: `flask db migrate -m "A short message"`
  - To apply the migration to the database: `flask db upgrade`

### 5.1. The Unified Portion System
To avoid code duplication, the application uses a **single, unified model (`UnifiedPortion`)** for all portion types, which resides in the primary `user_data.db`.
- **Linking:** This model uses three nullable foreign key columns (`fdc_id`, `my_food_id`, `recipe_id`) to associate a portion with its parent (a USDA Food, a MyFood, or a Recipe).
- **Data Seeding:** The static USDA portions are seeded into this table using the `flask seed-usda-portions` command. All user-created portions (for MyFoods and Recipes) are added directly by the application logic.
- **Directive:** Any new feature that requires portion data **must** use and interact with this single, centralized model.

## 6. Code Style and Project Structure
- **Python:** Follow **PEP 8** for all Python code.
- **Application Factory:** The project uses the application factory pattern (`create_app` function). Blueprints are registered within this factory.
- **Blueprints:** All features are organized into Flask Blueprints within the `opennourish/` directory (e.g., `opennourish/auth`, `opennourish/tracking`).
- **Configuration:** Store application configuration (like `SECRET_KEY`) in a `config.py` file.
- **Templates & Static Files:** Templates are in `templates/`, and static files (CSS, JS) are in `static/`.

## 7. Design Directives & UI Conventions
To maintain a consistent and professional look and feel, all generated HTML templates should adhere to these Bootstrap 5 conventions.
- **Primary Actions (Submit, Save, Create):** Buttons for primary actions should always use the main theme color.
  - **Class:** `btn btn-primary`
- **Secondary Actions (Cancel, Go Back):** Buttons for secondary or less important actions.
  - **Class:** `btn btn-secondary`
- **Destructive Actions (Delete, Remove):** Buttons that trigger a deletion or other irreversible action must be clearly marked in red.
  - **Class:** `btn btn-danger`
- **Flash Messages:** User feedback and notifications must be handled using Flask's flashing system with categories (`'success'`, `'danger'`, `'warning'`, `'info'`). All flashed messages should be rendered in `base.html` using the standard Bootstrap Alert component structure.

## 6. Code Style and Project Structure
- **Python:** Follow **PEP 8** for all Python code.
- **Application Factory:** The project uses the application factory pattern (`create_app` function). Blueprints are registered within this factory.
- **Blueprints:** All features are organized into Flask Blueprints within the `opennourish/` directory (e.g., `opennourish/auth`, `opennourish/tracking`).
- **Configuration:** Store application configuration (like `SECRET_KEY`) in a `config.py` file.
- **Templates & Static Files:** Templates are in `templates/`, and static files (CSS, JS) are in `static/`.

## 7. Design Directives & UI Conventions
To maintain a consistent and professional look and feel, all generated HTML templates should adhere to these Bootstrap 5 conventions and outline variants button styles for consistency across the the application. 
- **Primary Actions (Submit, Create, Add, Edit):** Buttons for these primary actions should always use the main theme color.
  - **Class:** `btn btn-outline-primary`
- **Save Actions:** Buttons specifically for saving data.
  - **Class:** `btn btn-outline-success`
- **Secondary Actions (Cancel, Go Back):** Buttons for secondary or less important actions.
  - **Class:** `btn btn-outline-secondary`
- **Destructive Actions (Delete, Remove):** Buttons that trigger a deletion or other irreversible action must be clearly marked in red. Confirmation pop-ups (e.g., JavaScript `confirm()`) should NOT be used for these actions, as an undo system will be implemented.
  - **Class:** `btn btn-outline-danger`
- **Success Feedback:** Use green for success alerts and messages (e.g., after a form is saved).
  - **Class:** `alert alert-success`
- **Flash Messages:** User feedback and notifications must be handled using Flask's flashing system.
  - **Logic:** In the Python routes, always provide a category when calling the `flash()` function (e.g., `flash('Message here', 'success')`). The standard categories should be:
    - `'success'` for positive actions (e.g., item saved).
    - `'danger'` for errors or failed actions (e.g., form validation failed).
    - `'warning'` for non-critical alerts.
    - `'info'` for neutral information.
  - **Template:** All flashed messages should be rendered in the `base.html` template, typically right after the navbar and before the main content block. This ensures they appear consistently on every page. The rendering logic must loop through the messages and use the message's category to apply the corresponding Bootstrap alert class.
- **Informational Links/Buttons:** Use `btn btn-outline-info` for non-critical actions like "View Details". Use `btn btn-outline-primary` for "Edit" actions that lead to a primary editing page.
  - **Class:** `btn btn-outline-info` or `btn btn-outline-primary`
- **Forms:** All forms should be rendered cleanly. Each form field should have a proper `<label>` and be wrapped in a `div class="mb-3"` for correct spacing. Validation errors should be displayed prominently.
  - **Separate Forms for Actions:** For clarity and to prevent unintended side effects, each distinct action (e.g., saving data, deleting a record) should be handled by its own `<form>` element. Do not nest forms or use a single form for multiple, unrelated actions. This ensures that submitting one action does not inadvertently trigger another, and simplifies backend processing.
- **Tables:** All tables should use Bootstrap's `table-striped` class for improved readability.
  - **Class:** `table table-striped`
- **Charts:** All charts should be generated using Chart.js. They should be responsive and include clear labels and titles.

---
### 7.1. Unified Search and Add System

**Directive:** To prevent code duplication and ensure a consistent user experience, the project uses a single, unified system for all "search and add food" operations. Any new feature or modification requiring the user to search for an item (from USDA, My Foods, Recipes, or Meals) and add it to a destination (like the daily diary, a recipe, or a meal) **MUST** integrate with this system. **Do not create new, separate search routes or templates.**

**How It Works:**

*   The entire system is managed by the `search` blueprint.
*   The user is always directed to a single search page, rendered by the `search.index` route.
*   This route is made context-aware via URL parameters. The `target` parameter tells the system *where* the food will be added (e.g., `'diary'`, `'recipe'`, `'meal'`). Other parameters provide necessary IDs or data (e.g., `log_date`, `recipe_id`, `meal_id`).
*   A single `search.add_item` endpoint handles the logic for adding the selected item to the correct destination based on the context provided.

### 7.2. URL Structure for Resource Actions

**Directive:** To maintain a clear, hierarchical, and RESTful routing structure, all URLs that perform an action on a specific instance of a resource (e.g., editing a specific recipe, deleting a specific food) **MUST** follow the pattern: `/{resource_collection}/{id}/{action}`. The unique ID of the resource must come before the action verb.

**Reasoning:** This structure clearly identifies the resource first (`/myfoods/11`) and then specifies the action being performed on it (`/edit`). This improves readability and organization.

**Standard Actions:**

*   **Render Edit Form (GET):** `.../{id}/edit`
*   **Process Edit Form (POST):** `.../{id}/edit`
*   **Process Deletion (POST):** `.../{id}/delete`

**Note on Collections:** This directive applies to actions on *specific items*. Routes that act on the entire collection (like rendering a list or creating a new item) should not include an ID.
*   **List all items (GET):** `/recipes/`
*   **Render New Item Form (GET):** `/recipes/new`
*   **Process New Item Form (POST):** `/recipes/new`


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

### 8.1. Cross-Database Queries
- **Challenge:** A common challenge in this project is querying relationships between the user database (`user_data.db`) and the static USDA database (`usda_data.db`). Standard SQLAlchemy eager loading strategies like `joinedload` or `selectinload` can fail, as they may attempt to join tables across different database files, resulting in `sqlite3.OperationalError: no such table`.
- **Solution:** To handle these cross-database relationships, you must use a manual, two-step query process. First, query the primary database (usually the user database) to retrieve the main objects. Then, extract the foreign keys from the results and perform a second, separate query against the second database (usually the USDA database) to fetch the related objects. Finally, manually attach the related objects to the main objects in your Python code. This approach ensures that each query is sent to the correct database, avoiding the "no such table" error.

## 9. Debugging with the Flask Logger
To maintain a clean and professional codebase, **do not use `print()` statements for debugging.** Instead, use Flask's built-in logger, which is automatically configured to show messages only when the application is in debug mode.

### 9.1. Why Use the Logger?
-   **Automatic Toggling:** Log messages with the level `DEBUG` will only appear in your console when `FLASK_DEBUG=1` or `app.run(debug=True)` is active. They are automatically silenced in a production environment.
-   **Contextual Information:** The logger provides valuable context, including a timestamp, the log level, and the module where the message originated.
-   **Configurable and Standard:** It's the standard, production-ready way to handle application messages and can be configured to write to files or other services.

### 9.2. How to Add a Debug Message
1.  **Import `current_app`** from Flask in the route file you are working on.
    ```python
    from flask import current_app
    ```
2.  **Call the logger** at the point in your code you want to inspect. Use an f-string to easily include variables.
    ```python
    current_app.logger.debug(f"This is a debug message. The value is: {my_variable}")
    ```

### 9.3. Other Log Levels
You can also use other log levels for different situations:
-   `current_app.logger.info("A standard informational message.")`
-   `current_app.logger.warning("Something unexpected happened, but the app continues.")`
-   `current_app.logger.error("A serious error occurred.")`
