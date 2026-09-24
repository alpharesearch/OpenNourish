# tests — verification layer

## Purpose

The pytest suite is the broadest of this repository's four gates and the only one that exercises behaviour. It covers every registered blueprint plus the shared service layer.

## Ownership

- `conftest.py` — the single app-factory fixture and the login helpers every test reuses.
- 72 test files, 983 non-integration tests + 1 integration test (984 collected). 16 of them are the `test_*_coverage.py` files raised for the 99% TOTAL pass; each mirrors a feature module and is named for it.
- `pytest.ini` (repo root) — declares the `integration` marker only; no `addopts`, no `testpaths`.
- `.coveragerc` (repo root) — `exclude_also` patterns only.
- Not owned here: what each feature must do (feature AGENTS.md files), and the workflow file itself (`.github/workflows/ci.yml`, root-owned — it runs the commands below on every push and PR).

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
- **20 tests need the `typst` binary on PATH**: `test_utils.py` (6), `test_typst_coverage.py` (9), `test_recipes_coverage.py` (4), `test_recipe_label.py` (1). They shell out to it, and a missing binary surfaces as `500 == 200`, not a skip — so a machine without `typst` reports failures that are not the code's fault. Three of the `test_typst_coverage.py` ones are the `renders_markup_hazards` regressions, which are the only tests that prove the label escapers produce compilable Typst: the rest assert on the generated source, not on the render. `test_my_foods_coverage.py` mentions typst but patches it. CI installs the Dockerfile's build plus `fonts-liberation`, which the templates need (`opennourish/typst_utils.py` pins Liberation Sans); the font affects the rendered label, not these assertions.
- The `integration` marker gates exactly one test, `test_database_import.py:40`, which shells out to bare `python import_usda_data.py` and needs `persistent/usda_data/*.csv`. It does not skip when the CSVs are absent, so always run `-m "not integration"` as the default command.
- Coverage runs line coverage only (`.coveragerc` has no `[run]` section, so no `source`, no `branch`, no `omit`). `test_config.py` imports generated temp modules, so `"/tmp/*"` must be in the omit list or TOTAL is polluted.
- An assertion on `status_code == 200` with `follow_redirects=True` also passes when `@onboarding_required` bounces the request. Assert on rendered content, not just the status.
- Do not add English month or weekday names to HTML assertions unless the format string itself is the contract (current exception: `test_dashboard.py:199`).
- Patch session/`db` methods on the **class**, not the instance: `monkeypatch.setattr(db.session, "commit", …)` restores on undo by writing the old bound method back as an **instance** attribute, which then permanently shadows any later `scoped_session.commit` (class-level) patch in a test that shares the app. Use `monkeypatch.setattr("sqlalchemy.orm.scoping.scoped_session.commit", …)` (see `test_search.py::test_add_item_exception`).
- `app_with_db` yields **inside** an `app_context`, so Flask-Login's cached `g._login_user` survives across requests within one test; switching identity via `session_transaction()` alone silently keeps the first user. Pop `g._login_user` (or use a fresh client) to truly switch mid-test.

## Work Guidance

- New route → new or extended test file named after the feature area; keep the existing grouping (search, recipes, my_foods, diary, meals, goals, tracking/analytics, exercise, fasting, friends, profile, admin, usda_admin, undo, settings, auth, cli, config, models, utils, time_utils).
- Reuse the `conftest.py` fixtures. Hand-rolled `session_transaction` `_user_id` login is duplicated in 25 files and `POST /auth/login` in 11 (a few of those — `test_auth*.py` — are testing the login route itself and stay); when touching one of the others, move it onto a fixture instead of adding a copy.
- Cross-user authorisation must be tested both ways (owner succeeds, non-owner is rejected) using `auth_client_two_users` or `auth_client_with_friendship`.
- Format with `python -m ruff format .` and lint with `python -m ruff check .`; both are gates, so CI enforces them on the pushed commit even though nothing runs locally at commit time.
- CI (`.github/workflows/ci.yml`) runs the commands below, minus coverage, on every push to `main` and every PR. There is still no pre-commit config and no active git hook, so a local commit is unverified until you push. djlint stays out of CI deliberately — see the root AGENTS.md.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q                    # expect 0 failures
$P -m ruff check .                                      # expect "All checks passed!"
$P -m ruff format --check .                             # expect no files listed
$P -m coverage run -m pytest -m "not integration" && \
  $P -m coverage report --skip-covered --omit="test*","/tmp/*"   # TOTAL is 99%
```

Coverage TOTAL is **99%** (6113 statements, 43 misses); 53 modules are at 100%. The only files with any misses are: `exercise/routes.py` 85%, `goals/routes.py` 98%, `my_foods/routes.py` 99%, `recipes/routes.py` 99%, `search/routes.py` 97%, `utils.py` 99%. The `search`/`my_foods`/`recipes`/`utils` remainders are documented as dead or unreachable (duplicate-int guards, an unreachable `continue`, `PortionForm`-prevented validators, identity-map branches); `exercise` is the only lane where new tests would still move TOTAL.

## Child DOX Index

No child docs. Test coverage rules for a specific feature belong in that feature's own AGENTS.md.
