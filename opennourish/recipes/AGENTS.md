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

- **`nutrition_label_svg` (L1295-1296) has no access check at all**, while its siblings `generate_label_pdf` (L1285) and `generate_pdf_details` (L1301) both check `is_public or user_id == current_user.id`. Any logged-in user can pull any recipe's label by id; `typst_utils._get_nutrition_label_data_recipe` is a bare `db.session.get`. Mirror the sibling guard.
- **`edit_recipe` writes before it authorises**: it backfills ingredient `seq_num`s and commits (L689-696), and `ensure_portion_sequence` (L731) can commit again, all before the owner check at L764-766. Move the ownership check to the top of the handler.
- `copy_recipe` (L1311) preserves the source row's `portion_id_fk`, `my_food_id`, and `recipe_id_link` while copying portions fresh (L1353-1363), so a copied recipe can point at another user's rows. Re-point them at the copies.
- The ingredient display path re-resolves portions per ingredient (`recipes/routes.py:448` triggers `SAWarning: fully NULL primary key identity cannot load any object` when `portion_id_fk` is NULL); guard on NULL before `db.session.get`.
- Keep `_get_or_create_food_category` behaviour identical to the `my_foods` copy, or extract one shared helper in `utils.py` — the two copies must not diverge silently.
- Import/export changes must be validated by a round-trip test (export then import then compare), not by unit-testing one direction.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_recipes.py tests/test_recipes_routes.py tests/test_recipe_import.py tests/test_recipe_import_export.py tests/test_recipe_final_weight.py tests/test_update_recipe_nutrition.py tests/test_recipe_label.py
```

60 tests; `recipes/routes.py` is at 82% coverage.

## Child DOX Index

No child docs.
