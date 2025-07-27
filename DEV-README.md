# Developer Notes for OpenNourish

This document contains notes and procedures for developers working on the OpenNourish project.

## 1. Resetting the User Database and Migrations

There are times during development when you may need to completely reset the user database (`user_data.db`) and start fresh. This is useful when the migration history gets corrupted or you want to revert to a clean slate.

**Warning:** This process will permanently delete all data in your `user_data.db` file.

Follow these steps to reset the database and Alembic migration configuration:

1.  **Delete the Database File:**
    Remove the existing SQLite database file.
    ```bash
    rm user_data.db
    ```

2.  **Delete the Migrations Directory:**
    Remove the entire `migrations` directory. This will erase the Alembic history.
    ```bash
    rm -rf migrations
    ```

3.  **Initialize Migrations:**
    Create a new migrations repository.
    ```bash
    flask db init
    ```

4.  **Generate the Initial Migration:**
    Create a new migration script based on the current state of the models in `models.py`.
    ```bash
    flask db migrate -m "Initial migration"
    ```

5.  **Apply the Migration:**
    Apply the newly created migration to the database. This will create all the tables.
    ```bash
    flask db upgrade
    ```

After these steps, you will have a fresh `user_data.db` file and a clean migration history.

## 2. Making Non-Destructive Database Schema Changes

When you need to make changes to the database schema (e.g., adding a new table or column), you should always use a non-destructive workflow to avoid losing data. This is the standard process for evolving the database schema as the application grows.

Follow these steps to make non-destructive schema changes:

1.  **Modify Your Models:**
    Make the desired changes to your models in the `models.py` file. For example, you might add a new column to an existing model or create a new model class.

2.  **Generate a New Migration:**
    Once you have updated your models, generate a new migration script. This script will contain the necessary commands to update the database schema to match your models.
    ```bash
    flask db migrate -m "A short, descriptive message about the changes"
    ```
    Replace "A short, descriptive message about the changes" with a brief summary of your changes (e.g., "Add email column to User model").

3.  **Apply the Migration:**
    Apply the new migration to your database. This will update the database schema without deleting any existing data.
    ```bash
    flask db upgrade
    ```

By following this process, you can safely evolve your database schema as you develop the application, without worrying about losing your data.

## 3. Database Seeding for Development

To quickly populate your `user_data.db` with realistic test data for development and testing purposes, you can use the `seed-dev-data` Flask CLI command.

**Prerequisites:**

*   Ensure you have the `Faker` library installed. If not, run: `pip install Faker` (or `pip install -r requirements.txt` after adding `Faker` to it).

**Usage:**

To seed the database with a default number of users (currently 10) and their associated data:

```bash
flask seed-dev-data
```

To specify a custom number of users to create:

```bash
flask seed-dev-data --count <number_of_users>
```

Replace `<number_of_users>` with the desired count (e.g., `flask seed-dev-data --count 5`).

**What this command does:**

*   **Clears Old Data:** Deletes all existing records from user-related tables (`DailyLog`, `MyFood`, `Recipe`, `UserGoal`, `CheckIn`, `User`, etc.) to ensure a clean slate.
*   **Creates a Main Test User:** Adds a predictable user for easy login (username: `test`, password: `password`).
*   **Generates Bulk Data:** For each specified user count, it generates:
    *   A new fake `User`.
    *   A `UserGoal` with randomized values.
    *   20-30 `MyFood` items with fake descriptions and nutritional data.
    *   50-60 `CheckIn` records spanning the last two months with varying weights.
    *   2-5 `Recipe` objects.
    *   100+ `DailyLog` entries spanning different dates and meals, randomly linked to USDA foods, `MyFood` items, or `Recipe` objects.

This command is invaluable for quickly setting up a development environment with sufficient data to test pagination, data display, and other features.

### 3.1 Using the `seed_db.sh` Script

For a fully automated, non-destructive seeding process, you can use the `seed_db.sh` shell script. This script will ensure your database schema is up-to-date and then populate it with development data, preserving your existing database file and migration history.

**Usage:**

1.  Make the script executable (if you haven't already):
    ```bash
    chmod +x seed_db.sh
    ```
2.  Run the script from the project root:
    ```bash
    ./seed_db.sh
    ```

This script executes `flask db upgrade` to apply any pending migrations and then `flask seed-dev-data` to populate the database. It's a convenient way to refresh your development data without manually running multiple commands.

## For Project Maintainers: Creating the Pre-built Database

To update the static USDA data (which is used to provide a pre-populated USDA database for new deployments), the maintainer must:

1.  Run `python import_usda_data.py` locally to generate a new `usda_data.db`.
2.  Create a new Release on the project's GitHub page.
3.  Upload the newly generated `usda_data.db` file as a binary asset to that release.
4.  Update the download URL in the `entrypoint.sh` script to point to this new release asset.

## 4. Docker for Developers

This section outlines how to use Docker for local development. The setup uses volumes to persist database files. Note that live code reloading is not configured, but the image can be rebuilt quickly to incorporate changes.

### Prerequisites

1.  **Docker and Docker Compose:** Ensure Docker and Docker Compose are installed on your system.
2.  **`.env` file:** Copy the `.env.example` file to `.env` in the project root and configure your `SECRET_KEY`.
    ```bash
    cp .env.example .env
    ```
    
3.  **Typst Binary:** Ensure the `typst/` directory (containing the `typst` executable, a typesetting system used for generating PDF reports) is present in the project root. This directory is copied into the Docker image during the build process.

### Building and Running the Container

1.  **Build the image:**
    To build the Docker image, run the following command from the project root:
    ```bash
    docker compose build --no-cache
    ```
    Using the `--no-cache` flag is recommended when you have made changes to the `Dockerfile` or project dependencies.

2.  **Start the services:**
    To start the application, run:
    ```bash
    docker compose up
    ```
    Running the container in the foreground (without the `-d` flag) is useful for viewing logs directly in your terminal.

### How It Works

*   **Automated First-Time Setup:** The first time you run `docker compose up`, the `entrypoint.sh` script will automatically:
    *   Download the required USDA dataset.
    *   Build the `usda_data.db` from the downloaded CSV files.
    *   Run database migrations to create or update the `user_data.db`.
    *   Seed the database with essential portion and category data.
    This initial setup process can take several minutes.

*   **Persistent Data via Volumes:** The `docker-compose.yml` file is configured to use Docker volumes for the database files (`usda_data.db` and `user_data.db`). This means that once the databases are created, they will persist on your host machine between container restarts. Subsequent runs of `docker compose up` will be much faster as they will detect the existing databases and skip the build process.

### Development Workflow

Since the project files are copied into the image at build time, you need to rebuild the image to see your changes.

1.  **Make code changes** to the project files on your local machine.
2.  **Stop the container** if it is running (`Ctrl+C` or `docker compose down`).
3.  **Rebuild the image** to include your changes:
    ```bash
    docker compose build
    ```
    (You typically do not need `--no-cache` for simple code changes, which makes the rebuild faster).
4.  **Restart the container** to run the new code:
    ```bash
    docker compose up
    ```

## 5. Deploying to TrueNAS SCALE

This guide outlines how to deploy the OpenNourish Docker image to TrueNAS SCALE. This setup uses a private Docker registry to store the images, which is highly recommended for local network deployments.

### Step 1: Set Up a Private Docker Registry

Before you can deploy OpenNourish, you need a private Docker registry accessible by your TrueNAS server. You can set one up on TrueNAS itself by installing the **Docker Registry** application from the **Apps > Available Applications** page.

### Step 2: Build, Tag, and Push the Docker Images

From your development machine, follow these steps to prepare the images for deployment:

1.  **Build the images using the standard `docker-compose.yml`:**
    This file contains the necessary build instructions for the application and Nginx services.
    ```bash
    docker compose build
    ```

2.  **Tag the images for your private registry:**
    Replace `YOUR_REGISTRY_URL` with the address of your private registry (e.g., `your-truenas-ip:5000`).
    ```bash
    docker tag opennourish-app:latest YOUR_REGISTRY_URL/opennourish-app:latest
    docker tag opennourish-nginx:latest YOUR_REGISTRY_URL/opennourish-nginx:latest
    ```

3.  **Push the images to your registry:**
    ```bash
    docker push YOUR_REGISTRY_URL/opennourish-app:latest
    docker push YOUR_REGISTRY_URL/opennourish-nginx:latest
    ```

#### Step 2.1 Script
To build, tag, and push the Docker images to your private TrueNAS registry, and to generate the necessary YAML configuration for TrueNAS Custom Apps, use the `deploy_truenas.sh` script.

**IMPORTANT:** Before running the script, ensure you have set the following variables in your `.env` file:
- `TRUENAS_REGISTRY_URL`: The address of your TrueNAS registry (e.g., `your-truenas-ip:5000`).
- `SECRET_KEY`: Your Flask application's secret key.
- `REAL_CERT_PATH` (optional): The path to your real SSL certificate on TrueNAS (e.g., `/etc/certificates/LEProduction.crt`).
- `REAL_KEY_PATH` (optional): The path to your real SSL key on TrueNAS (e.g., `/etc/certificates/LEProduction.key`).
- `TRUENAS_APP_PATH` (REQUIRED): The base path on your TrueNAS server where application data will be stored (e.g., `/mnt/data-pool/opennourish`).

```bash
./deploy_truenas.sh
```

This script will:
1.  Build the Docker images using the standard `docker-compose.yml`.
2.  Tag the images with your specified registry URL.
3.  Push the tagged images to your private TrueNAS registry.
4.  Print the TrueNAS Custom App YAML configuration to your console. You will need to copy this output and paste it into the TrueNAS UI.

### Step 3: Deploy the Application on TrueNAS

The following YAML configuration should be used when creating a "Custom App" in the TrueNAS UI.

1.  In the TrueNAS UI, navigate to **Apps > Custom App**.
2.  Paste the following YAML into the **Docker Compose** editor:

    ```yaml
    services:
      opennourish-app:
        image: TRUENAS_REGISTRY_URL/opennourish-app:latest
        restart: unless-stopped
        environment:
          - SECRET_KEY=YourSuperStrongSecretKeyGoesHere
          - SEED_DEV_DATA=true # Set to 'false' or remove for production deployments
        volumes:
          - /mnt/data-pool/opennourish:/app/persistent

      nginx:
        image: TRUENAS_REGISTRY_URL/opennourish-nginx:latest
        restart: unless-stopped
        ports:
          - "18080:80"
          - "18443:443"
        environment:
          # These variables tell the entrypoint script where to find the real certs.
          # Users can change these values if their certs are named differently.
          # Leave these blank or unset them to use the self-signed fallback.
          REAL_CERT_PATH: /etc/certificates/yourname.crt
          REAL_KEY_PATH: /etc/certificates/yourname.key
        volumes:
          # 1. Mount the TrueNAS certificates directory so the container can see it.
          - /etc/certificates:/etc/certificates:ro
          # 2. Mount a persistent directory for Nginx to store its fallback certs.
          - /mnt/data-pool/opennourish/nginx_certs:/etc/nginx/certs
        depends_on:
          - opennourish-app
    ```
3.  **Important:** Before deploying, you must update the following values in the YAML you just pasted:
    *   Replace `saturn.ms4f.net:30095` with the address of your private registry for both `image` definitions.
    *   Set a strong, unique `SECRET_KEY` in the `environment` section of the `opennourish-app` service.
    *   Adjust the `volumes` paths (e.g., `/mnt/data-pool/opennourish`) to match the desired storage locations on your TrueNAS server.
    *   **Certificate Paths for Nginx:** If you are using real SSL certificates managed by TrueNAS (e.g., from Let's Encrypt), you will need to update the `REAL_CERT_PATH` and `REAL_KEY_PATH` environment variables under the `nginx` service in the YAML. These paths should point to where TrueNAS stores your certificates. You can typically find these paths by navigating to **System Settings > Certificates** in the TrueNAS UI, selecting your certificate, and inspecting its details or by checking the `/etc/certificates` directory on your TrueNAS server via SSH. You can copy these values from your local `.env` file.
4.  Deploy the application.

### 4. Running Tests and Measuring Coverage

The project uses the `pytest` framework for testing and the `coverage` package to measure how much of the code is exercised by the tests.

#### 4.1. Running the Test Suite

*   **Run All Fast Application Tests:** This is the most common command you will use. It runs all tests except for the slow integration tests.
    ```bash
    pytest -m "not integration"
    ```

*   **Run a Single Test File:** To focus on a specific feature you are working on.
    ```bash
    pytest tests/test_diary.py
    ```

*   **Run a Single Test Function:** For highly targeted debugging.
    ```bash
    pytest tests/test_diary.py::test_add_usda_food_to_diary -vvv
    ```

#### 4.2. Measuring Test Coverage

To ensure your changes are well-tested, you should run a coverage analysis.

    If something like the dev seed function should not count towards the production code we can remove it from coverage:
    ```
    # no cover: start
    ...
    ...
    ...
    # no cover: stop
    ```

1.  **Run Tests via Coverage:** This command runs the test suite while monitoring which lines of code are executed.
    ```bash
    coverage run -m pytest -m "not integration"
    ```

2.  **View a Quick Report:** To see a summary of coverage percentages directly in your terminal, use the `report` command. The `-m` flag will also highlight which line numbers are missing coverage. Gemini understands markdown tables better than clear text.
    ```bash
    coverage report -m --skip-covered --format=markdown --omit="test*"
    ```

3.  **Generate an Interactive HTML Report:** This is the most useful way to analyze coverage. It creates a detailed, clickable report.
    ```bash
    coverage html
    ```
    After the command finishes, open the `htmlcov/index.html` file in your web browser to explore which specific lines and branches of your code are not currently being tested.

4.  **All in one** 
    Without integration
    ```bash
    coverage run -m pytest -m "not integration" && coverage html && coverage report -m --skip-covered --format=markdown --omit="test*","/tmp/*"
    ```
    Full
    ```bash
    coverage run -m pytest && coverage html && coverage report -m --skip-covered --format=markdown --omit="test*","/tmp/*"
    ```


## 5. Creating pip requirments.txt for deployment

To create a `requirements.txt` file, run the following command in your virtual environment.

```bash
pip freeze > requirements.txt
```
To remove a package and all dependencies, run the following command:

```bash
pip install pip3-autoremove
pip-autoremove <package name> -y
pip uninstall pip3-autoremove
```bash

