# Migration plan — Python 3.12, dependency refresh, tooling gates

Target interpreter: **Python 3.12** (security-supported to 2028-10-31).
Evidence behind the numbers: [`README.md`](README.md). Candidate locks live in this folder until the
milestone that consumes them lands, and are deleted once `requirements.txt` supersedes them.

**Status as of 2026-09-23: M0, M1, M2, M2b, M3 and M4's CI step have landed, and deployment provenance landed with them. The runtime/dev split (M4's second half) is dropped. M5 and M6 (security hardening, added once the upgrade track closed) are pending.**
Landed state: conda env `opennourish` and both Docker stages are on 3.12, `requirements.in` drives a
generated `requirements.txt` (54 packages, was 72), Flask-Mailing is at 3.0.0, `ruff.toml` pins its rule
families, the image's `typst` is 0.15.1, `.github/workflows/ci.yml` runs the four gates on every push and
PR, and every gate is green — 975 tests passed, `ruff check` clean, `ruff format --check` clean, djlint
advisory at 204 findings. `THIRD-PARTY-LICENSES.md` is no longer hand-maintained: `gen_licenses.py`
generates it from the installed wheels plus the vendored assets in `static/`, and `--check` fails if it
drifts.

## Ground rules

- **No schema change anywhere in this plan.** `models.py` is untouched, so no Alembic revision is
  generated and `safe_upgrade.sh` is not part of any step. If a step ever needs one, it stops and
  backs up through `./safe_upgrade.sh` first.
- **Never run `seed_usda.sh`** (it deletes `persistent/user_data.db`) and do not trust `seed_db.sh`.
- Every milestone is one shippable commit with its own rollback. Do not merge two of them.
- `entrypoint.sh` runs under `set -e` on a fresh volume: a dependency that imports badly is a boot
  loop, not a 500. Always boot the built image before deploying.
- Order matters: pin the ruff rule set (M1) *before* ruff moves, or the gate goes red with 372
  findings and stops being a signal.

## M0 — Environment truth (no repo change) — LANDED

Done 2026-09-23: `opennourish-py39-backup` holds the 3.9.23 clone, `opennourish` is recreated on
3.12.14, `pip check` is silent, and `python -m djlint --version` now works — it previously failed,
which is how the documented advisory lint had been silently unrunnable.

Rebuild the dev env so `requirements.txt` and the conda env agree again.

1. Clone the current env aside for rollback:
   `conda create -y -n opennourish-py39-backup --clone opennourish`
2. Recreate it from the lock on 3.12 (see M2 for the lock):
   `conda create -y -n opennourish python=3.12 && conda run -n opennourish pip install -r requirements.txt`
3. Confirm the drift is gone both ways: `pip check`, and that `python -m djlint --version` works —
   it currently fails, so the documented advisory lint has been silently unrunnable.

**Rollback:** `conda env remove -n opennourish` then `conda create -n opennourish --clone opennourish-py39-backup`.

## M1 — Pin the lint contract — LANDED

`ruff.toml` set only `per-file-ignores`, so the old clean gate rode ruff 0.5.5's implicit default
rule set. Newer ruff ships a much wider default (confirmed with `--isolated`): ~372 findings here,
led by `I001` 124, `DTZ011` 108, `RUF059` 65.

```toml
exclude = ["*.md"]                        # ruff >=0.16 reformats fenced blocks in Markdown too

[lint]
select = ["E4", "E7", "E9", "F"]          # the rule families the codebase is actually clean under
```

Both keys were needed. `GEMINI.md` and `README.md` are documentation (and `GEMINI.md`/`QWEN.md` are
hardlinks of each other), so Markdown is excluded rather than reformatted.

Landed consequence: ruff 0.16.8's *formatter* also differs from 0.5.5, and `ruff format` rewrote 6
Python files (`opennourish/typst_utils.py` + 5 test modules). That was verified safe — every literal
character of the Typst template is byte-identical, only text inside `{...}` f-string fields moved —
but it introduced **PEP 701 nested-quote f-strings**, which is the mechanical reason 3.11 and below
can no longer import `typst_utils.py`. Recorded in the root `AGENTS.md` Toolchain contract.

**Verify:** `$P -m ruff check .` and `$P -m ruff format --check .` both clean.
**Rollback:** revert `ruff.toml` and the 6 reformatted files together.

## M2 — Prune, regenerate the lock, bump the image to 3.12 — LANDED (2026-09-23, cold-volume boot verified)

One commit; the interpreter and dependency bumps land together because the prunes and the newest
releases are what the resolver produced for 3.12.

1. **Prune what nothing imports and nothing needs on 3.12** — 11 pins: `soupsieve`,
   `SQLAlchemy-Utils`, `importlib_metadata`, `zipp`, `tomli`, `exceptiongroup`, `six`,
   `python-dateutil`, `sniffio`, `colorama`, `tqdm`. The last four fall out because `anyio` and
   `Faker 40` dropped them and djlint 1.46 no longer needs them; `pytz` needs no file change (it is
   env-only drift). **`aioredis` and the `httpx` chain stay for now** — `Flask-Mailing==0.2.3`
   requires them, and the resolver will re-add anything deleted by hand. They go in M3.
2. **Add `requirements.in`** at the repo root as the hand-edited surface (drafted in this folder),
   with `Flask-Mailing==0.2.3` pinned and a comment naming 3.0.0 as the M3 target.
3. **Regenerate `requirements.txt`** from it: 61 packages, down from 72, every advisory clear. The
   adopted lock file in this folder was deleted once `requirements.txt` carried it. Dev tooling lives
   in the same file as runtime — the split was later dropped, see M4.
4. **Fix the regeneration recipe in `DEV-README.md`.** `pip freeze > requirements.txt` is how the
   file drifted; it is replaced by a real resolver command — today
   `pip-compile --strip-extras -o requirements.txt requirements.in`, run with the 3.12 interpreter —
   and by the record that `pip check` must stay silent. (`--generate-hashes` was weighed here and not
   adopted: nothing in this repo verifies hashes, and `pip install` would then need `--require-hashes`
   everywhere, including in the Dockerfile.)
5. **`Dockerfile`:** `python:3.9` → `python:3.12` (build stage), `python:3.9-slim` →
   `python:3.12-slim` (runtime stage). Both stages must stay on the same minor: the venv is copied
   between them and is not portable across interpreter versions.

**Verify** — all green on 2026-09-23:
- ✅ `$P -m pytest -m "not integration" -q` → 972 passed, 1 deselected.
- ✅ `$P -m ruff check .` and `$P -m ruff format --check .` → clean.
- ✅ `$P -m djlint templates --profile jinja --extension html --use-gitignore` → advisory, 204
  findings under djlint 1.46.2 (was ~230 under 1.36.4).
- ✅ `docker build -t opennourish:m2-312 .` → built (build context is ~81 MB once `persistent/` is
  excluded by `.dockerignore`).
- ✅ Image smoke test, bypassing the entrypoint: interpreter 3.12.14, `pip check` silent, `typst`
  present (0.13.1 at that point — M2b moved the pin to 0.15.1), `python -m compileall` parses every
  module, and `create_app()` boots with 133
  routes registered. Run it with `--entrypoint python`, never by appending a command: `ENTRYPOINT`
  is `entrypoint.sh`, which downloads the 474 MB USDA archive before it ever reaches your arguments.
- ✅ **Cold-volume boot verified on a fresh checkout** (2026-09-23, at `1a14ae3` with an empty
  `persistent/`): `entrypoint.sh` downloaded and unpacked the pinned USDA CSVs (3.0 GB), rebuilt
  `usda_data.db` (1.74 GB — `foods` 1,768,972, `nutrients` 477, `food_nutrients` 17,615,687,
  `pragma quick_check` ok), stamped Alembic `4ff671f5bcdc`, then seeded 47,088 `portions`,
  28 `food_category` rows, 6 `exercise_activities` and the `markus` dev admin, all under 3.12.14. The
  residual risk this bullet was holding — interpreter behaviour inside the seed scripts — is retired,
  and the boot-loop row is gone from the risk register.
- ✅ **Label render through the subprocess:** 159 tests in the four typst-dependent files pass *inside
  the built image*, against the shipped binary rather than a host one (M2b).
- Measured while verifying, so nobody re-litigates it: `foods.fdc_id` is `INTEGER PRIMARY KEY`, hence
  the rowid — a lookup is a B-tree seek (0.1 ms across 1.77 M rows, full scan 55 ms) and
  `food_nutrients` carries `idx_food_nutrients_unique`. No index work is warranted.

**Incidental finding:** `aioredis` cannot be imported on 3.12 at all — it dies on
`from distutils.version import StrictVersion`, and `distutils` is gone. Nothing noticed because
Flask-Mailing guards that import in a `try/except` inside `utils/email_check.py`, an optional
disposable-email-check feature this app never calls. The package is inert weight in the image today,
and M3 removes it.

**Rollback:** revert `requirements.txt`, `requirements.in`, `DEV-README.md`, `Dockerfile`.
The previous image tag is untouched.

## M2b — typst binary bump (0.13.1 → 0.15.1) — LANDED (2026-09-23)

One URL in the `Dockerfile` runtime stage. `.github/workflows/ci.yml` greps that URL rather than
duplicating it, so the runner cannot test a different typst build than the one shipped. It rides here
rather than in M5 because the image still owes its cold-volume boot (M2): one rebuild validates the
interpreter move and the renderer together.

Two majors is a real gap — 0.14.0 landed 2025-10-24 and 0.15.0 on 2026-06-15, each with breaking
changes — so the bump was decided on rendered output, not on the changelog. All seven `.typ` sources
the app generates were compiled with 0.13.1, 0.14.0, 0.14.2, 0.15.0 and 0.15.1, which holds the
templates constant and leaves the binary as the only variable:

| check | 0.13.1 → 0.15.1 |
|---|---|
| PDF raster, all 5 artifacts at 100 dpi | identical |
| PDF raster, 2 artifacts at 300 dpi (0.24 pt/px) | identical |
| PDF text layer (`pdftotext -layout`, position-sensitive) | identical for all 5 |
| SVG raster at 1× | 37 of 1,080,000 pixels differ, RMSE 2.3e-5 |
| 0.15.0 vs 0.15.1 | byte-identical PDFs, 0 differing pixels |
| the 159 tests in the 4 typst-dependent files | green under 0.15.1 |

Sizes move without appearance. PDFs grow 33 → 40 KB and SVGs shrink 222 → 181 KB, which is 124 wrapper
groups collapsing to 48 with path counts (181) and unique glyph paths (165) unchanged. 0.14.2 is the
worst PDF of the five (43 KB, larger than both neighbours) and buys nothing, which is why 0.14.x was
skipped rather than stepped through.

None of the documented breakages reach these templates: no math mode, no `link`/`slice`/`str(base:)`/
`enum.item`/`pdf.embed`, no HTML export, fonts selected by one name rather than a fallback list, no
backslash paths. Registry position was checked too — `nutrition-label-nam` 0.2.0 and `codetastic`
0.2.2 are the newest published versions, their `typst.toml` declares no `typst-version` floor, and
`typst/typst` carries **zero** security advisories (OSV is empty for the crate and for the wheel), so
this is currency, not a CVE fix. The one advisory on `typst/packages` is their own
`pull_request_target` CI bug, not these two packages.

**Verify:** `docker run --rm --entrypoint typst <image> --version` reports `typst 0.15.1`, and the 159
tests of the four typst-dependent files pass with the image's own interpreter and binary. CI exercises
the same build, because its typst step greps this URL — run 35925075739 is that step installing 0.15.1
on the runner and passing the suite. The dev host was moved too: `/usr/local/bin/typst` is 0.15.1 with
sha256 `29273eaa04f6d00e…`, byte-identical to the copy inside the image, so dev, CI and image agree on
one renderer. **Rollback:** put `v0.13.1` back in that one URL.

## M3 — Flask-Mailing 3.0.0 (first app-code change) — LANDED (2026-09-23, live round-trip verified on TrueNAS)

`Mail.init_app` in 3.0.0 raises `ValueError` unless `MAIL_SERVER`, `MAIL_USERNAME` and
`MAIL_PASSWORD` are all non-empty, and this app deliberately runs with them empty
(`opennourish/__init__.py`, DB-loaded with `default=""`). Measured before changing anything: with
3.0.0 installed and the old one-line init, `tests/test_app_factory_coverage.py` alone went 2 failed
+ 15 errored on `ValueError: Missing required configuration: MAIL_USERNAME, MAIL_PASSWORD`. The
application could not boot at all, which is the whole of M3's risk.

What shipped:

1. **Init is conditional** — `mail.init_app(app)` runs only when `MAIL_SERVER` is non-empty: the
   preferred shape from step 1 of the original list, so `USE_CREDENTIALS = False` stays honest.
   Readiness probe is `"mailing" in app.extensions`.
2. **A second break the plan did not know about.** 3.x reads suppression as **`SUPPRESS_SEND`**
   (a `ConnectionConfig` field; `connection.py` checks `settings.get("SUPPRESS_SEND")`), while the
   environment, the `system_settings` rows and the `app.testing` override all speak
   `MAIL_SUPPRESS_SEND`. Unbridged, suppression silently stops working — the suite patches
   `Mail.send_message` at `conftest.py:49`, so no test could notice, and a deployment running with
   `MAIL_SUPPRESS_SEND=true` would start dialing SMTP. The factory now bridges both names.
3. **Unauthenticated relays still work.** Whichever credential is empty is set to
   `NO_MAIL_CREDENTIAL` for the duration of `init_app` and restored to `""` immediately after, so
   `ConnectionConfig` receives a non-empty string while nothing else in the app reads a fake value.
   The obvious reading of step 1 — skip init when there are no credentials — would have broken a
   legitimate configuration instead.
4. Step 2's claim is now genuinely verified, which it could not be at 0.2.3: `send_message` is
   still `async def` and `Message` still takes `subject` / `recipients` / `html` (as pydantic
   fields; `__init__` is now `**data`), so both send sites in `opennourish/utils.py` are untouched.
5. The lock was **regenerated from `requirements.in`**, not adopted from
   `lock-py312-flaskmailing-3.0.0.txt` — it produced the same 54 pins, so the candidate file is
   deleted here as M2's was. Dropped: `aioredis`, `anyio`, `async-timeout`, `certifi`, `h11`,
   `httpcore`, `httpx`. That is the entire mail chain, and with it **CRITICAL** anyio
   CVE-2026-63374 leaves the image. `aiosmtplib` and `pydantic` were already in the lock (0.2.3 used
   both), which is why installing 3.0.0 swapped exactly one package.
6. Three tests in `tests/test_app_factory_coverage.py` cover both new branches and the bridge: boots
   with no server, `MAIL_SUPPRESS_SEND` → `SUPPRESS_SEND`, and relay-without-credentials (the
   placeholder reaches `ConnectionConfig` and the config keys come back empty).

**Verified:** 975 passed (`-m "not integration"`), ruff lint and format clean, `pip check` silent,
`gen_licenses.py --check` current at 54 packages. Image rebuilt: `BUILD_INFO` reports
`packages=54` and a `requirements_sha256` equal to `sha256sum requirements.txt` on the host. Probed
inside the image, all four mail shapes behave: no server → not initialised, app boots; relay with no
credentials → initialised, `USE_CREDENTIALS=False`, placeholder on the wire, `""` in config; server +
credentials → real values; `MAIL_SUPPRESS_SEND=False` with `TESTING` off → `SUPPRESS_SEND=0`.

**Verified on the deployment (2026-09-23):** the image built from these commits is live on TrueNAS, and
a password-reset email arrived. That is the round-trip no test here can perform — every send point is
patched in the suite and CI has no mail server — and it is also field evidence for the bridge: had
`SUPPRESS_SEND` come out non-zero, `connection.py` would have dropped the send silently and nothing
would have arrived. The deployment runs in **environment mode** (no `MAIL_CONFIG_SOURCE` row in
`system_settings`; mail has never been saved in the admin UI there), so its container `MAIL_*`
variables are the live mail config. `send_verification_email` uses the other send site and has not had
its own live round-trip.

**Rollback:** revert `opennourish/__init__.py`, `requirements.in`, `requirements.txt` and the three
tests. The pre-bump lock is `requirements.txt` at `1ad7b82`. `AGENTS.md` and `opennourish/AGENTS.md`
carry the new init contract and must be reverted with the code.

## M4 — Runtime/dev split, then CI — CI LANDED (2026-09-23); the split is DROPPED (2026-09-23)

1. **`.github/workflows/ci.yml` — landed early, pulled ahead of the split** so M3, the first
   app-code change in this plan, lands under automated gates rather than manual discipline. It
   installs the one flat `requirements.txt` on 3.12, runs `pip check`, then all four gates. djlint is
   absent by design. Each gate step carries `if: ${{ !cancelled() }}` so one push reports everything
   that is broken, not just the first failure. It needs `SECRET_KEY` plus an `ENCRYPTION_KEY`
   shaped like a real Fernet key — generated per run into `$GITHUB_ENV`, because `config.py` only
   fails at import if the value is absent, and a placeholder string would survive import and then
   fail at the `MAIL_PASSWORD` decrypt call site.
2. **Split `requirements.in` into runtime and `requirements-dev.in` — DROPPED.** The reason to do it
   was licensing tidiness, not behaviour: **djlint is GPL-3.0-or-later** and ships in the distributed
   image together with its `cssbeautifier`/`jsbeautifier`/`EditorConfig`/`json5`/`pathspec`/`regex`
   closure. That state is compliant — djlint ships unmodified with its licence text, which
   `THIRD-PARTY-LICENSES.md` carries — and the owner declined to spend a file split on it
   (2026-09-23). Treat the copyleft-in-image fact as accepted, not as an open item; what it does rule
   out is *modifying* djlint or distributing a derivative of it. `Faker` stays a runtime dependency
   either way, because the boot-time `seed-dev-data` uses it.
3. CI's follow-up step — install runtime + dev instead of the flat lock — goes with the split. The
   workflow stays exactly as landed: one flat `requirements.txt`.

**Verify:** the job's steps were replayed here in a clean `python3.12 -m venv` with nothing but
`requirements.txt` installed — install clean, `pip check` silent, 972 passed, `ruff check` and
`ruff format --check` clean, `gen_licenses.py --check` current. That the licence gate passes from a
pristine install matters: it proves the recorded texts and hashes do not depend on this machine's
conda env or on platform-specific wheel contents.

The first real run then **failed the suite while the other three gates went green**: 17 label tests
(`test_utils.py` 6, `test_typst_coverage.py` 6, `test_recipes_coverage.py` 4, `test_recipe_label.py` 1)
returned `500 == 200` because a GitHub runner has no `typst` binary. Nothing in `requirements.txt`
can express a native binary, so CI now downloads the same `typst` build the Dockerfile does — the URL
is grepped out of the `Dockerfile` rather than duplicated — and installs `fonts-liberation`, which
the templates need (`opennourish/typst_utils.py` pins Liberation Sans). Re-verified by replaying
those commands in a tracked-files-only `git worktree` with `typst` otherwise off PATH: 972 passed.

**The re-run went green end to end** — run [35925075739](https://github.com/alpharesearch/OpenNourish/actions/runs/35925075739)
at `40a3940`, all nine steps success in 4m51s: lock install, `pip check`, typst install, test suite,
lint, formatting, licence inventory. Job logs need repo admin rights, so failures are diagnosed by
replaying the steps locally, which is what worked here.

## M5 — Follow-up cleanup (tracked, not blocking)

- **`datetime.utcnow()` — 12 call sites, plus `models.py:142`'s bare `default=datetime.utcnow`.**
  Deprecated on 3.12, scheduled for removal, and the source of `DTZ011` noise. Migrate to
  `datetime.now(timezone.utc)` in line with `opennourish/time_utils.py`; the column default holds the
  *callable*, so it needs a lambda rather than a find-and-replace — that is the one spot a mechanical
  pass gets wrong silently. This is the largest remaining behaviour-adjacent edit, so give it its own
  commit and read the timezone rules in `opennourish/AGENTS.md` first.
- **Adopt ruff rules family by family** (`I001` 124, then `DTZ011` 108 with the utcnow work, then
  `RUF059` 65, `BLE001` 13) instead of a 372-finding big bang.
- **`pytest-flask`** works on pytest 9 but has been unmaintained since 2023-10 (classifiers stop at
  3.9). Replace with plain fixtures when convenient.
- **Next interpreter refresh: 3.14** (security to 2030-10-31). `djlint 1.46.2`, `pytest 9.1.1`,
  `SQLAlchemy 2.0.54`, `cryptography 50.0.1`, `greenlet 3.5.6` all declare 3.14/3.15 support.
  Re-run M0/M2 verification rather than assuming it carries over.
- **User text reaches the Typst templates as markup, not as strings.** `opennourish/typst_utils.py:248`
  interpolates the food description after a `=` heading and the myfood/recipe builders do the same,
  while `_sanitize_for_typst` escapes only `\ " *` — so `$`, `#`, `<`, `@` are live syntax. A food
  named `Yogurt $5 pack` already fails **today**, on typst 0.13.1, with `error: unclosed dollar`, and
  the label route answers 500. Four constructs render on ≤0.13 and error on ≥0.14 — `#link("")`,
  `#text(font: ())`, `#pdf.embed`, `image("a\b.png")` — but all need deliberate markup: nine plausible
  names (`Beef #9`, `Soup #2 - Tomato`, `100% Juice`, `Vitamin A & D`, `1/2 cup oats`, …) behave
  identically on every version, so no existing data is at risk from M2b. Fix by escaping `$ # < > @`
  next to `*`, or by passing descriptions as string arguments instead of content, with one regression
  test per template builder. `= Yogurt \$5 pack` compiles on both ends of the version range.
- **Labels need outbound internet at render time.** The image caches no `@preview` packages and the
  `subprocess.run` calls pass no `--root`, so the first label render inside a container downloads
  `nutrition-label-nam:0.2.0` and `codetastic:0.2.2` from typst.app; with no egress every label route
  500s. Fetching both during the build into `TYPST_PACKAGE_CACHE_PATH` removes the dependency.
  Checked on the way: typst's default root confines `#read` to the temp directory, so injected markup
  cannot read the filesystem — `#read("/etc/hostname")` fails on 0.13.1 and 0.15.1 alike.
- **Unrelated but adjacent:** `.dockerignore` still lets `htmlcov/` (9.8 MB) and `.kilocode/` (58 MB)
  into every image — measured rather than estimated, because the same commit built to 418 MB from this
  checkout and 351 MB from a clean clone, so ~68 MB of editor state and coverage HTML ships on every
  deploy and makes up most of the build context. Exclude both. The other deployment-script items live
  in M6.3 now that the YAML block is understood to be the artifact itself; the unquoted `.env` export
  is worth fixing regardless of which mail mode a deployment uses.

## M6 — Security hardening (added 2026-09-23, after the upgrade track closed)

These hazards are recorded in `AGENTS.md` but owned by no milestone, so they were knowledge rather
than work. The upgrade track is finished and the app is deployed, so each item below is independently
shippable, ordered by exposure. Numbers were re-measured today, not carried over from the audit.

### M6.1 — Close the CSRF gap

Measured: **98 `<form>` tags, 29 `hidden_tag()` calls, 20 of 32 form-bearing templates**; `CSRFProtect`
is registered nowhere in app code. The trap is that `tests/conftest.py:26` and
`test_app_factory_coverage.py:28` both set `WTF_CSRF_ENABLED = False`, so **the suite is blind to this
before and after** — a green run proves nothing here.

1. Add `hidden_tag()` to every POST form. Mechanical, and the 6 structural H025 findings djlint
   reports live in the same files — fix them while in there.
2. Audit JS-initiated posts (portions API, Chart.js refresh, html5-qrcode upload, anything using
   `fetch`/XHR). Those need an `X-CSRFToken` header or step 3 breaks them silently in production.
3. Register `CSRFProtect(app)` in `create_app`, **and** add a test that builds the app with CSRF
   *enabled* and asserts an untokenised POST is rejected while a tokenised one is not. Without that
   test the gate stays blind forever.
4. Never hand-roll tokens, and do not exempt routes to make step 3 pass quietly (`AGENTS.md` rule).

### M6.2 — Mutating GETs, which no CSRF token can cover

`/undo` is `methods=["GET"]` (`opennourish/undo/routes.py:254`), `onboarding.finish_onboarding`
commits, and `ensure_portion_sequence` writes from GET handlers in `main`, `search`, `recipes` and
`my_foods`. These stay exploitable after M6.1, because CSRF protection guards non-GET methods only.
Convert to POST, then M6.1 covers them.

### M6.3 — Deployment secrets, keeping the copy-paste deploy working

The YAML block is load-bearing, and the reason is more specific than "TrueNAS needs env vars".
`system_settings` is empty on a fresh volume, and `MAIL_CONFIG_SOURCE` — read from the **database**
at `opennourish/__init__.py:76-79`, written only when an admin saves email settings at
`opennourish/admin/routes.py:111-118` — **defaults to `"environment"`**. So today the container's
`MAIL_*` values are the live mail configuration, and they only go inert after someone saves mail
settings in the UI. Check which mode a deployment is in with
`docker exec <app> python -c "import sqlite3;print([r[0] for r in sqlite3.connect('/app/persistent/user_data.db').execute('select key from system_settings')])"`
— presence of a `MAIL_CONFIG_SOURCE` row means database mode.

- `SECRET_KEY` never needs pasting: `config.py:27` already falls back to `persistent/secret_key.txt`
  on the volume.
- `ENCRYPTION_KEY` is the one irreducible pasted secret (`config.py:79`, env only). A symmetric
  `persistent/encryption_key.txt` fallback would make the generated YAML secret-free, at the cost of
  two key files on the dataset instead of one — a decision, not a free win.
- `FLASK_DEBUG` is emitted into the YAML and read by no code. Delete it.
- Fix `deploy_truenas.sh:20`: the unquoted `export $(cat .env | xargs)` word-splits any value
  containing a space — including a `SECRET_KEY` — and exports every unrelated key in the file. Use
  `set -a; . ./.env; set +a`.
- Add `name: opennourish` to `docker-compose.yml` so image names stop depending on the checkout
  directory's name; a clone in `~/opennourish-test` currently tags images that do not exist.
- **Keep printing the YAML.** TrueNAS's custom-app editor takes neither `env_file` nor `${VAR}` from a
  host file, and whatever is pasted is stored in TrueNAS's own app config anyway, so the paste is not
  the exposure — scrollback, terminal history and CI logs are. Write the YAML to a `0600` file and
  print the path plus only the non-secret parts.

### M6.4 — Seed-admin default

`.env.example` ships `SEED_DEV_DATA=true` and `opennourish/__init__.py:298-301` creates administrator
`markus` with password `1`; registration is open and the first registrant becomes admin when
`INITIAL_ADMIN_USERNAME` is unset. Flip the example default to `false`, and have the seeder generate a
random password printed once instead of `1`. This combination is already described in a public repo,
so treat it as publicly known configuration.

### M6.5 — Input-handling defects already recorded as inherited

The open redirect on `add_item`'s `return_url`/`request.referrer` (~9 exit points,
`opennourish/search/routes.py`) and the unvalidated `portion_id` in the diary add/edit paths
(`opennourish/diary/routes.py:411`, `:560`). Typst markup injection from user text stays in M5 — do
it once, not in both places.

### M6.6 — Network-facing defaults

`serve.py` trusts `X-Forwarded-*` from any peer that reaches :8081 (latent, because compose publishes
no app port today) — replace unconditional trust with an explicit trusted-proxy setting. And
`nginx/nginx.conf` sets no `client_max_body_size`, so the YAML food/recipe importers are capped at
1 MiB: a functional bug as much as a hardening item.

**Ordering:** nothing upstream of M6 is outstanding — M3 landed and M4's split is dropped, which removes
the earlier constraint against meeting M4's file churn. The one live conflict is internal: M6.1 rewrites
templates and djlint's `--reformat` rewrites 42 of 43 files, so those two churns must not meet inside one
commit.
**Verify:** full suite, plus the new CSRF-enabled test, plus a manual pass over the 32 form-bearing
templates (register, login, onboarding, diary add, recipe save, admin settings, YAML import), plus
`curl -i` on an untokenised POST against a running container expecting 400.
**Rollback:** the `CSRFProtect` registration is one call, and `hidden_tag()` is inert without it, so
steps 1–2 are safe to land well ahead of step 3.

## Deployment provenance — LANDED (2026-09-23, outside the milestone sequence)

Added after the first TrueNAS deployment turned out to be unidentifiable. Three layers erased
identity at once: `deploy_truenas.sh` tagged every build in history as the constant `V1.0.0`, the
TrueNAS YAML it generates pulls a mutable `:latest`, and the `Dockerfile` had no `ARG` and no `LABEL`,
so `docker inspect` said nothing and boot printed nothing about itself.

- `VCS_REF`/`BUILD_DATE` build args now reach three places: OCI labels, `/app/BUILD_INFO` (revision,
  build date, python, typst, `requirements_sha256`, package count), and the banner `entrypoint.sh`
  prints before the USDA work — so a container that boot-loops still says which build it is, in the
  one place TrueNAS surfaces: the log pane.
- `deploy_truenas.sh` stamps both args from git, with a `-dirty` suffix on an unclean tree. A plain
  `docker compose build` yields `revision=unknown` on purpose: a local build has no published commit,
  and admitting that beats printing a SHA that may be stale.
- **Per-commit image tags were weighed and deliberately not adopted.** Tags stay `V1.0.0` + `:latest`,
  so identity comes from the image, not the tag: `docker exec <app> cat /app/BUILD_INFO`, then compare
  its `requirements_sha256` with `sha256sum requirements.txt` at the commit you think is deployed. The
  re-pull caveat therefore stands — a NAS that cached an older `:latest` still serves it, which is why
  the container's own output is the check, not the tag.
- Fixed a real bug found on the way: the script's push error check sat after `docker logout` and read
  *logout's* exit code, so a failed push reported "successfully built, tagged, and pushed" and printed
  the YAML to redeploy anyway. Each push is checked now and the script aborts.
- Verified by building: labels and `/app/BUILD_INFO` agree, and the image's `requirements_sha256`
  (`4196120db1aa…`) equals the committed lock byte for byte.

## Lock resolver — pip-compile, not uv (2026-09-23, outside the milestone sequence)

uv was the resolver from M2 onward because it was already on the machine and pip-tools was not. It is
now dropped in favour of `pip-compile`, so the toolchain is miniconda + pip + one pip-based tool.

- **The lock is unchanged where it matters.** `pip-compile --strip-extras -o requirements.txt
  requirements.in` on the same interpreter reproduces all 54 pins exactly, case-insensitively — same
  versions, same resolution. Only the header and the sort order of the `# via` notes differ.
- **`--strip-extras` is not cosmetic.** Without it pip-compile writes `coverage[toml]==7.16.1`, and
  `gen_licenses.py`'s `read_lock` splits on `==` without parsing extras, so the name becomes
  `coverage[toml]`, the lookup against installed distributions fails, and the licence gate reports a
  package that is installed as missing. uv normalises extras away, which is why uv never showed this.
- **The header pip-compile writes is wrong on one point and must not be trusted as proof.** It always
  records `--no-index`, even when the flag was never passed: `get_compile_command` skips an option
  when `option.default == value`, and `--no-index`'s click default is `Sentinel.UNSET` while its value
  is `False`, so the comparison never matches and the flag is always emitted. Resolution is genuinely
  online — verified by compiling a `six` requirement on an interpreter where `six` is not installed,
  which resolved to the current 1.17.0 from PyPI.
- **pip-tools lives in the conda env, not in `requirements.in`.** Its arrival there is `build`,
  `setuptools`, `wheel` and `pyproject_hooks` (4 extra distributions); `click` and `pip` were already
  present. It must stay out of the lock, because the Dockerfile installs the lock and that would ship
  build tooling in the runtime image — the same objection M4's dropped split accepted for djlint, and
  a worse one here since these are pure build tools. `gen_licenses.py` iterates the lock's pins, so
  extra installed packages are invisible to `--check`; `pip check` stays silent with pip-tools
  installed, verified.
- **Plain pip can do this too, and was rejected on purpose.** `pip install --dry-run --ignore-installed
  --report -` on the same interpreter reproduces the lock exactly — 54 distributions, no additions, no
  removals, no version differences — and would leave the toolchain at miniconda + pip with nothing
  extra, at the cost of a bespoke generator script in the repo and a lock with no `# via` annotations.
  The annotations won: they are what made M3's dead `httpx`/`anyio`/`httpcore` chain visible at a
  glance. Do not re-open this; the extra packages are `pip-tools` plus `build`, `setuptools`, `wheel`
  and `pyproject_hooks`, all outside the lock and therefore outside the image.
- Nothing else used uv: the `Dockerfile` and CI both run `pip install -r requirements.txt`. uv is
  left installed on the host for other projects; this repo simply no longer asks for it.

## Deferred risk register

| risk | milestone | mitigation |
|---|---|---|
| Registering `CSRFProtect` breaks a POST that no test covers | M6 | land the `hidden_tag()`s first (inert until registration), add a CSRF-enabled test, manual pass over the 32 form-bearing templates |
| Lint gate becomes noise | M1 before M2 | rule set pinned, families adopted one at a time |
| Dev env irrecoverably broken | M0 | rebuild it from `requirements.txt` — the `opennourish-py39-backup` 3.9 clone was deleted on 2026-09-23 once the 3.12 image was confirmed deployed |
| `pip freeze` reintroduces drift | M2 | resolver command documented in `DEV-README.md` |
