# opennourish/my_foods — user foods, categories, import/export

## Purpose

The user's own food database: hand-entered foods, copies of USDA foods, categories, portion lists, and CSV/YAML import plus export used as the AI-assistant interchange format.

## Ownership

- `routes.py` (1070 lines, 18 routes): list L284, `new_my_food` L312, `edit_my_food` L432, delete L540, portion add/update/delete L555-612, `copy_usda_food` L634, import L246, export, category CRUD.
- `_process_yaml_import` L69 and `_export_my_foods_to_yaml` L941 define the file format contract; `_get_or_create_food_category` L44 is duplicated in `recipes/routes.py:53`.
- Not owned here: the `portions` table rules (root `models.py` contract), category seed data (USDA admin).

## Local Contracts

- `MyFood` stores 15 explicit `*_per_100g` columns (the identical block `Recipe` duplicates). Values are always per 100 g; display code scales by `portion.gram_weight` (`get_nutrients_for_display`, utils L851 treats `gram_weight == 1.0` as the per-gram base). Never store per-portion values.
- Every user food needs a 1 g portion plus any named portions; portion `seq_num` ordering is what the UI shows, and `portion_id_fk` on a diary row plus `amount_grams` must both reflect the chosen portion's `gram_weight`.
- `copy_usda_food` snapshots USDA values into a new `MyFood` — after copying, the user food is independent of the USDA row.
- Import accepts both the legacy flat format and the structured format; it must remain backward compatible, keep `seq_num` correct, and never create duplicate portions for an existing food.
- Export is scaled by the food's first portion, not by 100 g, and must round-trip through import (including `is_placeholder` foods coming from recipe imports).
- Category rows are shared per user (`FoodCategory`, default bind); deleting a category must not orphan foods that reference it.

## Work Guidance

- `delete_category` is owner-scoped and preserves other accounts' category links: the bulk `food_category_id` clear filters on `user_id=current_user.id`, and because the `FoodCategory→MyFood` ORM delete dependency (`models.py`) also nulls every referencing row, the route captures foreign rows and re-points them after the delete. Do not remove either step — a plain delete un-categorises other users' foods.
- Portion mutations resolve the parent before touching ownership. USDA/recipe portions have `my_food=None`, so dereferencing `portion.my_food.user_id` raises `AttributeError`; use the `_owned_portion_or_none()` helper (checks the parent type and owner) on the update and move routes rather than re-introducing the direct dereference.
- Unlike `usda_admin` and `recipes`, the portion move routes here have no NULL-`seq_num` guard, so a swap silently no-ops on rows that `ensure_portion_sequence` has not repaired yet.
- `new_my_food` and `edit_my_food` implement two independent per-100 g conversions and each spells out all 15 nutrient fields, with a third copy as string names in `copy_usda_food`. Consolidate on `utils.get_nutrients_for_display` / `convert_display_nutrients_to_100g` before adding a nutrient.
- Deletion goes through the undo mechanism (`opennourish/undo`): stash the serialised row in the session before deleting.
- Import/export changes: add or update a round-trip test in `test_my_foods_import.py` / `test_my_foods_export.py`; assert the exported payload re-imports to identical values. Import errors must be collected and reported per row rather than aborting the whole file.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_my_foods_features.py tests/test_my_foods_import.py tests/test_my_foods_export.py tests/test_my_foods_categories.py tests/test_my_foods_coverage.py
```

70 tests; `my_foods/routes.py` is at 99% (`tests/test_my_foods_coverage.py`). The two remaining misses are the `new_my_food` gram-weight guard that `PortionForm` validators make unreachable over HTTP — behaviour is locked, do not "fix" the branch.

## Child DOX Index

No child docs.
