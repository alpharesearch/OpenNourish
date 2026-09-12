# opennourish/tracking — check-ins, progress, and analytics

## Purpose

Body-composition check-ins, the progress page with its history chart, and the analytics module that derives multi-week trends from diary, exercise, and check-in data.

## Ownership

- `routes.py` (206 lines, 4 routes): `progress` L28 (`/tracking/progress`, GET shows check-ins and the chart, POST adds one), `update_check_in` L126, `delete_check_in` L153, `analytics` L173 (`GET /tracking/analytics`).
- `analytics.py` (356 lines) — the dataset builders: `get_daily_nutrition_data`, `get_macro_distribution_by_meal`, `get_weekly_trends`, `get_food_category_breakdown`, `get_exercise_vs_diet_balance`, `get_nutrient_intake_vs_goals`, `get_body_composition_trends`.
- `forms.py` (55 lines) — `CheckInForm`.
- Templates: `templates/tracking/progress.html` and `templates/tracking/analytics.html` (canonical owner of the analytics chart markup).

## Local Contracts

- Every dataset builder takes `user_id` and must filter on it; these functions are called from both the tracking routes and the dashboard route, so an unfiltered query leaks across accounts.
- Window boundaries use `time_utils.get_user_today(current_user.timezone)`, not `date.today()`. Every window function in `analytics.py` currently anchors on `date.today()`, which shifts the window for any non-UTC user; treat new code as requiring the user-local version and fix the existing ones when touching this file.
- Loop efficiency is the file's main risk: several builders call `calculate_nutrition_for_items([log])` once per log row and resolve categories with `db.session.get` inside the loop. Build one query per window and group in Python.
- Window sizes default to 30 days (daily/category/exercise), 7 days (macro distribution), and 1 year (weekly trends, all-time check-ins). Keep them parameterised via the `days=` argument so the dashboard and the analytics page can request different ranges.
- Empty-data shapes matter: every card in `analytics.html` is guarded by `{% if <dataset> %}` and has an explicit empty-state message. Returning `[]` / `{}` is correct; raising or returning `None` is not.
- Check-in mutations verify `check_in.user_id == current_user.id` before update or delete.
- `get_nutrient_intake_vs_goals` and `get_body_composition_trends` are redundant with the dashboard's own cards; do not add a third copy of either calculation.

## Work Guidance

- Macro percentages are computed as protein×4, carbs×4, fat×9 over measured calories; keep that definition in this module only.
- Return plain JSON-friendly dicts (dates as `"%Y-%m-%d"` strings) — the template serialises them with `|tojson` straight into Chart.js.
- Route-level tests assert only HTTP 200 today. Add content assertions (canvas ids, empty-state text) when extending, and request the real URLs: `/tracking/analytics`, `/dashboard/<iso>`.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_analytics.py tests/test_tracking.py
```

`tests/test_analytics.py` currently has two wrong-URL failures (it requests `/<iso>` instead of `/dashboard/<iso>`, and uses `auth_client` instead of `auth_client_onboarded`), and the file is not `ruff format` clean.

## Child DOX Index

No child docs.
