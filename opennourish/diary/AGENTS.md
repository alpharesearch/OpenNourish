# opennourish/diary — daily logging, saved meals, friend meal copy

## Purpose

The diary page for any date, per-meal entry editing (update, move, copy, delete), the user's saved meals, and copying a friend's meal into your own diary.

## Ownership

- `routes.py` (921 lines, 17 routes) mounted at `/`, so paths read `/diary/...`, `/my_meals/...`, and `/api/get-remaining-calories/<date>` (L889).
  - `diary()` L56 — 231 lines: renders one day for self or read-only friend view.
  - Entry mutations: `delete_log` L291, `update_entry` L365, `move_entry` L400, `copy_entry` L434.
  - Saved meals: `new_meal` L479, `edit_meal` L489, `delete_item` L560, `save_meal_and_edit` L589, `save_meal_as_recipe` L637, `my_meals` L716, `update_item` L793, delete/copy L315/L334.
  - `copy_meal_from_friend` L821 — the reference implementation for cross-user access.
- `forms.py` (50 lines) — meal forms.
- Not owned here: adding items from search (`opennourish/search/AGENTS.md`), nutrition totals (`opennourish/utils.py`), the templates (`/templates/AGENTS.md`).

## Local Contracts

- Dates are user-local. Parse the `log_date_str` path segment defensively and compare against `time_utils.get_user_today(current_user.timezone)`; never against `date.today()`.
- Meals come from `MEAL_CONFIG[User.meals_per_day]`. The page anchors each meal block as `meal-<meal-name-slug>`; mutations redirect with `_anchor` so the user lands back on the meal they edited. Preserve the slug formula.
- Every mutation checks ownership with the standard idiom (`diary/routes.py:366-369` is the canonical shape). Saved meals may legitimately have a NULL `user_id` (orphaned by account deletion) — those must render read-only and must never be editable by any user.
- `copy_meal_from_friend` L821 verifies an accepted `Friendship` in both directions (L836-852) **before** querying the friend's `DailyLog` rows, and rejects non-friends. Reuse that block wherever another user is addressed by username; `search/routes.py:671` is the counter-example that skips the check.
- Writing a diary row means writing `amount_grams` **and** `portion_id_fk` **and** `serving_type` from the same portion; the update path multiplies `amount × portion.gram_weight` and stores that portion's `full_description_str` as `serving_type`. Storing only one of the three produces a row that displays one value and counts another.
- Deletes are undoable: stash the row in the session for `opennourish/undo` before removing it.
- `/api/get-remaining-calories/<date>` feeds the base-layout modal and returns JSON; its shape is consumed by inline JS in `templates/base.html`.

## Work Guidance

- `DASHBOARD_ROUTE` in this module is `"dashboard.dashboard"`, which is not a registered endpoint (the real one is `dashboard.index`); `copy_meal_from_friend` redirects to it at `:829,:834,:852` and will raise `BuildError`. Correct it rather than adding another literal.
- `db.session.get(UserGoal, current_user.id)` at `:70` and `:897` looks up the wrong column (`UserGoal.id` is a surrogate); query by `user_id`. `profile/routes.py:254` has the same bug for the friend's goals.
- An ad-hoc `meal_name` (for example the bare `"Snack"` offered by `AddToLogForm`) breaks this page: `:156-158` appends to the meal list without a matching `meal_totals` key and `:198` sorts with `ALL_MEAL_TYPES.index(...)`. Guard both, or keep stored meal names inside `constants.ALL_MEAL_TYPES`.
- The GET handler inserts the `Water` `MyFood` and thirteen `UnifiedPortion` rows (`:208-265`) and commits, and those portions are created without `seq_num` or `portion_description`, so they sort differently from every other 1 g row. Move provisioning to a command or a POST.
- `diary()` aggregates the day, goals, exercise, fasting state, and friend context in one function; extract helpers per card rather than growing it. Its per-log loop runs `calculate_nutrition_for_items([log])` twice per row plus four identity loads — batch per day.
- `update_entry` and `update_meal_item` (`:363` vs `:793`) are the same portion math; a fix to one belongs in both, and neither checks that the posted `portion_id` belongs to the row's food.
- Friend viewing renders `diary/diary.html` through the profile blueprint with `is_read_only=True`; any new action button needs that guard.
- Copy/move between meals and dates must keep `log_date` semantics (the row moves, it does not re-date to "today").

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_diary.py tests/test_diary_api.py tests/test_meals.py tests/test_utils_meals.py tests/test_profile.py
```

`diary/routes.py` is at 81% coverage; the friend-copy path is the area where a regression is a security issue, so keep its negative test (non-friend rejected).

## Child DOX Index

No child docs.
