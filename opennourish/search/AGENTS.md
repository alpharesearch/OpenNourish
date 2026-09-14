# opennourish/search — discovery and the universal "add item" endpoint

## Purpose

Search across all four food sources (USDA, user foods, recipes, saved meals) including friend content and UPC lookup, and provide the single endpoint that logs a found item into a diary, a recipe, a meal, or a rematch slot.

## Ownership

- `routes.py` (1579 lines) holds exactly three routes:
  - `search()` L122 — `GET|POST /search/`: query parsing, per-source result assembly, UPC matching, pagination, frequent items.
  - `add_item()` L596 — `POST /search/add_item`, ~850 lines: every write path.
  - `get_portions()` L1448 — `GET /search/api/get-portions/<food_type>/<int:food_id>`, JSON for the portion picker.
- Not owned here: portion storage rules (root `models.py` contract), nutrition math (`opennourish/utils.py`), the modal markup (`templates/base.html` `addItemModal`).

## Local Contracts

- Two orthogonal form fields drive `add_item`:
  - `food_type` ∈ `usda`, `my_food`, `recipe`, `my_meal`, `diary_meal`.
  - `target` ∈ `diary`, `recipe`, `meal`, `rematch_ingredient`.
  Adding a sixth `food_type` or fifth `target` means auditing every branch of `add_item`; the pairs are dispatched by nested `if/elif` chains inside `add_item` (L596-1445).
- `return_url` is honoured on every exit path; keep it, or callers lose their scroll position and their meal anchor.
- Every USDA food logged must have a 1 g portion. `add_item` creates one on the fly with `was_imported=True` and falls back to it as the default portion (a non-numeric `food_id` on the USDA path is now rejected with "Invalid food ID." rather than 500-ing). Recipes and user foods get their 1 g portion from their own create path.
- `portion_id == -1` is a sentinel meaning "virtual 1 g portion for rematch", but it resolves to `None` on the diary/recipe/meal paths (the sentinel object is discarded and the id is re-resolved against the table) → "A valid portion is required." The rematch branch re-resolves its own portion later, which is why rematch still works. Locked by `test_add_item_virtual_portion_sentinel_is_not_resolved`. Do not add behaviour that depends on `-1` working outside rematch.
- Friend visibility: search results and the portions API filter to `current_user.friends` and exclude the searcher's own content and deleted accounts.
- Authorization on the write paths uses the plain ownership check plus the friendship rule — the two historical defects here are **closed and test-locked**: the copy-meal (`diary_meal`) branch verifies an accepted `Friendship` via `_has_accepted_friendship()` before reading the friend's `DailyLog` rows, and the `obj.user_id != current_user.id and not obj.user` predicate that only rejected deleted owners was replaced with real ownership checks (`_portion_matches_item`, parent checks). `test_search_coverage.py` exercises each rejection both ways. Keep the idiom from `opennourish/AGENTS.md`; do not reintroduce the deleted-owner predicate.
- **Open, not fixed:** `return_url` and `request.referrer` are passed to `redirect()` unvalidated at ~9 exit points (an open redirect). Validate that the target resolves same-host before `redirect()` — but keep the redirect itself; callers rely on it for scroll position and meal anchor.
- The GET search view writes: it creates and commits a 1 g USDA portion per result row (`was_imported=True`, L317 and L536). Do not add further writes to it.
- `ensure_portion_sequence` (utils L830) backfills missing `seq_num` by sorting on `gram_weight`; it is called on search result pages (L560-564) and may write. Preserve those calls when changing result assembly.
- The Add buttons in templates carry `data-log-date`; `tests/test_search_log_date.py` asserts it by regex on rendered HTML, so keep the attribute when editing the buttons.

## Work Guidance

- `add_item` is the largest function in the codebase. New behaviour goes into a named helper per `target`, not into the existing chain. A duplicate `elif target == "rematch_ingredient"` arm (an older copy missing the live arm's validations) was deleted; rematch is handled once, near the end of the chain.
- "Save a meal into another meal" (`my_meal` + `target == "meal"`) is unimplemented: the top-level `my_meal` special case returns on every path, so the `elif food_type == "my_meal"` inside the meal branch is unreachable — and it references a `MyMealItem.my_meal_id_link` column that does not exist in `models.py`. It is reported as "Cannot add a meal to the selected target: meal." (`test_my_meal_into_meal_is_intercepted_before_the_meal_branch`). Implementing it needs a schema decision, not a test change.
- Batch queries: USDA nutrient lookups and portion lookups must be hoisted out of per-item loops (`calculate_nutrition_for_items` already batches by `fdc_id`).
- Anything that changes what a search result row displays must keep `templates/search/` and the `addItemModal` hidden inputs in sync — the modal is in the base layout, not in the search template.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_search.py tests/test_search_upc.py tests/test_search_placeholder.py tests/test_search_log_date.py tests/test_add_to_diary_modal.py tests/test_search_coverage.py
```

163 tests cover this module; `search/routes.py` is at 97% (`tests/test_search_coverage.py` carries it). The 20 remaining statements are provably dead (duplicate `int()` guards, a redundant self-nesting flash, the unreachable meal-in-meal arm) — do not delete them for a cleaner number.

## Child DOX Index

No child docs.
