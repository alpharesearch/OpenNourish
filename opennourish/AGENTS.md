# opennourish — Flask application layer

## Purpose

The Flask app factory, the 18 feature blueprints, and the shared service helpers every blueprint calls.

## Ownership

- `__init__.py` — `create_app()` spans L53-1448 and does configuration, DB-backed mail setup, ProxyFix, `CSRFProtect`, login manager, template-filter registration, blueprint registration (L229-297), error handlers, and the Flask CLI seed/admin commands nested inside it. Growing this function further is the default failure mode; extract before adding.
- One package per feature: `__init__.py` (Blueprint object), `routes.py`, optional `forms.py`.
- Shared services: `utils.py` (nutrition, portions, unit conversion, BMR, encryption helpers, and the two client-input validators `same_host_redirect_url` / `portion_matches_item`), `typst_utils.py` (nutrition-label PDF/SVG via the `typst` binary), `time_utils.py` (timezone helpers, the naive-UTC `utcnow_naive()`, the `user_today_default()` form default, Jinja filters), `decorators.py`, `context_processors.py`.
- Not owned here: ORM models (`/models.py`), runtime config (`/config.py`), shared enums and USDA nutrient ids (`/constants.py`) — root AGENTS.md owns those; markup lives in `/templates/AGENTS.md`.

## Local Contracts

Blueprint registry — prefixes are applied at registration in `__init__.py:229-297`, except where the Blueprint constructor already declares one:

| package | exported object | effective prefix | notes |
|---|---|---|---|
| auth | `auth_bp` | `/auth` | |
| onboarding | `onboarding_bp` | `/onboarding` | |
| dashboard | `dashboard_bp` | `/dashboard` | owns `/<string:log_date_str>` |
| my_foods | `my_foods_bp` | `/my_foods` | object exported from both `__init__.py` and `routes.py` |
| diary | `diary_bp` | `/` | routes are `/diary/...`, `/my_meals/...` |
| goals | `bp` | `/goals` | only package exporting a bare `bp` |
| recipes | `recipes_bp` | `/recipes` | constructor also sets `template_folder="templates"` |
| settings | `settings_bp` | `/settings` | prefix declared in `__init__.py` |
| tracking | `tracking_bp` | `/tracking` | |
| exercise | `exercise_bp` | `/exercise` | `__init__.py` also registers `flask exercise seed-activities` |
| main | `main_bp` | (none) | `routes.py` |
| search | `search_bp` | `/search` | |
| friends | `friends_bp` | `/friends` | |
| profile | `profile_bp` | `/user` | prefix declared in `__init__.py` |
| admin | `admin_bp` | `/admin` | prefix and `template_folder` in the constructor |
| usda_admin | `usda_admin_bp` | (none) | |
| fasting | `fasting_bp` | `/fasting` | |
| undo | `undo_bp` | (none) | `/undo` only |

- The `template_folder="templates"` on admin, fasting, friends, and recipes points at directories that do not exist inside those packages; every template actually resolves from the app-level `templates/` directory. Do not add a fifth variant — new templates go in `/templates/<feature>/`.
- Parent owns the blueprints without a child doc: onboarding, main, friends, profile, settings, exercise, fasting, undo, usda_admin.
- Authorization is layered and all three layers are required where they apply: `@login_required`, then `@admin_required` / `@key_user_required` / `@onboarding_required` (`decorators.py`), then an ownership check in the body.
- Ownership idiom: `obj = db.session.get(Model, id)`, then `if not obj or obj.user_id != current_user.id: flash(...); return redirect(...)`. Never trust an id coming from a form or URL path.
- **Two client-supplied values are validated in `utils.py`, not at each route.** `same_host_redirect_url()` / `same_host_referrer()` gate every `redirect()` target — a hidden `return_url` field and the `Referer` header are attacker-chosen, and the app must not 302 a logged-in browser to somebody else's host; they return `None` so every caller keeps its own `url_for(...)` fallback and the redirect itself (scroll position, meal anchor) survives. `portion_matches_item(portion, item)` gates every write of `portion_id_fk` — the posted portion decides what `amount_grams` is multiplied by, so accepting one from another item lets the client set a row's nutrition and its displayed serving. Compare against the row's own `fdc_id` / `my_food_id` / `recipe_id`; both helpers abstain (`True`) on an absent or unsaved portion so the caller's existing "no portion" message still fires.
- **`CSRFProtect` is registered, so every non-GET request must carry a valid Flask-WTF token.** That registration is also what binds the `csrf_token` / `csrf_meta_tag` Jinja globals; the hand-binding of `flask_wtf.csrf.generate_csrf` that preceded it existed only so forms could carry tokens before the gate did. Two settings are load-bearing: `WTF_CSRF_TIME_LIMIT = None` in `config.py` (the 3600 s default would 400 a recipe form somebody opened hours earlier) and `WTF_CSRF_SSL_STRICT` left at True, which holds only because `nginx.conf` sends no `Referrer-Policy`. The token is read from form fields and the `X-CSRFToken` / `X-CSRF-Token` headers and **never from a JSON body**, which is why the timezone probe in `templates/base.html` sends a header. `tests/conftest.py` disables the hook, so `tests/test_csrf.py` — which builds its own app — is the only place enforcement is observable. Exempting a route, or minting a token of our own, is not an option.
- **Portion order is a read-side concern.** Every listing of `portions` — the three `portions` relationships in `models.py` and `/search/api/get-portions/` — orders `seq_num ASC NULLS LAST, gram_weight ASC`. That tie-break is the same rule `ensure_portion_sequence` writes, which is why a read no longer has to repair anything: an unsequenced portion already displays where repairing it would put it. `seq_num` is display order only — nutrition comes from `gram_weight` — so never make a new reader depend on it being non-NULL, and never put a repair call in a GET handler (`tests/test_portion_sequence.py` enforces both).
- Any route that resolves **another** user by username must verify an accepted `Friendship` before reading or writing their rows. The canonical block is `diary/routes.py:879-899` (`copy_meal_from_friend`), mirrored by `profile/routes.py:36-51`. A bare `User.query.filter_by(username=...)` followed by a `DailyLog` query on that user is an authorization hole.
- **Time is user-local, and the whole `DTZ` ruff family now enforces it** (2026-09-26, PLAN.md M5). Use `time_utils.get_user_today(user.timezone)` for "today" and `get_start_of_week(today, user.week_start_day)` for week boundaries — `User.week_start_day` is honoured by `dashboard`, `exercise` and the `friends` scoreboard, and nowhere else. A form that pre-fills a date uses `time_utils.user_today_default()` (its no-request fallback is UTC, so a script can build a form). A submitted calendar date is `date.fromisoformat(s)`, never `datetime.strptime(s, "%Y-%m-%d").date()`. `date.today()` is server-local and correct in exactly two places: CLI seeders (the three `# noqa: DTZ011` in `opennourish/__init__.py`) and tests. Timestamps that are *not* clocks — the YAML export names and the nutrition-label file stamps — use `utcnow_naive()`, which needs no viewer. Ruff cannot see a `default=date.today` **reference** (only calls), so the form rule above is a contract, not a lint.
- **Stored instants are naive UTC, and `time_utils.utcnow_naive()` is the only way to get one.** Every `db.DateTime` column here stores naive UTC, and SQLite drops `tzinfo` on the way in (measured on SQLAlchemy 2.0.54: even a `DateTime(timezone=True)` column reads back naive), so an aware `datetime.now(timezone.utc)` compared with a loaded row raises `TypeError: can't subtract offset-naive and offset-aware datetimes` — `fasting/fasting.html` and `dashboard.html` both compute `now - active_fast.start_time`, so an aware `now` is a 500 on both pages. Ruff pins `DTZ003`, which bans the deprecated `datetime.utcnow()` outright. `models.py` keeps a private twin (`_utcnow_naive`) because `opennourish/__init__.py:4` imports `models` at module level and the import would be circular. Keep `datetime.now(timezone.utc)` only where both sides are aware, e.g. `fasting/routes.py:114`.
- Endpoint names come from `/constants.py` (`DASHBOARD_INDEX_ROUTE`, `TRACKING_PROGRESS_ENDPOINT`, `MAIN_FOOD_DETAIL_ENDPOINT`, `FRIENDS_PAGE_ENDPOINT`, `PORTIONS_TABLE_ANCHOR`, `USERS_ID`, `USDA_PORTION_NOT_FOUND_MSG`). Import them; do not hardcode `"dashboard.index"` strings.
- Meal structure is derived from `constants.MEAL_CONFIG` keyed by `User.meals_per_day` (3, 4, 6, 7) with `DEFAULT_MEAL_NAMES = MEAL_CONFIG[6]`, including the `Water` and `Unspecified` pseudo-meals. Never inline a meal list.
- Nutrition math lives only in `utils.py` (`calculate_nutrition_for_items`, `get_meal_based_nutrition`, `calculate_intake_vs_goal_deviation`, `calculate_weight_projection`, `calculate_weekly_nutrition_summary`) against `constants.CORE_NUTRIENT_IDS`. Reimplementing macro arithmetic in a route forks the definition of a calorie.
- Cross-bind rule: `foods`, `nutrients`, `food_nutrients` live on the `usda` bind, everything user-owned on the default bind. Reach across only through the `foreign(...)` viewonly relationships or by loading ids in Python; a SQL join across binds is invalid here.
- `context_processors.py:inject_global_vars` is the only place global template variables may be defined; register new ones there rather than repeating them in 40 `render_template` calls.
- **Typst label text is escaped by context, and the two escapers are not interchangeable.** `typst_utils.py` builds its document by interpolating user text (food/recipe name, description, ingredients, instructions, portion descriptions) into a template, so every interpolation must pick a context: `_escape_typst_markup` for markup (`= <name>` headings, the `== Ingredients:` / `== Portion Sizes:` / `== Instructions:` bodies) and `_escape_typst_string` for text inside a Typst `"…"` string literal (`serving_size`, the `#ean13` UPC). Escaping markup specials *inside a string* is a bug, not a defence — `"a\*b"` prints the backslash — and leaving `$ # @ < ` ]` unescaped in markup is a compile error, which surfaces as a 500 label route. `TYPST_MARKUP_SPECIALS` is `\` plus `*_$#<>@\`[]%`, measured on typst 0.15.1; `\` is escaped first, and straight quotes and `--` are deliberately left for Typst's smart typography, which is what the USDA labels have always rendered. Escape **each list item**, never a string already joined with the `"\\ "` separator — that separator is markup and escaping the joined text doubles its backslash. `Recipe.servings` is a Float column, so it needs no escaping. New interpolations must choose an escaper; see `upgrade-research/PLAN.md` M5 and `tests/test_typst_coverage.py`'s `MARKUP_HAZARDS`.
- **The `@preview` imports in `typst_utils.py` are a build input.** The `Dockerfile` greps this file for `@preview/<name>:<version>` to decide which Typst packages to vendor into the image's `TYPST_PACKAGE_CACHE_PATH`, so changing one here is a deployment change that needs a rebuild — and if the templates ever move out of this file, that grep matches nothing and the build fails its non-empty guard rather than silently shipping an image whose labels need egress (root AGENTS.md owns the vendoring step). The `subprocess.run` calls deliberately pass no `--root`, which is what confines a template's `#read` to the temp directory.
- **Mail init is conditional and its key names matter.** `create_app` bridges `MAIL_SUPPRESS_SEND` → `SUPPRESS_SEND` — Flask-Mailing 3.x reads only the second name, while the environment, the `system_settings` rows and the `app.testing` override all speak the first, so without the bridge every suppressed context (the whole test suite included) starts opening real SMTP connections. It then calls `mail.init_app(app)` only when `MAIL_SERVER` is non-empty, because 3.x raises `ValueError` on an empty server/username/password and a deployment with mail unconfigured must still boot. A server without credentials gets `NO_MAIL_CREDENTIAL` for whichever is missing, restored to `""` the moment `init_app` has copied it, so no other reader sees a fake value; `USE_CREDENTIALS = False` is what keeps it off the wire. Probe readiness with `"mailing" in app.extensions`. `mail` is a module-level singleton, so a skipped init leaves the previously initialised app's connection config in place — one app per process in production, but a trap in tests. Sends stay `asyncio.run(mail.send_message(msg))` in `utils.py` (`send_message` is still `async def` in 3.x): do not sync it, and do not add an early-out before the call — `tests/test_email_verification.py` asserts on that call.

## Work Guidance

Inherited defects in the code you are working around — fix them where you touch them, never imitate them:

- **Mutating routes are POST-only.** `/undo` and `/onboarding/finish_onboarding` were `methods=["GET"]` until 2026-09-26 and are now POST (`tests/test_undo.py::test_undo_rejects_get`, `tests/test_onboarding_coverage.py::test_finish_onboarding_rejects_get`); the Undo affordance is a tokenised form inside the flash message, not a link. This matters because `CSRFProtect` guards non-GET methods only, so a write reachable by GET stays exploitable whatever the token check does. The remaining GET writers are listed in the next bullet.
- **Two GET handlers still write.** `diary.routes` inserts the Water food and its thirteen portions while rendering, and `search.search` commits a generated 1 g portion per USDA food it displays. `auth.verify_email` commits on GET legitimately — a mail client cannot POST. The five `ensure_portion_sequence` calls that used to sit in GET handlers are gone (2026-09-26, PLAN.md M6.2): the numbers are now maintained by `flask repair-portion-sequence` and, where a swap genuinely needs them, by the POST that asked for the swap. Do not put them back.
- **`calculate_nutrition_for_items` conflates `item.recipe_id` (`utils.py:517`).** On `DailyLog`/`MyMealItem` that column *is* the referenced recipe, but on `RecipeIngredient` it is the non-null parent FK — the linked recipe lives in `recipe_id_link`. Since the function is called with both model kinds (rollups pass ingredients, diary passes logs), every nested-recipe ingredient hits the circular-dependency guard and contributes 0 to recipe nutrition and label per-ingredient numbers (visible as "Circular recipe dependency detected" warnings); diary-logged recipes meanwhile roll up live. Dispatch on model type (use `recipe_id_link` for `RecipeIngredient`), and update the tests that currently pin the zero-contribution and double-count symptoms.
- Two divergent default exercise-activity seed lists exist: `exercise/__init__.py:8-41` (15 activities) and `opennourish/__init__.py:257-276` (6, different MET values). Pick one before seeding anywhere else.

Structural work:
- `search/routes.py` `add_item` is ~850 lines (L592) handling diary add, recipe ingredient, meal item, copy-meal, friend copy, rematch, and portion creation. Split along those seams before adding behaviour to it; do not extend it further.
- Batch work: `calculate_nutrition_for_items` already groups USDA lookups into one query. Fetching `Food`, `FoodNutrient`, `UnifiedPortion`, or `MyFood` with `db.session.get` inside a per-log loop turns a 30-day page into hundreds of queries — hoist the ids and query once.
- Keep the timezone, meal, portion, and nutrient invariants above intact when refactoring; they are the reason route handlers are long.
- Longest handlers today, in order to shorten first: `search/routes.py:592 add_item` (~850L), `recipes/routes.py:79 _process_recipe_yaml_import` (~313L), `recipes/routes.py:682 edit_recipe` (~221L), `dashboard/routes.py:39 index` (~236L), `diary/routes.py:88 diary` (~231L).
- CLI commands belong nested in `create_app` only until the next extraction; `exercise` shows the alternative (`exercise_bp.cli.command`).

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m ruff check .                                    # must stay clean
$P -m ruff format --check .                           # no files listed
$P -m pytest -m "not integration" -q tests/test_app.py tests/test_utils.py
```

Route-level behaviour is verified through `/tests/AGENTS.md`; run the full suite before handing off.

## Child DOX Index

- `search/AGENTS.md` — search, UPC lookup, `add_item`, portions API.
- `recipes/AGENTS.md` — recipe CRUD, ingredient nutrition rollup, YAML import/export and rematch.
- `my_foods/AGENTS.md` — user food CRUD, categories, YAML/CSV import-export.
- `diary/AGENTS.md` — daily logging, meals, move/copy, friend meal copy.
- `dashboard/AGENTS.md` — dashboard aggregation and its analytics inputs.
- `tracking/AGENTS.md` — check-ins, progress charts, and the `analytics.py` module.
- `goals/AGENTS.md` — goal math, diet presets, BMI and BMR.
- `admin/AGENTS.md` — admin and USDA-admin privileges.
- `auth/AGENTS.md` — registration, login, verification, password reset, and onboarding gate.
