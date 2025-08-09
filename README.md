# OpenNourish
OpenNourish is a free and open source food tracker.

## Installation

1. **Download the USDA FoodData Central dataset:**
   - Go to the [USDA FoodData Central download page](https://fdc.nal.usda.gov/download-datasets.html).
   - Download the latest "FoodData Central, April 2025: All data" dataset (or a newer version if available).
   - Unzip the downloaded FoodData_Central_csv_2025-04-24.zip file into ./persistent/usda_data/ folder.

2. **Organize the data files:**
   - Create a folder named `usda_data` in the root of the OpenNourish project directory.
   - From the unzipped USDA dataset, copy all CSV files into the `usda_data` folder.

3. **Set up the environment and install dependencies:**
   - It is recommended to use a Conda environment:
     ```bash
     conda create --name opennourish python=3.9
     conda activate opennourish
     ```
   - Install the required Python packages:
     ```bash
     pip install -r requirements.txt
     ```

4. **Create a `.env` file:**
    - Copy the `.env.example` file to `.env` in the project root:
      ```bash
      cp .env.example .env
      ```
    - Open the newly created `.env` file and replace the placeholder `SECRET_KEY` with a strong, random key.
    - You can generate a secure key using Python:
      ```python
      import secrets
      secrets.token_hex(16)
      ```
    - Also, add an `ENCRYPTION_KEY` to your `.env` file. This key is crucial for encrypting sensitive data like email passwords stored in the database.
    - You can generate a strong, URL-safe `ENCRYPTION_KEY` using Python:
      ```python
      from cryptography.fernet import Fernet
      print(Fernet.generate_key().decode())
      ```
      ```bash
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
      ```
    - The `SEED_DEV_DATA` variable in `.env` controls whether development data is seeded on the first run. Set it to `true` for development or `false` for a clean production setup.

5. **Install Typst:**
   - Typst is an external dependency required for generating nutrition labels. For non-Docker installations, you need to ensure the `typst` executable is available in your system's PATH (e.g., by placing it in `/usr/local/bin`).
   - Download the pre-built binary for your system from the official Typst website: [https://github.com/typst/typst/](https://github.com/typst/typst/).
   - **Note:** The `typst/` directory in the project root is primarily used for the Docker build context. If you are running the application outside of Docker, ensure `typst` is installed and accessible via your system's PATH.
   - **Note:** The snapd version of Typst may have limitations. Refer to the "Typst PDF Generation Issues" in the Troubleshooting section for more details.

6. **Install Liberation Sans Font:**
   - Ensure the Liberation Sans font is installed on your system. This font is used for generating nutrition labels. On Debian/Ubuntu-based systems, you can install it using:
     ```bash
     sudo apt-get update && sudo apt-get install -y fonts-liberation
     ```
     For other operating systems, please refer to your system's documentation for font installation.

7. **Create and populate the database:**
   - Run the import script to build the `usda_data.db` file from the USDA data. This may take a few minutes.
     ```bash
     python import_usda_data.py [--keep_newest_upc_only]
     ```
   - The `--keep_newest_upc_only` flag (optional) will ensure that if multiple food entries share the same UPC, only the one with the most recent `available_date` is imported. By default, all entries with duplicate UPCs will be imported.
   - Initialize the user database (only needed the very first time you set up the project):
     ```bash
     flask db init
     ```
   - Apply any pending database migrations to create the necessary tables:
     ```bash
     flask db upgrade
     ```
   - Seed the unified portion system with USDA data. This is crucial for the application to function correctly with USDA foods.
     ```bash
     flask seed-usda-portions
     ```
   - Seed the food categories from the USDA data.
     ```bash
     flask seed-usda-categories
     ```

8. **Run the Flask application:**
   - Start the web server:
     ```bash
     flask run
     ```
   - Open your web browser and navigate to `http://127.0.0.1:5000` to use the application.

## Docker Setup

OpenNourish is designed for a fully automated setup using Docker. The container handles everything from downloading data to initializing databases on the first run.

### Prerequisites

1.  **Docker and Docker Compose:** Ensure Docker and Docker Compose (v2.x, using `docker compose` command) are installed on your system.
2.  **`.env` file:** In the project root, create a file named `.env` and add your `SECRET_KEY`.

### Running the Application

1.  **Clone the repository.**
2.  **Navigate to the project root directory.**
3.  **Start the application:**
    ```bash
    docker compose up
    ```

**Note:** The first time you run the container, it will automatically download and process the entire USDA dataset, which may take several minutes depending on your system. Subsequent startups will be instant.

### Accessing the Application

The application will be accessible in your web browser at the port mapped by Docker Compose (typically `http://localhost:8081`). Check your `docker-compose.yml` for the exact port mapping.

### Stopping the Application

To stop the running containers, press `Ctrl+C` in the terminal where compose is running, or run:
```bash
docker compose down
```

## Email Configuration and Password Reset

OpenNourish includes a password reset feature that relies on email functionality. To enable and configure this:

- **Configuration Source:** You can choose to configure email settings either via the Admin Panel (Database) or directly through Environment Variables. This choice is made in the Admin Panel under Email Settings.
- **Password Reset:** The primary reason to configure email settings is to enable the password reset functionality, allowing users to recover their accounts.
- **Email Verification:** If enabled, new users will receive a verification email upon registration and must verify their email address before being able to make their recipes public.
- **Environment Variables:** If you choose to use environment variables, ensure the following are set in your `.env` file:
  - `MAIL_CONFIG_SOURCE=environment`
  - `ENABLE_PASSWORD_RESET=true`
  - `ENABLE_EMAIL_VERIFICATION=true`
  - Other `MAIL_*` variables (e.g., `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_SUPPRESS_SEND`). Refer to the `.env.example` file for a complete list and descriptions of these variables.

## Administrator Privileges

OpenNourish provides a flexible, two-pronged approach for assigning administrator rights, ensuring both ease of setup and control over user permissions.

### 1. Easy Install: First User Becomes Admin
If no specific admin user is designated via an environment variable, the system operates in "easy install" mode. In this mode, the **very first user** to register in a new OpenNourish instance is automatically granted full administrator privileges. This is ideal for single-user instances or for quickly setting up a new environment without extra configuration.

A confirmation message will be displayed to the user upon their first login, informing them of their new admin status. All subsequent users will register with standard, non-admin permissions.

### 2. Pre-designated Admin via Environment Variable
For more controlled setups, you can pre-designate an administrator by setting the `INITIAL_ADMIN_USERNAME` environment variable in your `.env` file.

Example `.env` configuration:
```
INITIAL_ADMIN_USERNAME=my_admin_user
```

This method has two effects:
- **On Registration:** If a new user registers with a username that exactly matches the value of this variable, they will be granted administrator rights immediately upon creation.
- **Retroactive Promotion:** If a user with that username already exists but does not have admin rights, the system will automatically promote them to an administrator the next time they log in. A message will flash to inform them of the change.

This retroactive capability is particularly useful for granting admin access to an existing user without needing to modify the database manually.

### 3. Command-Line Interface (CLI)

For existing users, you can manually grant or revoke administrator rights using a Flask CLI command.

-   **To grant admin rights:**
    ```bash
    flask user manage-admin <username> --action grant
    ```

-   **To revoke admin rights:**
    ```bash
    flask user manage-admin <username> --action revoke
    ```
This provides a flexible and secure way to manage administrator access after the initial setup.

## Troubleshooting

### Typst PDF Generation Issues
If you encounter errors when generating nutrition labels (e.g., "input file not found"), ensure that your `typst` installation is not the snapd version. The snapd version of `typst` may have restrictions that prevent it from accessing files outside of your home directory, which can cause issues with temporary files generated by the application. It is recommended to install `typst` directly from its official releases or a package manager that does not impose such restrictions.
