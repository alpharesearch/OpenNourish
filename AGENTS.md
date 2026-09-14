# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## Purpose

OpenNourish is a self-hosted, multi-user food and nutrition tracker built on the USDA FoodData Central dataset. Server-rendered Flask + Jinja + Bootstrap, SQLite, deployed with Docker on TrueNAS. MIT licensed.

## Ownership

Root owns the repository-wide contract and the top-level files that have no folder of their own:

- `models.py` — all 19 SQLAlchemy models and the two-bind layout.
- `constants.py` — diet presets, pinned USDA `CORE_NUTRIENT_IDS`, meal configuration, endpoint-name constants.
- `config.py` — `Config`, secret-key bootstrap, DB-backed system settings loader.
- `app.py`, `serve.py` — WSGI entry points; `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `nginx/` — deployment.
- `import_usda_data.py`, `schema_usda.sql`, `seed_db.sh`, `seed_usda.sh`, `safe_upgrade.sh`, `deploy_truenas.sh`, `proj_snap.sh` — data import and operations scripts.
- `README.md` (install/usage), `DEV-README.md` (dev procedures), `GEMINI.md` (AI-assistant onboarding doc; `QWEN.md` is an untracked hardlink of it).
- Children own their subtree; anything not listed here and not in a child is root's by default.

## Local Contracts

### Toolchain

- Run everything under the conda env `opennourish`: `/home/markus/miniconda3/envs/opennourish/bin/python`. Conda `base` has no Flask and will fail at import.
- Stack is pinned in `requirements.txt`: Flask 3.1.1, SQLAlchemy 2.0.41 + Flask-SQLAlchemy 3.1.1, Alembic/Flask-Migrate, Flask-Login, Flask-WTF, Flask-Mailing, waitress. Bootstrap CSS, Bootstrap Icons, Chart.js, and fonts are vendored in `static/`; there is no npm/bundler step.
- Nutrition-label PDF/SVG generation shells out to the `typst` binary (`opennourish/typst_utils.py`); the Dockerfile downloads it. Without `typst` on PATH, label routes fail while the rest of the app works.

### Persistence and secrets

- Two SQLite databases live in `persistent/`, gitignored: `user_data.db` (default bind) and `usda_data.db` (bind `usda`, roughly 1.7 GB). Never read, grep, or glob `usda_data.db` wholesale; query it with explicit limits. `persistent/backups/` and `persistent/secret_key.txt` also live there.
- `persistent/usda_data/*.csv` is the raw USDA FoodData Central drop consumed by `import_usda_data.py`.
- `.env` is gitignored and untracked; `.env.example` is the documented surface. `config.py` raises at import if `SECRET_KEY` or `ENCRYPTION_KEY` is missing.
- `ENCRYPTION_KEY` encrypts `MAIL_PASSWORD` stored in `system_settings`; rotating it silently invalidates stored mail credentials, so re-enter them in the admin settings page after rotation.

### Data model layout

- Bind `usda` (read-only reference data): `Food` (foods), `Nutrient` (nutrients), `FoodNutrient` (food_nutrients). Everything else is on the default bind, including `FoodCategory`, which is seeded from USDA text but stored with user data.
- Nutrient values for a food are `FoodNutrient` rows keyed by pinned `constants.CORE_NUTRIENT_IDS` (14 ids) and expressed per 100 g. `MyFood` and `Recipe` instead persist the same **15** explicit `*_per_100g` columns in identical order (`models.py:266-280` vs `:335-349`); duplicates by design, changed together. `added_sugars` is in the model columns but commented out of `CORE_NUTRIENT_IDS` and never written by `update_recipe_nutrition`, so `Recipe.added_sugars_per_100g` is permanently 0 while the `MyFood` one is editable.
- Item trios are mutually exclusive, not combined: `DailyLog`, `RecipeIngredient`, and `MyMealItem` each carry exactly one of `fdc_id`, `my_food_id`, `recipe_id`, plus `amount_grams`, `serving_type`, and `portion_id_fk`.
- `UserGoal.id` is a surrogate autoincrement key, **not** the user id (`user_id` is a separate FK). Resolve goals with `UserGoal.query.filter_by(user_id=...)`; `db.session.get(UserGoal, user_id)` returns whichever goal row happens to carry that surrogate PK — the wrong-PK idiom was fixed at three call sites (diary, profile, onboarding) and is locked by tests, do not reintroduce it.
- `UnifiedPortion` (table `portions`) is the single portion table for all three food sources: exactly one of `my_food_id`, `recipe_id`, `fdc_id` is set, with `seq_num` ordering, `gram_weight` as the conversion truth, and `full_description_str` as the display string. A diary or ingredient row whose `portion_id_fk` and `amount_grams` disagree with `gram_weight` is corrupt — set both together, through the helper rather than by hand.
- Cross-bind joins are invalid. Use the `foreign(...)` viewonly relationships declared in `models.py`, or load ids in Python.
- User privilege flags: `is_admin`, `is_key_user` (USDA data editing), `is_verified` (gates public visibility and sending friend requests), `is_active`, `has_completed_onboarding`. Reading another user's data requires an accepted `Friendship`. `is_private` is **not** a read gate — it only hides an account from the friend search (`friends/routes.py:75`); profile and friends reads are gated purely by friendship, so treat friendship as the only privacy boundary you may rely on.

### Schema changes

- Change `models.py`, then generate a migration. Apply with `./safe_upgrade.sh`, which backs up first; plain `flask db upgrade` does not.
- Tests build their schema with `db.create_all()`, so a green suite does **not** prove the migration works. Run the migration against a copy of a real database.
- Alembic manages the default bind only; `migrations/AGENTS.md` is authoritative here.

### Runtime and deployment

- `serve.py` runs waitress on `0.0.0.0:8081` with `clear_untrusted_proxy_headers=False` so `ProxyFix` can read `X-Forwarded-*`. That means the app trusts forwarded headers from **any** peer that reaches it directly: never expose :8081 without the reverse proxy in front.
- `app.py` is the dev entry point (`app.run(debug=True)` on 127.0.0.1:5000); it is never used by the image.
- `docker-compose.yml` publishes no port for the app; only `nginx` maps 80/443 and reaches the app over the compose network by service name. The `README` claim about `localhost:8081` is wrong.
- `entrypoint.sh` runs with `set -e` and, on a fresh volume, downloads a pinned USDA CSV zip, rebuilds `usda_data.db`, runs `safe_upgrade.sh`, then `seed-usda-portions`, `seed-usda-categories`, `seed-exercise-activities`, `seed-dev-data`. Any step failing is a boot loop; `seed-usda-portions` re-runs on every start and deletes `was_imported` portions each time.
- `nginx/nginx.conf` sets no `client_max_body_size`, so uploads are capped at the 1 MiB default — relevant to the YAML food and recipe importers.
- `.dockerignore` does not exclude `.kilocode/` or `htmlcov/`, so `COPY . .` bakes tens of megabytes of junk into every image.

### Destructive scripts — read before running

- `seed_usda.sh:10` deletes `persistent/user_data.db` unconditionally and `:30` autogenerates a migration into tracked `migrations/versions/`. Do not run it in a working clone.
- `seed_db.sh:13` guards on `user_data.db` in the repo root, which never exists, so its reset branch silently does nothing and the subsequent upgrade runs against the live database.
- `safe_upgrade.sh` only backs up the hard-coded `persistent/user_data.db`; with `DATABASE_URL` set elsewhere it migrates without a backup.
- `deploy_truenas.sh:20` does an unquoted `export $(cat .env | ...)`, which word-splits values with spaces and exports every unrelated key in `.env`; it then prints `SECRET_KEY`, `ENCRYPTION_KEY`, and `MAIL_PASSWORD` to stdout. It also derives image names from the checkout directory name, so it only works from a directory called `opennourish`.

### Security

- There is **no global CSRF protection**: `CSRFProtect` is not registered, so only Flask-WTF forms carrying `hidden_tag()` are protected (~29 of ~98 forms). Close gaps by converting forms or registering `CSRFProtect`, never by hand-rolling tokens.
- Cross-user reads require an accepted `Friendship`, and any write addressed by id must verify the row's owner is `current_user` (or that the row is legitimately orphaned). The historical violations — the unauthorised friend-diary/copy-meal read, the unguarded recipe label SVG, the ownership test that only rejected deleted owners (`search`), and `undo` restoring with a session-supplied `user_id` — are all closed and locked by tests. Keep the real idiom (plain ownership check plus the friendship rule); do not reintroduce the `... and not obj.user` predicate that only rejects deleted owners.
- `SEED_DEV_DATA=true` on an empty database creates an administrator named `markus` with password `1` (`opennourish/__init__.py:298-301`), and `.env.example` ships it set to `true`. Registration is open by default and, with `INITIAL_ADMIN_USERNAME` unset, the first registrant becomes admin. Never take this combination to a public host.
- `ENCRYPTION_KEY` guards only `MAIL_PASSWORD`; reset and verification tokens are signed with `SECRET_KEY`. Rotating either has user-visible consequences documented in `opennourish/admin/AGENTS.md` and `opennourish/auth/AGENTS.md`.

## Work Guidance

- Keep user data scoped by `user_id` in every query, and verify ownership for anything addressed by id.
- Do not commit `persistent/`, `htmlcov/`, `.coverage`, `project_snapshot.txt`, `.kilocode/`, `.vscode/`, or `__pycache__/` — all are ignored today; keep it that way.
- `DEV-README.md` and `README.md` drift from the code; trust this tree. Known mismatches: `DEV-README.md` `rm user_data.db` and the `typst/` directory requirement, `README.md:11-13` contradicting itself on where `usda_data/` lives, `README.md:113` naming a port compose never publishes, and `README.md:98` omitting that `ENCRYPTION_KEY` is mandatory. Fix the doc in the same change as the behaviour.
- `THIRD-PARTY-LICENSES.md` is a hand-maintained snapshot and is missing entries for Flask, Flask-Login/Migrate/WTF/SQLAlchemy, cryptography, PyJWT, Jinja2, PyYAML, and every vendored asset in `static/`. Treat it as incomplete, not authoritative.
- `DATABASE_URL`, `USDA_DATABASE_URL`, `FLASK_APP` are read but undocumented in `.env.example`; `MAIL_CONFIG_SOURCE` and `FLASK_DEBUG` are documented or deployed as env vars but read by no code (mail source is DB-only). Correct `.env.example` when touching configuration.
- No CI, no pre-commit config, and no active git hooks exist. Every check below is run manually by whoever makes the change.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q     # full non-integration suite
$P -m ruff check .                        # lint gate
$P -m ruff format --check .               # formatting gate
```

Coverage and the single `integration` test (needs `persistent/usda_data/*.csv`) are covered in `tests/AGENTS.md`.

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

## Child DOX Index

- `opennourish/AGENTS.md` — Flask app factory, blueprint registry, shared services, cross-cutting authorization/timezone/nutrition rules.
  - `opennourish/search/AGENTS.md`, `recipes/`, `my_foods/`, `diary/`, `dashboard/`, `tracking/`, `goals/`, `admin/`, `auth/` — one per feature blueprint with its own contracts.
- `templates/AGENTS.md` — Jinja inheritance, base blocks, Chart.js conventions, flash/CSRF patterns, the analytics duplication.
- `tests/AGENTS.md` — pytest fixtures, markers, coverage commands, current gate.
- `migrations/AGENTS.md` — Alembic history for the default bind, SQLite batch-mode rules, backup-first upgrade.
- Root keeps direct ownership of `models.py`, `config.py`, `constants.py`, `app.py`, `serve.py`, `import_usda_data.py`, `alembic.ini`, the ops shell scripts, `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `nginx/`, `static/`, and `requirements.txt`.
- Blueprints without their own doc (onboarding, main, friends, profile, settings, exercise, fasting, undo, usda_admin) are governed by `opennourish/AGENTS.md`, except `usda_admin`, governed by `opennourish/admin/AGENTS.md`.
