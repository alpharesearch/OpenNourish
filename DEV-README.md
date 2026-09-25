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
    or better run that creates a backup
    ```bash
    ./safe_upgrade.sh
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

2.  **Tag the images under a namespace inside your private registry:**
    Replace `YOUR_REGISTRY_URL` with the address of your private registry (e.g., `your-truenas-ip:5000`).
    `docker-compose.yml` pins `name: opennourish`, so the local app image is always
    `opennourish-opennourish-app`, not `opennourish-app` and regardless of what the checkout directory
    is called — `deploy_truenas.sh` depends on that name.
    The `library/` path component is **load-bearing**, not decoration: see Step 2.2 for why dropping
    it silently costs you the Apps "update available" badge.
    ```bash
    docker tag opennourish-opennourish-app:latest YOUR_REGISTRY_URL/library/opennourish-app:latest
    docker tag opennourish-nginx:latest YOUR_REGISTRY_URL/library/opennourish-nginx:latest
    ```

3.  **Push the images to your registry:**
    ```bash
    docker push YOUR_REGISTRY_URL/library/opennourish-app:latest
    docker push YOUR_REGISTRY_URL/library/opennourish-nginx:latest
    ```

4.  **Confirm what a deployment is actually running.** Tags carry no identity here — `IMAGE_VERSION`
    in `deploy_truenas.sh` is a constant `V1.0.0` and TrueNAS pulls a mutable `:latest` — so read the
    image instead:
    ```bash
    docker exec <app-container> cat /app/BUILD_INFO
    docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' <app-container>
    ```
    The container log pane (TrueNAS → Apps → *OpenNourish* → Logs) prints the same block on every
    start, before the USDA download begins, so it is visible even when the boot then fails.
    `requirements_sha256` must equal `sha256sum requirements.txt` at the commit you believe is
    deployed. A bare `docker compose build` reports `revision=unknown` by design; use
    `./deploy_truenas.sh`, which stamps the git SHA and refuses to continue if a push fails.

#### Step 2.1 Script
To build, tag, and push the Docker images to your private TrueNAS registry, and to generate the necessary YAML configuration for TrueNAS Custom Apps, use the `deploy_truenas.sh` script.

**IMPORTANT:** Before running the script, ensure you have set the following variables in your `.env` file:
- `TRUENAS_REGISTRY_URL`: The address of your TrueNAS registry (e.g., `your-truenas-ip:5000`).
- `SECRET_KEY`: Your Flask application's secret key.
- `REAL_CERT_PATH` (optional): The path to your real SSL certificate on TrueNAS (e.g., `/etc/certificates/LEProduction.crt`).
- `REAL_KEY_PATH` (optional): The path to your real SSL key on TrueNAS (e.g., `/etc/certificates/LEProduction.key`).
- `TRUENAS_APP_PATH` (REQUIRED): The base path on your TrueNAS server where application data will be stored (e.g., `/mnt/data-pool/opennourish`).
- `TRUENAS_REGISTRY_NAMESPACE` (optional, default `library`): the single repository path component the images are pushed under. Omit it unless your registry insists on a particular namespace.

```bash
./deploy_truenas.sh
```

This script will:
1.  Build the Docker images using the standard `docker-compose.yml`.
2.  Tag the images under `<registry>/<namespace>/<name>` (default namespace `library`).
3.  Push the tagged images to your private TrueNAS registry.
4.  Print the TrueNAS Custom App YAML configuration to your console. You will need to copy this output and paste it into the TrueNAS UI.

#### Step 2.2 How TrueNAS decides an update is available

TrueNAS 25.10 never compares versions for a custom app — `IMAGE_VERSION` and `:latest` are irrelevant
to the badge. The badge is `app.query`'s `upgrade_available`, which for a custom app is set purely from
`image_updates_available`: middlewared's periodic sweep (`app.image.op.check_update`, on Docker service
start and every 86400 s, gated by `docker.config.enable_image_updates`) fetches
`https://<registry>/v2/<image>/manifests/<tag>` **anonymously** and compares the digest with the local
image's `RepoDigests`. Three consequences, all measured on the production NAS at 25.10.6:

- **The repository name must contain a slash.** `normalize_reference` prepends `library/` to any
  single-component repo name before building that URL — private registries included — while Distribution
  stores the repository exactly as pushed. Pushed `opennourish-app`, probed `library/opennourish-app`:
  200 versus 404, the 404 becomes a `CallError` that the sweep logs and swallows per image, and the badge
  never appears. Hence the namespace in `deploy_truenas.sh`.
- **The registry must allow anonymous manifest reads.** On 25.10 the update probe never sends the
  credentials stored under Apps → Registries (those are pull-only), so an htpasswd-protected registry is
  a hard 401 no path naming can fix.
- **The probe always speaks HTTPS with normal certificate validation.** The URL is hardcoded, so an
  HTTP-only or untrusted-cert registry is never detected; `insecure_registry_mirrors` configures the
  daemon, not this code path.

When the badge does appear, **Update** = `app.pull_images` + redeploy against the same tag — no manual
image deletion. It refuses while the app is stopped. To diagnose a missing badge on the NAS itself
(bash, root; do not put `# comments` on the same line as an assignment in zsh — zsh then treats the
assignment as that nonexistent command's environment and the variable stays empty):

```bash
curl -sk https://YOUR_REGISTRY/v2/_catalog                       # what names the registry stores
curl -s -o /dev/null -w '%{http_code}\n' -H 'Accept: application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json' https://YOUR_REGISTRY/v2/<name>/manifests/latest
midclt call app.image.query | jq -r '.[]|select((.repo_tags|join(" "))|test("opennourish"))|"tags=\(.repo_tags) digests=\(.repo_digests)"'
midclt call docker.config | jq .enable_image_updates
midclt call app.image.op.get_update_cache | jq 'with_entries(select(.key|test("opennourish")))'
```

`digests=[]` or a `404`/`401` there is the reason; a tag absent from the cache means the probe never
finished for it (on 25.10 a non-`CallError` transport failure aborts the whole sweep — fixed upstream by
a bare `except Exception`). A `false` left in the cache after an Update is not a verdict: pulling clears
the flag unconditionally.

### Step 3: Deploy the Application on TrueNAS

The following YAML configuration should be used when creating a "Custom App" in the TrueNAS UI.

1.  In the TrueNAS UI, navigate to **Apps > Custom App**.
2.  Paste the following YAML into the **Docker Compose** editor:

    ```yaml
    services:
      opennourish-app:
        image: TRUENAS_REGISTRY_URL/library/opennourish-app:latest
        restart: unless-stopped
        environment:
          - SECRET_KEY=YourSuperStrongSecretKeyGoesHere
          - SEED_DEV_DATA=true # Set to 'false' or remove for production deployments
        volumes:
          - /mnt/data-pool/opennourish:/app/persistent

      nginx:
        image: TRUENAS_REGISTRY_URL/library/opennourish-nginx:latest
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
    *   Replace `TRUENAS_REGISTRY_URL` with the address of your private registry for both `image` definitions. Keep the `/library` component — see Step 2.2.
    *   Set a strong, unique `SECRET_KEY` in the `environment` section of the `opennourish-app` service.
    *   Adjust the `volumes` paths (e.g., `/mnt/data-pool/opennourish`) to match the desired storage locations on your TrueNAS server.
    *   **Certificate Paths for Nginx:** If you are using real SSL certificates managed by TrueNAS (e.g., from Let's Encrypt), you will need to update the `REAL_CERT_PATH` and `REAL_KEY_PATH` environment variables under the `nginx` service in the YAML. These paths should point to where TrueNAS stores your certificates. You can typically find these paths by navigating to **System Settings > Certificates** in the TrueNAS UI, selecting your certificate, and inspecting its details or by checking the `/etc/certificates` directory on your TrueNAS server via SSH. You can copy these values from your local `.env` file.
4.  Deploy the application.

### Step 4: Deploying an Update

`./deploy_truenas.sh` pushes only — it does not touch a running deployment. After the push, TrueNAS
flags the app with *update available* on its own once the digest sweep has run (within 24 h, or at the
next Docker service start; see Step 2.2), and **Apps → OpenNourish → Update** pulls the new digest and
redeploys. If the app was installed from a YAML whose `image:` lines lacked the `/library` namespace,
one manual edit of those two lines is required — the flag can never appear for an unnamespaced name.
Verify what actually came up with `cat /app/BUILD_INFO` in the container, per Step 2 item 4; the digest
is not a revision, and `:latest` never is.

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


## 6. Regenerating requirements.txt

`requirements.txt` is **generated**. The hand-edited surface is `requirements.in` (direct
dependencies only). Never run `pip freeze > requirements.txt`: it bakes in every transitive
package, silently re-adds whatever a dependency requires, and is how this file drifted from the
code before (abandoned `aioredis`, an unused `httpx` chain, and an unpinned `pytz`).

The resolver is pip-tools. It lives in the conda env, deliberately **not** in `requirements.in`:

```bash
conda run -n opennourish python -m pip install pip-tools   # once per machine
# resolve with the 3.12 interpreter, since pip-compile resolves for the interpreter it runs under
conda run -n opennourish python -m piptools compile --strip-extras -o requirements.txt requirements.in
conda run -n opennourish python -m pip install -r requirements.txt
conda run -n opennourish python -m pip check     # must print "No broken requirements found"
```

`pip-tools` pulls `build`, `setuptools`, `wheel` and `pyproject_hooks` into the env with it. Keep it
out of `requirements.in`, because the Dockerfile installs that lock and these are pure build tools —
they would ship in the runtime image for no reason. `gen_licenses.py` iterates the lock's pins, so
packages installed on top of the lock are invisible to `--check`, and `pip check` stays silent.

**`--strip-extras` is required, not stylistic.** Without it pip-compile writes
`coverage[toml]==7.16.1`, and `gen_licenses.py` parses lock names by splitting on `==` — the licence
gate then reports `coverage[toml]` as pinned-but-not-installed and fails.

Three things the resolver does that look like damage and are not. It rewrites the file's header, so
provenance notes, verification counts and anything else written by hand do not survive regeneration —
keep that prose in this file, not in a generated one. **Do not read that header as evidence of what
was run**: pip-compile records `--no-index` on every pass regardless of the flags, because its
header builder skips an option only when `option.default == value` and this flag's default is
`Sentinel.UNSET` against a `False` value. Resolution is genuinely online (a `six` requirement
compiles to the current release on an interpreter where `six` is absent). And it normalises pins to
PEP 503 lowercase (`typing_extensions` becomes `typing-extensions`), which pip accepts.

Then run the four gates in `AGENTS.md` before committing. To drop a dependency, remove it from
`requirements.in` and re-resolve — hand-deleting a line from `requirements.txt` does nothing, the
resolver puts it back.

`THIRD-PARTY-LICENSES.md` is generated too, from whatever environment has this lock installed, so
regenerate it in the same pass:

```bash
conda run -n opennourish python gen_licenses.py          # rewrites THIRD-PARTY-LICENSES.md
conda run -n opennourish python gen_licenses.py --check  # fails if it no longer matches the lock
```

It reads each installed wheel's own licence file, so it needs the environment to match
`requirements.txt` exactly — it warns on any pin it cannot find at that version.

To remove a package and all dependencies, run the following command:

```bash
pip install pip3-autoremove
pip-autoremove <package name> -y
pip uninstall pip3-autoremove
```

