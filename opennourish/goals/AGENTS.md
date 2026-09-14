# opennourish/goals — targets, diet presets, BMR and BMI

## Purpose

Create and edit the user's macro/micronutrient targets, derived body-composition targets, and the BMR calculation endpoint the goals form calls.

## Ownership

- `routes.py` (156 lines, 2 routes): `goals` L18 (`GET|POST /goals/`, `@login_required` + `@onboarding_required`), `calculate_bmr_api` L142 (`POST /goals/calculate-bmr`, JSON).
- `forms.py` (115 lines) — `GoalForm`, including the metric/us unit variants and the diet-preset selector.
- Not owned here: `UserGoal` columns (root `models.py`), preset ratios (`constants.DIET_PRESETS`), the math helpers (`opennourish/utils.py`).

## Local Contracts

- `diet_preset` and `goal_modifier` are stored verbatim (`routes.py:39-40`) and are **cosmetic today**: this route never calls `utils.calculate_goals_from_preset`, so the macro gram fields are whatever the form submitted. Do not describe the saved preset as the source of the gram targets until that wiring exists.
- `utils.calculate_goals_from_preset` (`utils.py:369`) returns `None` for any name not exactly matching a `constants.DIET_PRESETS` key (keys are capitalised, e.g. `"Balanced"`). Its only caller is `onboarding/routes.py:172`; it once passed lowercase `"balanced"`, silently killing the step-3 prefill — fixed to `"Balanced"` and test-locked. Keep lookups exact-match on both sides.
- `goals/forms.py:9-33` declares age/gender/height/weight fields that this route never writes back to `User`; treat them as display-only until someone wires them.
- Exercise goals and body-composition goals are stored on the same `UserGoal` row; editing one must not null the other.
- Height/weight units: the form accepts metric or US depending on `current_user.measurement_system` and stores canonical values (cm / kg). Convert on the boundary, store canonical.
- `/goals/calculate-bmr` returns JSON consumed by inline JS on the goals page; keep the response shape and validate inputs (`age`, `gender`, `height_cm`, weight) — invalid input must return an error, not a 500.
- BMI display is derived at render time from height and the latest `CheckIn.weight_kg`; never persist a BMI value.
- This page is one of only two `@onboarding_required` routes, so the onboarding flow must leave a user in a state where this page opens.

## Work Guidance

- Keep the arithmetic in `utils.py` (goals-from-preset, BMR, deviation) so the dashboard, diary API, and this page agree; a formula duplicated in a route will drift.
- If you wire presets for real, do it in one place: `utils.calculate_goals_from_preset` converts preset calorie shares into grams at 4/4/9 kcal, and the calorie target it uses is BMR — decide whether that or `UserGoal.calories` is authoritative before exposing it, and keep the stored gram values self-consistent with the preset.
- FDA scaled daily values are duplicated byte-for-byte between `dashboard/routes.py:202-213` and `profile/routes.py:178-193`; extract before adding a nutrient.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_goals.py tests/test_bmi.py
```

## Child DOX Index

No child docs.
