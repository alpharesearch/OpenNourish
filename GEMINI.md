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

### 6.1. Linting and Formatting
To ensure code quality and consistency, this project uses **Ruff** for both linting and formatting.
- **To check for linting errors:** `ruff check .`
- **To automatically format the code:** `ruff format .`

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
  - **Standardized Input Field Widths:** To ensure a consistent and clean layout in forms, especially where multiple inputs appear on a single line, specific input fields should have a standardized width. These are defined in `static/style.css`.
      - **Amount/Quantity Fields:** All numeric input fields for amounts or quantities should have a width of `60px`.
      - **CSS Selector:** `input[name="amount"], input[name="quantity"]`
    - **Portion Select Dropdowns:** All dropdowns for selecting a portion or serving size should have a width of `80px`. The dropdown will expand to show the full text when opened.
      - **CSS Selector:** `select[name="portion_id"]`
  - **Separate Forms for Actions:** For clarity and to prevent unintended side effects, each distinct action (e.g., saving data, deleting a record) should be handled by its own `<form>` element. Do not nest forms or use a single form for multiple, unrelated actions. This ensures that submitting one action does not inadvertently trigger another, and simplifies backend processing.
- **Tables:** All tables should use Bootstrap's `table-striped` class for improved readability.
  - **Class:** `table table-striped`
- **Charts:** All charts should be generated using Chart.js. They should be responsive and include clear labels and titles.

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

### 7.3. Standard Page and Card Layout
To ensure a consistent and semantically correct structure across all pages, new and updated templates should follow this standard layout. This structure separates the main page title from content cards and uses flexbox to align titles and action buttons.

**Standard Layout Example:**
```html
<div class="container mt-4">
    <!-- 1. PAGE HEADER: Main title and primary actions for the entire page -->
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1 class="mb-0">Page Title</h1>
        <div>
            <a href="..." class="btn btn-outline-primary">Primary Page Action (e.g., <i class="bi bi-plus-circle"></i> Add New)</a>
            <a href="..." class="btn btn-outline-secondary"><i class="bi bi-arrow-return-left"></i> Back to List</a>
        </div>
    </div>

    <!-- 2. STANDARD CONTENT CARD: For displaying information or forms -->
    <div class="card mb-4">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h2 class="h5 mb-0">Card Title</h2>
            <!-- Card-specific action buttons -->
            <div>
                <a href="..." class="btn btn-sm btn-outline-primary">Edit</a>
                <form action="..." method="POST" class="d-inline">
                    <button type="submit" class="btn btn-sm btn-outline-danger"><i class="bi bi-x-circle"></i></button>
                </form>
            </div>
        </div>
        <div class="card-body">
            <p>Card content, such as text, forms, or tables, goes here.</p>
            
            <!-- 3. ELEMENT-SPECIFIC ACTIONS: Buttons associated with a single input field -->
            <div class="input-group mt-3">
                <input type="text" class="form-control" placeholder="UPC Code">
                <button class="btn btn-outline-secondary" type="button">Scan UPC</button>
            </div>
        </div>
    </div>
</div>
```

**Key Principles and Improvements:**

1.  **Page Header:** A dedicated header for the page's `<h1>` title improves structure and provides a consistent location for primary, page-level actions (e.g., "Add New Recipe", "Back to List").
2.  **Card Header:** The `.card-header` is used for the title of a content block and any actions that apply to the entire card (e.g., "Edit", "Delete").
3.  **Element-Specific Actions:** Buttons that perform an action on a single input field (e.g., "Scan UPC", "Generate") should be placed directly next to that element, often using Bootstrap's `.input-group`.
4.  **Flexbox for Alignment:** Using `d-flex justify-content-between align-items-center` in both page and card headers provides a robust way to align titles to the left and action buttons to the right.
5.  **Semantic & Visual Headings:** Card titles should use a semantic `<h2>` tag but can be visually styled smaller with the `.h5` class for a balanced appearance. The `mb-0` class removes unwanted bottom margin.
6.  **Button Sizing:** Card-specific action buttons should be sized down with `btn-sm` to fit cleanly within the card header. Page-level buttons can remain the standard size.
7.  **Consistent Spacing:** Using `mt-4` on the main container and `mb-4` on headers and cards ensures predictable vertical spacing throughout the application.
8.  **Responsive Design:** All layouts and components must be responsive. Use Bootstrap's grid system (`row`, `col-*`), flexbox utilities (`d-flex`, `flex-wrap`), and responsive display/spacing classes to ensure the UI is usable and looks good on all screen sizes, from small mobile phones to large desktop monitors. For example, button groups in headers should use `flex-wrap` to stack vertically on small screens.

### 7.4. Frontend Display Conventions

#### Formatting Numbers to Two Decimal Places
To ensure that all floating-point numbers (e.g., nutritional values, weights) are displayed consistently with two decimal places, use the Jinja2 `format` filter directly within the template.

-   **Directive:** When rendering a floating-point number in an HTML input field or as text, apply the `%.2f` format specifier.
-   **Example:**
    ```jinja
    {{ form.calories_per_100g(class="form-control", value="%.2f"|format(my_food.calories_per_100g)) }}
    ```
-   **Note:** This approach is suitable for display purposes. For data integrity, server-side validation and rounding should still be implemented in the relevant form or route logic to ensure the data is stored correctly, regardless of the frontend presentation.

### 7.5. Icon Usage Conventions
To ensure a consistent and intuitive user interface, all icons should be used purposefully and adhere to the following guidelines. The project uses [Bootstrap Icons](https://icons.getbootstrap.com/), which are now locally hosted.

- **General Principle:** Whenever possible, icons should be paired with text labels for clarity (e.g., `<i class="bi bi-plus-circle"></i> Create New`). For compact spaces, such as in table rows, icon-only buttons are acceptable if the context makes their function clear.

- **Primary Actions (Create, Add New):**
  - **Icon:** `bi-plus-circle`
  - **Usage:** For buttons that initiate the creation of a new item, like "Create New Recipe" or "Add New Food".

- **Confirmation Actions (Save, Update):**
  - **Icon:** `bi-check2-circle`
  - **Usage:** For buttons that save or confirm changes, such as the small "Save" button next to an ingredient in a recipe.

- **Destructive Actions (Delete, Remove):**
  - **Icon:** `bi-x-circle`
  - **Usage:** For buttons that delete an item. This provides a clear visual cue for a destructive action.

- **Edit Actions:**
  - **Icon:** `bi-pencil-square`
  - **Usage:** For buttons that take the user to an edit page or enable editing functionality.

- **View/Details Actions:**
  - **Icon:** `bi-info-circle`
  - **Usage:** For buttons that link to a detailed view of an item, like "View Recipe".

- **Search Actions:**
  - **Icon:** `bi-search`
  - **Usage:** For search submission buttons.

- **Clone/Copy Actions:**
  - **Icon:** `bi-clipboard`
  - **Usage:** For buttons that clone or copy an existing item, like "Clone Recipe".

- **Move Actions:**
  - **Icon:** `bi-arrows-move`
  - **Usage:** For buttons that move an item from one location to another, such as moving a diary entry to a different date or meal.

- **PDF/Print Actions:**
  - **Icon:** `bi-file-earmark-pdf`
  - **Usage:** For buttons that generate a PDF.

## 8. Testing
- **Framework:** Testing is done using the **pytest** framework.
- **Test Directory:** All tests are located in the `tests/` directory.
- **Running Tests:**
- - To run only the fast application tests: `pytest -m "not integration"` (use this!)
  - To run all tests: `pytest` (very slow!)
- - To run a single test with verbose output (useful for debugging): `pytest <path_to_test_file>::<test_function_name> -vvv`
- **Database Safety:**
  - Standard application tests (`not integration`) **must** use an in-memory SQLite database to ensure they are fast and do not touch the real database files.
  - The `integration` test verifies the full USDA data import process. It is slow and should be run intentionally.
- **Test Creation:** When generating new application tests, ensure they use a fixture that configures the app for testing and provides a test client.
- **HTML Encoding in Assertions:** When asserting against HTML content in test responses, be mindful of HTML encoding. Characters like single quotes (`'`) are often encoded as `&#39;`. Therefore, assertions should check for the HTML-encoded version of the string (e.g., `assert b"Friend&#39;s Meal"` instead of `assert b"Friend's Meal"`).

### 8.1. Permanent Test Suite
**Directive:** Do not delete or disable tests. The test suite must be maintained and expanded to cover all new and existing functionality. If a test is temporarily failing due to a known issue that cannot be immediately resolved, it may be marked with `pytest.mark.xfail` and a clear explanation, but it must not be removed.

### 8.2. Cross-Database Queries
- **Challenge:** A common challenge in this project is querying relationships between the user database (`user_data.db`) and the static USDA database (`usda_data.db`). Standard SQLAlchemy eager loading strategies like `joinedload` or `selectinload` can fail, as they may attempt to join tables across different database files, resulting in `sqlite3.OperationalError: no such table`.
- **Solution:** To handle these cross-database relationships, you must use a manual, two-step query process. First, query the primary database (usually the user database) to retrieve the main objects. Then, extract the foreign keys from the results and perform a second, separate query against the second database (usually the USDA database) to fetch the related objects. Finally, manually attach the related objects to the main objects in your Python code. This approach ensures that each query is sent to the correct database, avoiding the "no such table" error.

### 8.3. Testing Flash Messages
- **Challenge:** When testing routes that flash a message and then immediately redirect, the flashed message is consumed by the redirected request. Asserting the message content in the final response body after setting `follow_redirects=True` will fail because the message has already been displayed and removed from the session.
- **Solution:** To reliably test flash messages, you must check the session *before* following the redirect.
  1. Make the POST request **without** `follow_redirects=True`.
  2. Assert that the response status code is `302` (the redirect).
  3. Use a `with client.session_transaction() as session:` block to access the session context.
  4. Assert the content of the `_flashes` object within the session.
  5. Optionally, you can then follow the redirect and assert the final page's status code.
- **Example:**
  ```python
  def test_flash_message_on_redirect(client):
      # Make the request that triggers the flash and redirect
      response = client.post('/some/url', data={'key': 'value'})
      
      # Assert the redirect happened
      assert response.status_code == 302

      # Check the session for the flash message
      with client.session_transaction() as session:
          flashes = session.get('_flashes', [])
          assert len(flashes) > 0
          assert flashes[0][0] == 'success' # Category
          assert flashes[0][1] == 'Your item was created!' # Message

      # Optionally, follow the redirect
      response = client.get(response.headers['Location'])
      assert response.status_code == 200
  ```
### 8.4. Writing Effective Pytest Tests

To avoid common pitfalls and ensure tests are robust and maintainable, follow these guidelines when writing tests for OpenNourish.

-   **Fixtures and App Context:**
    -   **Problem:** A frequent error is the `DetachedInstanceError` from SQLAlchemy. This occurs when a database object (like a `User`) is created in a fixture's app context but is then accessed in a test function *outside* of that context. The object loses its connection to the database session.
    -   **Solution:**
        1.  **Return IDs from Fixtures:** Fixtures that create database objects should return the object's primary ID, not the object instance itself.
        2.  **Re-fetch Objects in Tests:** Inside the test function, use a `with client.application.app_context():` block. Within this block, use the ID from the fixture to re-fetch the object from the database (e.g., `user = db.session.get(User, user_id)`). This ensures the object is "attached" to the current session.
        3.  **Keep Assertions in Context:** Any assertions that require accessing a lazy-loaded relationship (e.g., `user.goals`) must also be performed *inside* the `with client.application.app_context():` block.

-   **Mocking with `monkeypatch`:**
    -   **Problem:** Manually replacing functions or methods for testing (e.g., `original_func = my_module.func; my_module.func = mock_func`) is brittle and can have unintended side effects across tests.
    -   **Solution:** Use the built-in `monkeypatch` fixture from pytest. It handles the setup and teardown of the mock automatically, ensuring that the original function is restored after the test completes.
    -   **Example:**
        ```python
        def test_my_function(monkeypatch):
            # Define the mock function
            def mock_returns_five(arg1, arg2):
                return 5
            
            # Apply the mock to the target function
            monkeypatch.setattr('path.to.your.module.function_to_mock', mock_returns_five)
            
            # Now, when your code calls the original function, the mock will be executed instead.
            result = call_my_function()
            assert result == 5
        ```

-   **Test Structure Example:**
    ```python
    import pytest
    from models import db, User
    from opennourish.utils import some_function_to_test

    (at symbol)pytest.fixture
    def my_fixture(auth_client):
        with auth_client.application.app_context():
            user = User.query.filter_by(username='testuser').first()
            # ... create other necessary data ...
            db.session.commit()
            return auth_client, user.id # Return the ID

    def test_my_feature(my_fixture):
        client, user_id = my_fixture # Unpack client and ID

        # Use the app context for all database operations and function calls
        with client.application.app_context():
            # Re-fetch the user to ensure it's session-bound
            user = db.session.get(User, user_id)

            # Call the function you want to test
            result = some_function_to_test(user)

            # Perform assertions
            assert result is not None
            # If you need to access lazy-loaded relationships, do it here
            assert user.goals is not None 
    ```

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