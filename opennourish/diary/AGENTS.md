# opennourish/diary — daily logging, saved meals, friend meal copy

## Purpose

The diary page for any date, per-meal entry editing (update, move, copy, delete), the user's saved meals, and copying a friend's meal into your own diary.

## Ownership

- `routes.py` (957 lines, 17 routes) mounted at `/`, so paths read `/diary/...`, `/my_meals/...`, and `/api/get-remaining-calories/<date>` (L927).
  - Helpers first: `_get_user_goal` L57 (goal lookup by `user_id` — never `db.session.get(UserGoal, user_id)`, the PK is surrogate), `_meal_order_key` L67 (orders configured meals and sorts ad-hoc names like `"Snack"` last without crashing), `_empty_meal_totals` L81.
  - `diary()` L88 — renders one day for self or read-only friend view; creates `meal_totals` buckets for meal names outside `MEAL_CONFIG` instead of KeyError-ing.
  - Entry mutations: `delete_log` L327, `update_entry` L401, `move_entry` L436, `copy_entry` L470.
  - Saved meals: `delete_meal` L351, `copy_meal` L370, `new_meal` L515, `edit_meal` L525, `delete_meal_item` L598, `save_meal_and_edit` L627, `save_meal_as_recipe` L675, `my_meals` L754, `update_meal_item` L831.
  - `copy_meal_from_friend` L858 — the reference implementation for cross-user access.
- `forms.py` (50 lines) — meal forms.
- Not owned here: adding items from search (`opennourish/search/AGENTS.md`), nutrition totals (`opennourish/utils.py`), the templates (`/templates/AGENTS.md`).

## Local Contracts

- Dates are user-local. Parse the `log_date_str` path segment defensively and compare against `time_utils.get_user_today(current_user.timezone)`; never against `date.today()`.
- Meals come from `MEAL_CONFIG[User.meals_per_day]`. The page anchors each meal block as `meal-<meal-name-slug>`; mutations redirect with `_anchor` so the user lands back on the meal they edited. Preserve the slug formula.
- Every mutation checks ownership with the standard idiom (`diary/routes.py:366-369` is the canonical shape). Saved meals may legitimately have a NULL `user_id` (orphaned by account deletion) — those must render read-only and must never be editable by any user.
- `copy_meal_from_friend` L858 verifies an accepted `Friendship` in both directions **before** querying the friend's `DailyLog` rows, and rejects non-friends. Reuse that block wherever another user is addressed by username. `search/routes.py` `add_item`'s diary-meal copy branch now mirrors this (the old unguarded counter-example is fixed and locked by a friendship matrix in `tests/test_search_coverage.py`).
- Writing a diary row means writing `amount_grams` **and** `portion_id_fk` **and** `serving_type` from the same portion; the update path multiplies `amount × portion.gram_weight` and stores that portion's `full_description_str` as `serving_type`. Storing only one of the three produces a row that displays one value and counts another.
- Deletes are undoable: stash the row in the session for `opennourish/undo` before removing it.
- `/api/get-remaining-calories/<date>` feeds the base-layout modal and returns JSON; its shape is consumed by inline JS in `templates/base.html`.

## Work Guidance

- The GET handler inserts the `Water` `MyFood` and thirteen `UnifiedPortion` rows and commits, and those portions are created without `seq_num` or `portion_description`, so they sort differently from every other 1 g row. Move provisioning to a command or a POST.
- `diary()` aggregates the day, goals, exercise, fasting state, and friend context in one function; extract helpers per card rather than growing it. Its per-log loop runs `calculate_nutrition_for_items([log])` twice per row plus four identity loads — batch per day.
- `update_entry` and `update_meal_item` are the same portion math; a fix to one belongs in both, and neither checks that the posted `portion_id` belongs to the row's food (see the `portion_id` defect in `opennourish/AGENTS.md`).
- `save_meal_and_edit` and `save_meal_as_recipe` insert the `MyMeal`/`Recipe` row **before** checking that the source meal has items, so saving an empty meal leaves an orphan "New Meal from X"/"Recipe from X" row behind (current behaviour pinned by tests). Validate items first.
- Friend viewing renders `diary/diary.html` through the profile blueprint with `is_read_only=True`; any new action button needs that guard.
- Copy/move between meals and dates must keep `log_date` semantics (the row moves, it does not re-date to "today").

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_diary.py tests/test_diary_api.py tests/test_diary_coverage.py tests/test_meals.py tests/test_utils_meals.py tests/test_profile.py
```

`diary/routes.py` is at 100% statement coverage (`tests/test_diary_coverage.py` carries it); the friend-copy path is the area where a regression is a security issue, so keep its negative tests (non-friend rejected, ghost user, empty meal).

## Child DOX Index

No child docs.
