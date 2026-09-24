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
- `app.py`, `serve.py` — WSGI entry points; `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `nginx/` — deployment; `.github/workflows/ci.yml` — the gate workflow.
- `import_usda_data.py`, `schema_usda.sql`, `seed_db.sh`, `seed_usda.sh`, `safe_upgrade.sh`, `deploy_truenas.sh`, `proj_snap.sh` — data import and operations scripts.
- `README.md` (install/usage), `DEV-README.md` (dev procedures), `GEMINI.md` (AI-assistant onboarding doc; `QWEN.md` is an untracked hardlink of it).
- `gen_licenses.py` → `THIRD-PARTY-LICENSES.md` — the generated licence inventory covering the lock and the vendored files in `static/`.
- Children own their subtree; anything not listed here and not in a child is root's by default.

## Local Contracts

### Toolchain

- Run everything under the conda env `opennourish` (**Python 3.12**): `/home/markus/miniconda3/envs/opennourish/bin/python`. Conda `base` has no Flask and will fail at import, and the pre-move 3.9 clone is deleted — the 3.12 image is deployed and confirmed on TrueNAS, so there is no rollback env left and none is needed.
- **Python 3.12 is a hard floor.** The `Dockerfile` builds on `python:3.12` and `python:3.12-slim`, and ruff's formatter emits PEP 701 nested-quote f-strings inside `opennourish/typst_utils.py`, so 3.11 and below cannot even import that module. Keep both build stages on the same minor: `/opt/venv` is copied between them and is not portable across interpreters.
- Dependency source of truth is `requirements.in`; `requirements.txt` is **generated** from it by `pip-compile --strip-extras`, run with the 3.12 interpreter (procedure in `DEV-README.md` § "Regenerating requirements.txt"). Two things there are contracts, not taste: `--strip-extras` is mandatory, because pip-compile otherwise writes `coverage[toml]==…` and `gen_licenses.py` reports that installed package as pinned-but-not-installed; and the header pip-compile writes **always claims `--no-index`** whatever you passed, so it is not evidence of what was run. Provenance prose never belongs in the lock — the resolver's header pass erases it, which is how a "Verified: 972 passed" line went stale inside a generated file, and pins come back PEP 503 lowercase. pip-tools lives in the conda env and must stay out of `requirements.in`: the Dockerfile installs that lock, so it would ship `build`/`setuptools`/`wheel`/`pyproject_hooks` in the image. Never `pip freeze > requirements.txt` — that is how the file accumulated abandoned `aioredis`, an unused `httpx` chain, and an untracked `pytz`. Hand-deleting a line from `requirements.txt` also does nothing: the resolver puts it back.
- Stack: Flask 3.1.3, SQLAlchemy 2.0.54 + Flask-SQLAlchemy 3.1.1, Alembic/Flask-Migrate, Flask-Login, Flask-WTF 1.3.0, Flask-Mailing 3.0.0, waitress. Flask-Mailing 3.x no longer initialises on an empty `MAIL_SERVER` and renamed its suppression key, both of which this app depends on — `opennourish/AGENTS.md` owns that init contract. `Faker` is a runtime dep, not dev: `entrypoint.sh` seed steps use it. After any lock change, `pip check` must stay silent and the env must actually match the file. `static/` holds vendored front-end files and there is **no npm/bundler step**: Bootstrap 5.3.3 (css + bundle), Bootstrap Icons 1.11.3 (css, plus `static/fonts/bootstrap-icons.woff2`, which is the only file in that directory), Chart.js 4.5.0, and html5-qrcode 2.3.8 (Apache-2.0 — its minified file carries no version banner, so its identity is its sha256). `gen_licenses.py` records those versions and hashes.
- `djlint==1.46.2` lints Jinja templates: `$P -m djlint templates --profile jinja --extension html --use-gitignore`. djlint ignores `.gitignore` unless `--use-gitignore` is passed, so an unscoped `djlint .` sweeps the 209 generated `htmlcov/*.html`. Nothing new belongs in `.gitignore`: djlint writes no cache or backup files, and its `.djlintrc` config is meant to be committed. Its transitive deps (`cssbeautifier`, `jsbeautifier`, `EditorConfig`, `json5`, `pathspec`, `regex`) ship in the image, because the Dockerfile installs this same file — and so does **djlint itself, which is GPL-3.0-or-later**. That is compliant while it ships unmodified with its licence text, which `THIRD-PARTY-LICENSES.md` carries, and the runtime/dev split that would remove it was weighed and **dropped on 2026-09-23**: treat copyleft-in-image as accepted state, not an open item. What it does rule out is modifying djlint or shipping a derivative of it.
- djlint is advisory, not a gate: one pass over the 43 templates reports 204 findings — 101 H021 (inline styles), 81 H029 (`method="POST"`), 6 H043, 3 T038, 2 T002, and 6 **H025 orphan tags, which is structural and worth reading**. `--reformat` rewrites 42 of 43 files in a single pass, so reformat file-by-file, never tree-wide.
- Nutrition-label PDF/SVG generation shells out to the `typst` binary (`opennourish/typst_utils.py`), downloaded in the `Dockerfile` and pinned there at **v0.15.1**; `.github/workflows/ci.yml` greps that URL instead of repeating it, so the version lives in exactly one place — never add a second pin. Without `typst` on PATH, label routes fail while the rest of the app works. The templates import `@preview/nutrition-label-nam:0.2.0` and `@preview/codetastic:0.2.2`, which the image does **not** cache: the first render in a container needs outbound internet (`upgrade-research/PLAN.md` M5).
- **User-entered text reaches Typst as markup, not as data.** The templates interpolate food and recipe descriptions after a `=` heading and `_sanitize_for_typst` escapes only `\ " *`, so `$`, `#`, `<`, `@` stay live syntax: a name containing `$` fails its label with `unclosed dollar` (a 500) on every Typst version, and `#link("")`-shaped markup renders on ≤0.13 but errors on ≥0.14. Escaping `$ # < > @` is the fix, tracked in `upgrade-research/PLAN.md` M5. Renderer upgrades are otherwise safe here — 0.13.1 → 0.15.1 was verified pixel-identical.

### Persistence and secrets

- Two SQLite databases live in `persistent/`, gitignored: `user_data.db` (default bind) and `usda_data.db` (bind `usda`, roughly 1.7 GB). Never read, grep, or glob `usda_data.db` wholesale; query it with explicit limits. `persistent/secret_key.txt` lives there too.
- **`safe_upgrade.sh` is the only database copy in this repo, and it is a pre-migration net, not a backup policy.** It copies `persistent/user_data.db` to `persistent/backups/user_data.db.bak-<timestamp>` before `flask db upgrade`, but only when the database is behind head (`:21`) and the file already exists (`:31`) — so a fresh volume legitimately has an absent or empty `backups/`, which is correct behaviour, not a failed backup. Consequently the per-boot `seed-usda-portions` deletions run with no fresh copy behind them, and nothing here protects against data loss *between* migrations. `proj_snap.sh` is unrelated: it concatenates project text files into `project_snapshot.txt`, not a filesystem snapshot. Dataset-level protection has to come from TrueNAS snapshot tasks, configured outside this repo.
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
- `docker-compose.yml` publishes no port for the app; only `nginx` maps 80/443 and reaches the app over the compose network by service name. The `README` claim about `localhost:8081` is wrong. Compose prefixes images with the project name, so the local build is `opennourish-opennourish-app` — `deploy_truenas.sh` depends on that exact name.
- **The image identifies itself, because its tags do not.** `VCS_REF`/`BUILD_DATE` build args reach OCI labels, `/app/BUILD_INFO`, and the banner `entrypoint.sh` prints before any USDA work — so a boot-looping container still says which build it is. `deploy_truenas.sh` stamps them from git (with a `-dirty` suffix); a bare `docker compose build` yields `revision=unknown`, which is honest for a local build. Confirm a deployment with `docker exec <app> cat /app/BUILD_INFO` and check its `requirements_sha256` against `sha256sum requirements.txt` at the deployed commit. Never treat a tag as identity: `IMAGE_VERSION` is a constant `V1.0.0` and the TrueNAS YAML pulls `:latest`.
- `entrypoint.sh` runs with `set -e` and, on a fresh volume, downloads a pinned USDA CSV zip, rebuilds `usda_data.db`, runs `safe_upgrade.sh`, then `seed-usda-portions`, `seed-usda-categories`, `seed-exercise-activities`, `seed-dev-data`. Any step failing is a boot loop; `seed-usda-portions` re-runs on every start and deletes `was_imported` portions each time.
- `nginx/nginx.conf` sets no `client_max_body_size`, so uploads are capped at the 1 MiB default — relevant to the YAML food and recipe importers.
- `.dockerignore` does not exclude `.kilocode/` (58 MB) or `htmlcov/` (9.8 MB), so `COPY . .` bakes ~68 MB of editor state and coverage HTML into every image. Measured: the same commit builds to 418 MB from this checkout and 351 MB from a clean clone.

### Destructive scripts — read before running

- `seed_usda.sh:10` deletes `persistent/user_data.db` unconditionally and `:30` autogenerates a migration into tracked `migrations/versions/`. Do not run it in a working clone.
- `seed_db.sh:13` guards on `user_data.db` in the repo root, which never exists, so its reset branch silently does nothing and the subsequent upgrade runs against the live database.
- `safe_upgrade.sh` only backs up the hard-coded `persistent/user_data.db`, and only when the database is actually behind head — see Persistence and secrets for what that means for a fresh volume. With `DATABASE_URL` set elsewhere it migrates without a backup.
- `deploy_truenas.sh:20` does an unquoted `export $(cat .env | ...)`, which word-splits values containing spaces and exports every unrelated key in `.env`. Its closing `cat <<EOF` prints the generated TrueNAS custom-app YAML — **which is the deploy artifact itself, and its `SECRET_KEY`/`ENCRYPTION_KEY`/`MAIL_*` lines are load-bearing** (see Work Guidance: mail comes from the environment until the DB says otherwise), so removing the print breaks the copy-paste install. The real exposures are scrollback and CI logs, plus the fact that it emits `FLASK_DEBUG`, which no code reads. It also derives image names from the checkout directory name, so it only works from a directory called `opennourish`. Fix plan: `upgrade-research/PLAN.md` M6.3.

### Security

- There is **no global CSRF protection**: `CSRFProtect` is not registered, so only Flask-WTF forms carrying `hidden_tag()` are protected — measured 29 `hidden_tag()` calls against 98 `<form>` tags, in 20 of the 32 form-bearing templates. Close gaps by converting forms or registering `CSRFProtect`, never by hand-rolling tokens. **The suite cannot verify either state**: `tests/conftest.py:26` sets `WTF_CSRF_ENABLED = False`, so a green run proves nothing here and a CSRF-enabled test must be added alongside the fix. Mutating GETs (`/undo`, `onboarding.finish_onboarding`, `ensure_portion_sequence` reached from GET handlers) are outside CSRF protection by definition and must become POSTs; fix plan in `upgrade-research/PLAN.md` M6.1–M6.2.
- Cross-user reads require an accepted `Friendship`, and any write addressed by id must verify the row's owner is `current_user` (or that the row is legitimately orphaned). The historical violations — the unauthorised friend-diary/copy-meal read, the unguarded recipe label SVG, the ownership test that only rejected deleted owners (`search`), and `undo` restoring with a session-supplied `user_id` — are all closed and locked by tests. Keep the real idiom (plain ownership check plus the friendship rule); do not reintroduce the `... and not obj.user` predicate that only rejects deleted owners.
- `SEED_DEV_DATA=true` on an empty database creates an administrator named `markus` with password `1` (`opennourish/__init__.py:298-301`), and `.env.example` ships it set to `true`. Registration is open by default and, with `INITIAL_ADMIN_USERNAME` unset, the first registrant becomes admin. Never take this combination to a public host.
- `ENCRYPTION_KEY` guards only `MAIL_PASSWORD`; reset and verification tokens are signed with `SECRET_KEY`. Rotating either has user-visible consequences documented in `opennourish/admin/AGENTS.md` and `opennourish/auth/AGENTS.md`.

## Work Guidance

- Keep user data scoped by `user_id` in every query, and verify ownership for anything addressed by id.
- Do not commit `persistent/`, `htmlcov/`, `.coverage`, `project_snapshot.txt`, `.kilocode/`, `.vscode/`, or `__pycache__/` — all are ignored today; keep it that way.
- `DEV-README.md` and `README.md` drift from the code; trust this tree. Known mismatches: `DEV-README.md` `rm user_data.db` and the `typst/` directory requirement, `README.md:11-13` contradicting itself on where `usda_data/` lives, `README.md:113` naming a port compose never publishes, and `README.md:98` omitting that `ENCRYPTION_KEY` is mandatory. Fix the doc in the same change as the behaviour.
- `THIRD-PARTY-LICENSES.md` is generated by `gen_licenses.py`, not hand-maintained — never edit it by hand; change the lock or `static/`, then regenerate. Its `--check` mode is a gate below, so a lock bump that skips regeneration fails loudly instead of drifting silently for months.
- `DATABASE_URL`, `USDA_DATABASE_URL`, `FLASK_APP` are read but undocumented in `.env.example`; `FLASK_DEBUG` is documented and deployed into the TrueNAS YAML but read by no code. **`MAIL_CONFIG_SOURCE` is a database row, not an env var** — read via `get_setting_from_db` at `opennourish/__init__.py:76-79` and written only by the admin email-settings save (`opennourish/admin/routes.py:111-118`) — and its default is `environment`. So while `system_settings` holds no such row, the container's `MAIL_*` env vars *are* the live mail config; they go inert only once an admin saves mail settings in the UI. Check which mode a deployment is in by listing `system_settings` keys — as of 2026-09-23 the TrueNAS deployment is in **environment** mode (no such row; mail has never been saved in its admin UI), so its container `MAIL_*` variables are the live mail config. Correct `.env.example` when touching configuration.
- `.github/workflows/ci.yml` runs the four gates below on every push to `main`, every PR, and on demand — install `requirements.txt`, `pip check`, then the gates. It builds no image and boots nothing. There is still no pre-commit config and no active git hook, so a local commit is unverified until CI runs.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q     # full non-integration suite
$P -m ruff check .                        # lint gate
$P -m ruff format --check .               # formatting gate
$P gen_licenses.py --check                # licence inventory matches the lock and static/
```

`gen_licenses.py --check` reads the installed environment, so it also proves the env matches `requirements.txt`: any pin missing or at a different version, or any file under `static/` replaced, fails it. Regenerate with `$P gen_licenses.py`.

**The suite needs `typst` on PATH.** 17 label tests shell out to it and fail `500 == 200` without it — that is the first thing a bare runner hits. CI downloads the same build the Dockerfile does and installs `fonts-liberation`, because `opennourish/typst_utils.py` pins `Liberation Sans`.

Template linting (`$P -m djlint templates --profile jinja --extension html --use-gitignore`) is advisory, not one of the gates above — see Toolchain for why it is not clean yet.

The two ruff gates are only meaningful together with `ruff.toml`: `select` freezes the rule families this tree is clean under (newer ruff defaults would report ~372 findings) and `exclude = ["*.md"]` keeps ruff ≥0.16 out of Markdown code fences. Treat both keys as part of the gate contract, not as configuration taste.

Coverage and the single `integration` test (needs `persistent/usda_data/*.csv`) are covered in `tests/AGENTS.md`.

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- **Keep the Python toolchain to miniconda + pip; uv is overkill here** (owner decision 2026-09-23). The resolver is `pip-compile`, chosen over plain `pip --report` only because the lock's `# via` annotations earn the one extra dev package. Do not add tooling that only re-does what pip does, and do not re-open the runtime/dev dependency split — both were considered and declined the same day.
- The owner does not weight licence tidiness highly (their words). Copyleft djlint in the distributed image is therefore accepted, and licensing arguments alone will not justify a structural change. State a behaviour, size, or legal-risk consequence or drop the proposal.

## Child DOX Index

- `opennourish/AGENTS.md` — Flask app factory, blueprint registry, shared services, cross-cutting authorization/timezone/nutrition rules.
  - `opennourish/search/AGENTS.md`, `recipes/`, `my_foods/`, `diary/`, `dashboard/`, `tracking/`, `goals/`, `admin/`, `auth/` — one per feature blueprint with its own contracts.
- `templates/AGENTS.md` — Jinja inheritance, base blocks, Chart.js conventions, flash/CSRF patterns, the analytics duplication.
- `tests/AGENTS.md` — pytest fixtures, markers, coverage commands, current gate.
- `migrations/AGENTS.md` — Alembic history for the default bind, SQLite batch-mode rules, backup-first upgrade.
- Root keeps direct ownership of `models.py`, `config.py`, `constants.py`, `app.py`, `serve.py`, `import_usda_data.py`, `alembic.ini`, the ops shell scripts, `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`, `nginx/`, `static/`, `requirements.in`, `requirements.txt`, `gen_licenses.py`, and `.github/workflows/ci.yml`.
- `upgrade-research/` — dependency/interpreter migration material, root-owned. `README.md` is the 2026-09-23 audit (its baseline figures describe the **pre-move** state) and `PLAN.md` is the live sequenced plan with current status. M0–M2, M2b, M3, M4's CI step and deployment provenance landed 2026-09-23: env and Dockerfile on 3.12, `requirements.txt` generated from `requirements.in` (54 packages after M3 dropped the mail chain), Flask-Mailing at 3.0.0 with the `create_app` init guard, the image's `typst` at 0.15.1 with label output verified pixel-identical, and the image deployed to TrueNAS with `BUILD_INFO` proving the running revision. M2's cold-volume boot was verified on a fresh checkout: the full `entrypoint.sh` path (USDA download, `usda_data.db` rebuild, migrations, all four seed steps) ran clean under 3.12. Pending: M5 and M6 — security hardening (CSRFProtect, mutating GETs, deploy secrets, the seed-admin default), opened 2026-09-23 now that the upgrade track is closed; M4's runtime/dev split was dropped the same day, so copyleft djlint in the image is accepted state. The lock's resolver moved from uv to `pip-compile --strip-extras` on 2026-09-23 (identical 54 pins; the reasons and the two traps are recorded in PLAN.md and DEV-README). M3's live SMTP round-trip was performed on the TrueNAS deployment the same day: a password-reset email arrived from the 3.0.0 image, which also proves the suppression bridge in the field — a mis-bridged `SUPPRESS_SEND` would have dropped the send silently.
- Blueprints without their own doc (onboarding, main, friends, profile, settings, exercise, fasting, undo, usda_admin) are governed by `opennourish/AGENTS.md`, except `usda_admin`, governed by `opennourish/admin/AGENTS.md`.
