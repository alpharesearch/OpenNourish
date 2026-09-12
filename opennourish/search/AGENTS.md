# opennourish/search — discovery and the universal "add item" endpoint

## Purpose

Search across all four food sources (USDA, user foods, recipes, saved meals) including friend content and UPC lookup, and provide the single endpoint that logs a found item into a diary, a recipe, a meal, or a rematch slot.

## Ownership

- `routes.py` (1559 lines) holds exactly three routes:
  - `search()` L89 — `GET|POST /search/`, 470 lines: query parsing, per-source result assembly, UPC matching, pagination, frequent items.
  - `add_item()` L563 — `POST /search/add_item`, 861 lines: every write path.
  - `get_portions()` L1428 — `GET /search/api/get-portions/<food_type>/<int:food_id>`, JSON for the portion picker.
- Not owned here: portion storage rules (root `models.py` contract), nutrition math (`opennourish/utils.py`), the modal markup (`templates/base.html` `addItemModal`).

## Local Contracts

- Two orthogonal form fields drive `add_item`:
  - `food_type` ∈ `usda`, `my_food`, `recipe`, `my_meal`, `diary_meal`.
  - `target` ∈ `diary`, `recipe`, `meal`, `rematch_ingredient`.
  Adding a sixth `food_type` or fifth `target` means auditing every branch of `add_item`; the pairs are dispatched by nested `if/elif` chains at L783-1100.
- `return_url` is honoured on every exit path; keep it, or callers lose their scroll position and their meal anchor.
- Every USDA food logged must have a 1 g portion. `add_item` creates one on the fly with `was_imported=True` (L737-757) and falls back to it as the default portion. Recipes and user foods get their 1 g portion from their own create path.
- `portion_id == -1` is a sentinel meaning "virtual 1 g portion for rematch" (`UnifiedPortion(gram_weight=1.0)`, L730-733). It does not currently work: L772 unconditionally resets `portion = None` and re-resolves with `db.session.get(UnifiedPortion, portion_id_str)`, so both the sentinel and the MyFood default-portion fallback (L761-766) are dead code, and `-1` resolves to `None` → "A valid portion is required." (L793-797). The rematch branch re-resolves its own portion later (L1070-1085), which is why the flow still appears to work. Repair or delete the dead path; do not add behaviour that depends on it.
- Friend visibility: search results and the portions API filter to `current_user.friends` (L162, L1436, L1451) and exclude the searcher's own content and deleted accounts.
- Two distinct authorization defects live here, both confirmed:
  - The copy-meal branch at L671-676 resolves any account by `friend_username` and reads that user's `DailyLog` rows with no `Friendship` check, unlike the verified equivalent in `diary/routes.py:836-852`.
  - The write paths test `obj.user_id != current_user.id and not obj.user` (L586, L838, L863, L936, L975, L1160, L1184, L1207). That predicate only rejects rows whose owner has been deleted, so any living user's private `MyFood` or `Recipe` can be added to your diary, recipe, or meal and its contents disclosed. Replace it with the plain ownership check plus the friendship rule.
- `return_url` is passed to `redirect()` unvalidated at eight exit points, and `redirect(request.referrer)` is called before any guard at L738/L779/L792/L797 — validate both before touching this handler.
- The GET search view writes: it creates and commits a 1 g USDA portion per result row (L277-287, L496-506). Do not add further writes to it.
- `ensure_portion_sequence` (utils L830) backfills missing `seq_num` by sorting on `gram_weight`; it is called on search result pages (L527-531) and may write. Preserve that call when changing result assembly.
- The Add buttons in templates carry `data-log-date`; `tests/test_search_log_date.py` asserts it by regex on rendered HTML, so keep the attribute when editing the buttons.

## Work Guidance

- `add_item` is the largest function in the codebase. New behaviour goes into a named helper per `target`, not into the existing chain.
- Batch queries: USDA nutrient lookups and portion lookups must be hoisted out of per-item loops (`calculate_nutrition_for_items` already batches by `fdc_id`).
- Anything that changes what a search result row displays must keep `templates/search/` and the `addItemModal` hidden inputs in sync — the modal is in the base layout, not in the search template.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_search.py tests/test_search_upc.py tests/test_search_placeholder.py tests/test_search_log_date.py tests/test_add_to_diary_modal.py
```

44 tests cover this module; `search/routes.py` still sits at 76% coverage, the largest uncovered block in the repo (153 statements).

## Child DOX Index

No child docs.
