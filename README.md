# OpenNourish
OpenNourish is a free and open source food tracker.

## Installation

1. **Download the USDA FoodData Central dataset:**
   - Go to the [USDA FoodData Central download page](https://fdc.nal.usda.gov/download-datasets.html).
   - Download the latest "FoodData Central, April 2025: All data" dataset (or a newer version if available).
   - Unzip the downloaded FoodData_Central_csv_2025-04-24.zip file.

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
    - In the project root, create a file named `.env`.
    - Add the following line to this file, replacing the placeholder with a strong, random key:
      ```
      SECRET_KEY='a_very_strong_and_random_secret_key'
      ```
    - You can generate a secure key using Python:
      ```python
      import secrets
      secrets.token_hex(16)
      ```

5. **Install Typst:**
   - Typst is an external dependency required for generating nutrition labels. Follow the installation instructions on the official Typst website: [https://typst.app/docs/getting-started/](https://typst.app/docs/getting-started/)
   - **Note:** The snapd version of Typst may have limitations. Refer to the "Typst PDF Generation Issues" in the Troubleshooting section for more details.

6. **Install Liberation Sans Font:**
   - Ensure the Liberation Sans font is installed on your system. This font is used for generating nutrition labels. On Debian/Ubuntu-based systems, you can install it using:
     ```bash
     sudo apt-get update && sudo apt-get install -y fonts-liberation
     ```
     For other operating systems, please refer to your system's documentation for font installation.

6. **Create and populate the database:**
   - Run the import script to build the `usda_data.db` file from the USDA data. This may take a few minutes.
     ```bash
     python import_usda_data.py [--keep_newest_upc_only]
     ```
   - The `--keep_newest_upc_only` flag (optional) will ensure that if multiple food entries share the same UPC, only the one with the most recent `available_date` is imported. By default, all entries with duplicate UPCs will be imported.
   - Run `flask init-user-db` to initialize the `user_data.db`.

7. **Run the Flask application:**
   - Start the web server:
     ```bash
     flask run
     ```
   - Open your web browser and navigate to `http://127.0.0.1:5000` to use the application.

## Docker Setup

OpenNourish can be easily containerized using Docker for consistent development and deployment environments.

### Prerequisites

1.  **Docker and Docker Compose:** Ensure Docker and Docker Compose (v2.x, using `docker compose` command) are installed on your system.
2.  **`.env` file:** Create a `.env` file in the project root with your `SECRET_KEY` (as described in step 4 of the "Installation" section).
3.  **USDA Data:** Ensure you have the `usda_data/` directory populated with USDA CSV files (as described in step 2 of the "Installation" section).
4.  **Initial Database Setup:** Before running Docker, ensure your `user_data.db` and `usda_data.db` files are generated and migrated on your host machine. This is crucial as Docker volumes will mount these files into the container.
    *   Generate `usda_data.db`: `python import_usda_data.py`
    *   Initialize and migrate `user_data.db`:
        ```bash
        export FLASK_APP=app.py # or $env:FLASK_APP="app.py" for PowerShell
        flask db init # Only run this once for a new project
        flask db upgrade
        ```
5.  **Typst Binary:** Ensure the `typst/` directory (containing the `typst` executable and any necessary libraries) is present in the project root. This directory will be copied into the Docker image.

### Building the Docker Image

Navigate to the project root directory and build the Docker image:

```bash
docker compose build --no-cache
```
The `--no-cache` flag ensures a fresh build, which is useful after making changes to the `Dockerfile` or dependencies.

### Running the Application

Start the application services using Docker Compose in detached mode:

```bash
docker compose up -d
```

### Accessing the Application

The application will be accessible in your web browser at `http://localhost:8081`.

*   **Note on `localhost` vs. Internal IP:** If `http://localhost:8081` does not work, but you can access the application via an internal Docker IP (e.g., `http://172.18.0.2:8081`), it indicates a host-specific networking issue (e.g., firewall, `localhost` resolution). The Docker setup itself is likely correct in such cases.

### Stopping the Application

To stop the running containers:

```bash
docker compose down
```

### Rebuilding and Restarting (Troubleshooting)

If you encounter issues or need to apply changes to your code/dependencies:

1.  Stop and remove existing containers: `docker compose down`
2.  Rebuild the image: `docker compose build --no-cache`
3.  Start the application: `docker compose up -d`

## Troubleshooting

### Typst PDF Generation Issues
If you encounter errors when generating nutrition labels (e.g., "input file not found"), ensure that your `typst` installation is not the snapd version. The snapd version of `typst` may have restrictions that prevent it from accessing files outside of your home directory, which can cause issues with temporary files generated by the application. It is recommended to install `typst` directly from its official releases or a package manager that does not impose such restrictions.
