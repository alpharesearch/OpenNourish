# tests — verification layer

## Purpose

The pytest suite is the only automated quality gate in this repository. It covers every registered blueprint plus the shared service layer.

## Ownership

- `conftest.py` — the single app-factory fixture and the login helpers every test reuses.
- 57 test files, 443 non-integration tests + 1 integration test (444 collected).
- `pytest.ini` (repo root) — declares the `integration` marker only; no `addopts`, no `testpaths`.
- `.coveragerc` (repo root) — `exclude_also` patterns only.
- Not owned here: what each feature must do (feature AGENTS.md files), the CI question (no CI exists; see Work Guidance).

## Local Contracts

- Interpreter: run everything with `/home/markus/miniconda3/envs/opennourish/bin/python`. The conda `base` env has no Flask, so bare `python -m pytest` fails at import.
- One app factory only: `create_app(test_config)` (`conftest.py:14` `app_with_db`). Both binds are in-memory SQLite and the schema comes from `db.create_all()`, never from migrations. Schema changes therefore need a migration separately (`/migrations/AGENTS.md`).
- `SERVER_NAME="localhost.localdomain:5000"` is set for the test app, so requests must go through the Flask test client.
- Login fixtures inject the session directly (`conftest.py:78-80`), they do not POST to `/auth/login`.
  - `auth_client` user is **not** `is_verified`, so verified-only behaviour is unreachable through it.
  - `auth_client_onboarded` is required for any route behind `@onboarding_required` (dashboard, diary). Using `auth_client` there silently asserts against the onboarding page.
  - `admin_client` yields `(client, user, app)`, `auth_client_with_user` and `auth_client_two_users` yield tuples, the rest yield a bare client. Match the shape when reusing.
  - `auth_client_with_friendship` is the fixture for cross-user authorisation tests; `sample_usda_food` pins `fdc_id=12345`.
- Mail is patched globally at `conftest.py:49` (`flask_mailing.Mail.send_message`). Email-behaviour tests patch `opennourish.utils.mail.send_message` instead — pick the patch point that matches the assertion.
- The `integration` marker gates exactly one test, `test_database_import.py:40`, which shells out to bare `python import_usda_data.py` and needs `persistent/usda_data/*.csv`. It does not skip when the CSVs are absent, so always run `-m "not integration"` as the default command.
- Coverage runs line coverage only (`.coveragerc` has no `[run]` section, so no `source`, no `branch`, no `omit`). `test_config.py` imports generated temp modules, so `"/tmp/*"` must be in the omit list or TOTAL is polluted.
- An assertion on `status_code == 200` with `follow_redirects=True` also passes when `@onboarding_required` bounces the request. Assert on rendered content, not just the status.
- Do not add English month or weekday names to HTML assertions unless the format string itself is the contract (current exception: `test_dashboard.py:199`).

## Work Guidance

- New route → new or extended test file named after the feature area; keep the existing grouping (search, recipes, my_foods, diary, meals, goals, tracking/analytics, exercise, fasting, friends, profile, admin, usda_admin, undo, settings, auth, cli, config, models, utils, time_utils).
- Reuse the `conftest.py` fixtures. Hand-rolled `session_transaction` login is currently duplicated in 24 files and raw `POST /auth/login` in 12 more; when touching one of those files, move it onto a fixture instead of adding a seventh copy.
- Cross-user authorisation must be tested both ways (owner succeeds, non-owner is rejected) using `auth_client_two_users` or `auth_client_with_friendship`.
- Format with `python -m ruff format .` and lint with `python -m ruff check .`; both are local-only checks, nothing enforces them.
- There is no CI, no pre-commit config, and no active git hooks. Green means you ran the commands below yourself.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q                    # expect 0 failures
$P -m ruff check .                                      # expect "All checks passed!"
$P -m ruff format --check .                             # expect no files listed
$P -m coverage run -m pytest -m "not integration" && \
  $P -m coverage report --skip-covered --omit="test*","/tmp/*"   # TOTAL was 87%
```

Lowest-covered real modules, i.e. where new tests are worth the most: `opennourish/typst_utils.py` 74%, `opennourish/search/routes.py` 76%, `opennourish/onboarding/routes.py` 77%, `opennourish/profile/routes.py` 78%, `opennourish/diary/routes.py` 81%, `opennourish/recipes/routes.py` 82%.

## Child DOX Index

No child docs. Test coverage rules for a specific feature belong in that feature's own AGENTS.md.
