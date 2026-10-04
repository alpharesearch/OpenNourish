# opennourish/tracking — check-ins, progress, and analytics

## Purpose

Body-composition check-ins, the progress page with its history chart, and the analytics module that derives multi-week trends from diary, exercise, and check-in data.

## Ownership

- `routes.py` (~208 lines, 4 routes): `progress` (`/tracking/progress`, GET shows check-ins and the chart, POST adds one), `update_check_in`, `delete_check_in`, `analytics` (`GET /tracking/analytics`). Refer to them by name, never by line number.
- `analytics.py` (~370 lines) — the dataset builders: `get_daily_nutrition_data`, `get_macro_distribution_by_meal`, `get_weekly_trends`, `get_food_category_breakdown`, `get_exercise_vs_diet_balance`, `get_nutrient_intake_vs_goals`, `get_body_composition_trends`.
- `forms.py` (~55 lines) — `CheckInForm`.
- Templates: `templates/tracking/progress.html` and `templates/tracking/analytics.html` (canonical owner of the analytics chart markup).

## Local Contracts

- Every dataset builder takes `user_id` and must filter on it; these functions are called from both the tracking routes and the dashboard route, so an unfiltered query leaks across accounts.
- Window boundaries are the user's day: every window function in `analytics.py` ends at `_user_today(user_id)`, which reads the row's own owner and calls `time_utils.get_user_today(user.timezone)`. A server-local "today" here silently loses a user's current day from every chart and scores them against yesterday in `get_nutrient_intake_vs_goals` — never reintroduce one. `tests/test_analytics.py::test_the_day_window_follows_the_user_and_not_the_server` builds a user whose date provably differs from the box's and fails if the window moves.
- Loop efficiency is the file's main risk: several builders call `calculate_nutrition_for_items([log])` once per log row and resolve categories with `db.session.get` inside the loop. Build one query per window and group in Python.
- Window sizes default to 30 days (daily/category/exercise), 7 days (macro distribution), and 1 year (weekly trends, all-time check-ins). Keep them parameterised via the `days=` argument so the dashboard and the analytics page can request different ranges.
- Empty-data shapes matter: every card in `analytics.html` is guarded by `{% if <dataset> %}` and has an explicit empty-state message. Returning `[]` / `{}` is correct; raising or returning `None` is not.
- Check-in mutations verify `check_in.user_id == current_user.id` before update or delete.
- `get_nutrient_intake_vs_goals` and `get_body_composition_trends` are redundant with the dashboard's own cards; do not add a third copy of either calculation.

## Work Guidance

- Macro percentages are computed as protein×4, carbs×4, fat×9 over measured calories; keep that definition in this module only.
- Return plain JSON-friendly dicts (dates as `"%Y-%m-%d"` strings) — the template serialises them with `|tojson` straight into Chart.js.
- Route-level tests already assert rendered content (flash text, the stored weight on the page), not just HTTP 200 — keep that, and request the real URLs: `/tracking/analytics`, `/dashboard/<iso>`.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_analytics.py tests/test_tracking.py
```

`tests/test_analytics.py` carries the day-window contract and the dataset shapes; `tests/test_tracking.py` covers check-in add/update/delete both ways (owner allowed, other user rejected).

## Child DOX Index

No child docs.
