# opennourish/recipes — recipe CRUD, nutrition rollup, YAML import/export

## Purpose

User recipes: nested ingredients (foods, other recipes, meals), per-recipe nutrition rollup, portion lists, and the YAML import/export round-trip used by AI assistants.

## Ownership

- `routes.py` (1450 lines, 21 routes): import/export (`import_recipes` L395, `export_recipes` L416), list/new/edit (`recipes` L591, `new_recipe` L623, `edit_recipe` L677), ingredient CRUD and ordering (L902-1018+), portions, copy, rematch.
- Private helpers here, not in `utils.py`: `_process_recipe_yaml_import` L78 (313 lines), `_process_ingredient_for_display` L556, `_get_or_create_food_category` L53 (duplicated with the same function in `my_foods/routes.py:44`).
- `forms.py` (27 lines) holds the WTForms definitions.
- Not owned here: `Recipe` / `RecipeIngredient` / `UnifiedPortion` columns (root), rollup math `update_recipe_nutrition` (`opennourish/utils.py:615`).

## Local Contracts

- A recipe's own nutrient columns are derived, never hand-entered: they are recomputed from ingredients by `update_recipe_nutrition` after any ingredient change. Any new mutation path must call it or the recipe page disagrees with the diary.
- Final weight wins over summed ingredients when computing per-100g values; that precedence is intentional and covered by `tests/test_recipe_final_weight.py`.
- Ingredients are ordered by `RecipeIngredient` order plus each portion's `seq_num`; `move_up` / `move_down` swap and renumber. Reordering must keep both sequences consistent (`ensure_portion_sequence` at L731, L1088).
- Import has two formats: the "simple" YAML format (structured `name`, `quantity`, `unit`, `notes`) which creates placeholder `MyFood` + `UnifiedPortion` rows with `is_placeholder=True`, and the complex format which expects matched foods. Rematch (`search` `target=rematch_ingredient`) replaces placeholders and must preserve original quantity while recalculating `amount_grams`.
- `is_placeholder` survives export → re-import; do not drop it from the export payload.
- Recipes inherit visibility from their owner: unverified or private accounts expose nothing to friends, and deleted accounts leave orphaned rows the cleanup page handles.
- `_process_recipe_yaml_import` optionally calls an LLM parser (`_parse_recipe_with_llm`); tests patch that private name, so renaming it breaks `tests/test_recipe_import.py`.

## Work Guidance

- **`copy_recipe` (L1327) preserves the source row's `portion_id_fk`, `my_food_id`, and `recipe_id_link`** on the copied ingredients while copying portions fresh, so a copied recipe can point at another user's rows. Re-point them at the copies (or at the copies' new portion ids).
- The two historical authorisation defects are **fixed and test-locked**: `nutrition_label_svg` now mirrors the sibling guard (`is_public or owner`, 403 otherwise) and `edit_recipe` runs the ownership check **before** the `seq_num` backfills/`ensure_portion_sequence` that commit. Keep the check first; the ingredient-display path already guards `portion_id_fk` before `db.session.get`.
- Keep `_get_or_create_food_category` behaviour identical to the `my_foods` copy, or extract one shared helper in `utils.py` — the two copies must not diverge silently.
- Import/export changes must be validated by a round-trip test (export then import then compare), not by unit-testing one direction.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_recipes.py tests/test_recipes_routes.py tests/test_recipe_import.py tests/test_recipe_import_export.py tests/test_recipe_final_weight.py tests/test_update_recipe_nutrition.py tests/test_recipe_label.py tests/test_recipes_coverage.py
```

124 tests; `recipes/routes.py` is at 99% (`tests/test_recipes_coverage.py`). The single remaining miss (L441 `continue` in `export_recipes`) is unreachable — the identity map guarantees one object per recipe id, so the processed-set branch never fires.

## Child DOX Index

No child docs.
