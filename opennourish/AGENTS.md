# opennourish — Flask application layer

## Purpose

The Flask app factory, the 18 feature blueprints, and the shared service helpers every blueprint calls.

## Ownership

- `__init__.py` — `create_app()` spans L45-1325 and does configuration, DB-backed mail setup, ProxyFix, login manager, template-filter registration, blueprint registration (L164-234), error handlers, and the Flask CLI seed/admin commands nested inside it. Growing this function further is the default failure mode; extract before adding.
- One package per feature: `__init__.py` (Blueprint object), `routes.py`, optional `forms.py`.
- Shared services: `utils.py` (nutrition, portions, unit conversion, BMR, encryption helpers), `typst_utils.py` (nutrition-label PDF/SVG via the `typst` binary), `time_utils.py` (timezone helpers + Jinja filters), `decorators.py`, `context_processors.py`.
- Not owned here: ORM models (`/models.py`), runtime config (`/config.py`), shared enums and USDA nutrient ids (`/constants.py`) — root AGENTS.md owns those; markup lives in `/templates/AGENTS.md`.

## Local Contracts

Blueprint registry — prefixes are applied at registration in `__init__.py:164-234`, except where the Blueprint constructor already declares one:

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
- Any route that resolves **another** user by username must verify an accepted `Friendship` before reading or writing their rows. The canonical block is `diary/routes.py:836-852` (`copy_meal_from_friend`), mirrored by `profile/routes.py:36-51`. A bare `User.query.filter_by(username=...)` followed by a `DailyLog` query on that user is an authorization hole.
- Time is user-local. Use `time_utils.get_user_today(current_user.timezone)` for "today" and `get_start_of_week(...)` for week boundaries; render timestamps with the registered `user_date` / `user_time` filters. `date.today()` is server-timezone and only acceptable in CLI seeders; every call site on a request path is a bug.
- Endpoint names come from `/constants.py` (`DASHBOARD_INDEX_ROUTE`, `TRACKING_PROGRESS_ENDPOINT`, `MAIN_FOOD_DETAIL_ENDPOINT`, `FRIENDS_PAGE_ENDPOINT`, `PORTIONS_TABLE_ANCHOR`, `USERS_ID`, `USDA_PORTION_NOT_FOUND_MSG`). Import them; do not hardcode `"dashboard.index"` strings.
- Meal structure is derived from `constants.MEAL_CONFIG` keyed by `User.meals_per_day` (3, 4, 6, 7) with `DEFAULT_MEAL_NAMES = MEAL_CONFIG[6]`, including the `Water` and `Unspecified` pseudo-meals. Never inline a meal list.
- Nutrition math lives only in `utils.py` (`calculate_nutrition_for_items`, `get_meal_based_nutrition`, `calculate_intake_vs_goal_deviation`, `calculate_weight_projection`, `calculate_weekly_nutrition_summary`) against `constants.CORE_NUTRIENT_IDS`. Reimplementing macro arithmetic in a route forks the definition of a calorie.
- Cross-bind rule: `foods`, `nutrients`, `food_nutrients` live on the `usda` bind, everything user-owned on the default bind. Reach across only through the `foreign(...)` viewonly relationships or by loading ids in Python; a SQL join across binds is invalid here.
- `context_processors.py:inject_global_vars` is the only place global template variables may be defined; register new ones there rather than repeating them in 40 `render_template` calls.
- **Mail init is conditional and its key names matter.** `create_app` bridges `MAIL_SUPPRESS_SEND` → `SUPPRESS_SEND` — Flask-Mailing 3.x reads only the second name, while the environment, the `system_settings` rows and the `app.testing` override all speak the first, so without the bridge every suppressed context (the whole test suite included) starts opening real SMTP connections. It then calls `mail.init_app(app)` only when `MAIL_SERVER` is non-empty, because 3.x raises `ValueError` on an empty server/username/password and a deployment with mail unconfigured must still boot. A server without credentials gets `NO_MAIL_CREDENTIAL` for whichever is missing, restored to `""` the moment `init_app` has copied it, so no other reader sees a fake value; `USE_CREDENTIALS = False` is what keeps it off the wire. Probe readiness with `"mailing" in app.extensions`. `mail` is a module-level singleton, so a skipped init leaves the previously initialised app's connection config in place — one app per process in production, but a trap in tests. Sends stay `asyncio.run(mail.send_message(msg))` in `utils.py` (`send_message` is still `async def` in 3.x): do not sync it, and do not add an early-out before the call — `tests/test_email_verification.py` asserts on that call.

## Work Guidance

Inherited defects in the code you are working around — fix them where you touch them, never imitate them:

- **`portion_id` is still unvalidated against the item's parent in the diary paths.** `recipes/routes.py` (`portion_owns_ingredient`) and `search/routes.py` (`add_item` portion-ownership guard) now verify the portion belongs to the item being written, but the diary add/edit paths read a form-supplied `portion_id` (`diary/routes.py:411`, `:560`) and attach it to a `DailyLog` row with no parent check. Validate parentage (and ownership) before assigning `portion_id_fk`.
- **`search/routes.py` `add_item` redirects to an unvalidated `return_url`/`request.referrer`** at ~9 exit points — an open redirect. Validate it resolves same-host before `redirect()`; callers depend on the value for scroll position and meal anchor, so fix the validation, do not drop the redirect.
- **GET requests write to the database.** `ensure_portion_sequence` commits and is called from GET handlers (`main/routes.py:52`, `search/routes.py` result assembly, `recipes/routes.py`, `my_foods/routes.py:438`); `diary.routes` inserts the Water food and its portions while rendering; `search.search` commits per generated portion; `onboarding.finish_onboarding` and `undo` are mutating GETs with no CSRF. Do not add further writes to GET handlers.
- **`ensure_portion_sequence` destroys curated order**: if any portion of an item has NULL `seq_num` it renumbers *all* of them by `gram_weight` (`utils.py`), silently overwriting the order a key user built with the USDA move routes. Assign `seq_num` at creation instead of relying on the backfill.
- **`calculate_nutrition_for_items` conflates `item.recipe_id` (`utils.py:517`).** On `DailyLog`/`MyMealItem` that column *is* the referenced recipe, but on `RecipeIngredient` it is the non-null parent FK — the linked recipe lives in `recipe_id_link`. Since the function is called with both model kinds (rollups pass ingredients, diary passes logs), every nested-recipe ingredient hits the circular-dependency guard and contributes 0 to recipe nutrition and label per-ingredient numbers (visible as "Circular recipe dependency detected" warnings); diary-logged recipes meanwhile roll up live. Dispatch on model type (use `recipe_id_link` for `RecipeIngredient`), and update the tests that currently pin the zero-contribution and double-count symptoms.
- Two divergent default exercise-activity seed lists exist: `exercise/__init__.py:8-41` (15 activities) and `opennourish/__init__.py:257-276` (6, different MET values). Pick one before seeding anywhere else.

Structural work:
- `search/routes.py` `add_item` is ~850 lines (L596) handling diary add, recipe ingredient, meal item, copy-meal, friend copy, rematch, and portion creation. Split along those seams before adding behaviour to it; do not extend it further.
- Batch work: `calculate_nutrition_for_items` already groups USDA lookups into one query. Fetching `Food`, `FoodNutrient`, `UnifiedPortion`, or `MyFood` with `db.session.get` inside a per-log loop turns a 30-day page into hundreds of queries — hoist the ids and query once.
- Keep the timezone, meal, portion, and nutrient invariants above intact when refactoring; they are the reason route handlers are long.
- Longest handlers today, in order to shorten first: `search/routes.py:596 add_item` (~850L), `recipes/routes.py:79 _process_recipe_yaml_import` (~313L), `recipes/routes.py:682 edit_recipe` (~221L), `dashboard/routes.py:39 index` (~236L), `diary/routes.py:88 diary` (~231L).
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
