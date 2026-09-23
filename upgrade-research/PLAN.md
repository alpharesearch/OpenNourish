# Migration plan — Python 3.12, dependency refresh, tooling gates

Target interpreter: **Python 3.12** (security-supported to 2028-10-31).
Evidence behind the numbers: [`README.md`](README.md). Candidate locks live in this folder until the
milestone that consumes them lands, and are deleted once `requirements.txt` supersedes them.

**Status as of 2026-09-23: M0, M1, M2, M2b and M4's CI step have landed. M3, M4's split and M5 are pending.**
Landed state: conda env `opennourish` and both Docker stages are on 3.12, `requirements.in` drives a
generated `requirements.txt` (61 packages, was 72), `ruff.toml` pins its rule families, the image's
`typst` is 0.15.1, `.github/workflows/ci.yml` runs the four gates on every push and PR, and every gate
is green — 972 tests passed, `ruff check` clean, `ruff format --check` clean, djlint advisory at 204
findings. `THIRD-PARTY-LICENSES.md` is no longer hand-maintained: `gen_licenses.py` generates it from
the installed wheels plus the vendored assets in `static/`, and `--check` fails if it drifts.

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

## M2 — Prune, regenerate the lock, bump the image to 3.12 — LANDED (cold-volume boot still owed)

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
   adopted lock file in this folder was deleted once `requirements.txt` carried it;
   `Flask-Mailing==0.2.3` stays pinned **in `requirements.in`**, with the reason inline. Keep dev
   tooling in the same file until M4 splits it.
4. **Fix the regeneration recipe in `DEV-README.md:352-355`.** `pip freeze > requirements.txt` is
   how the file drifted; replace with a resolver command:
   `uv pip compile requirements.in --python-version 3.12 -o requirements.txt --generate-hashes`
   (or `pip-compile`), and record that `pip check` must stay silent.
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
- ✅ Image smoke test, bypassing the entrypoint: interpreter 3.12.14, `pip check` silent, `typst
  0.13.1` present, `python -m compileall` parses every module, and `create_app()` boots with 133
  routes registered. Run it with `--entrypoint python`, never by appending a command: `ENTRYPOINT`
  is `entrypoint.sh`, which downloads the 474 MB USDA archive before it ever reaches your arguments.
- ⬜ **Still owed:** one cold start on a real volume, so `entrypoint.sh` runs its seed steps under
  3.12 (`safe_upgrade.sh`, `seed-usda-portions`, `seed-usda-categories`, `seed-exercise-activities`,
  `seed-dev-data`), plus a nutrition-label PDF render through the `typst` subprocess. Do this on the
  TrueNAS host or against a copied volume; the seed code is untouched by this migration, so the
  residual risk is interpreter behaviour inside those scripts, not the scripts themselves.

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

## M3 — Flask-Mailing 3.0.0 (first app-code change)

`Mail.init_app` in 3.0.0 hard-requires `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`; this app
deliberately runs with them empty (`opennourish/__init__.py:148-152`, DB-loaded with `default=""`).

1. Give the three keys non-empty fallbacks in `create_app` before `mail.init_app(app)`, or skip
   mail init when no server is configured — the latter keeps `USE_CREDENTIALS = False` honest and is
   the preferred shape.
2. Keep the two send sites (`opennourish/utils.py:68,86`) — `Message(subject=…, recipients=[…], html=…)`
   and `asyncio.run(mail.send_message(msg))` are unchanged in 3.0.0 (verified against installed
   signatures).
3. Adopt [`lock-py312-flaskmailing-3.0.0.txt`](lock-py312-flaskmailing-3.0.0.txt) (54 packages).
   This is the milestone that finally drops the mail chain — `aioredis` (abandoned 2021), `httpx`,
   `httpcore`, `h11`, `anyio`, `certifi`, `async-timeout` — which is also what removes the
   **CRITICAL** `anyio` CVE-2026-63374 from the image entirely.
4. Send a real verification email against a live SMTP account before merging to the deployment
   branch: the suite covers `MAIL_SUPPRESS_SEND`, not the wire format.

**Verify:** full suite green (972); manual signup + password-reset mail round-trip; `pip check`.
**Rollback:** revert the `create_app` guard and `requirements.in`/`requirements.txt`.
**Do not skip:** AGENTS.md warns that `ENCRYPTION_KEY` rotation invalidates the stored
`MAIL_PASSWORD` — after this change, re-enter mail credentials in the admin settings page once.

## M4 — Runtime/dev split, then CI — CI LANDED (2026-09-23), split pending

1. **`.github/workflows/ci.yml` — landed early, pulled ahead of the split** so M3, the first
   app-code change in this plan, lands under automated gates rather than manual discipline. It
   installs the one flat `requirements.txt` on 3.12, runs `pip check`, then all four gates. djlint is
   absent by design. Each gate step carries `if: ${{ !cancelled() }}` so one push reports everything
   that is broken, not just the first failure. It needs `SECRET_KEY` plus an `ENCRYPTION_KEY`
   shaped like a real Fernet key — generated per run into `$GITHUB_ENV`, because `config.py` only
   fails at import if the value is absent, and a placeholder string would survive import and then
   fail at the `MAIL_PASSWORD` decrypt call site.
2. Split `requirements.in` into runtime and `requirements-dev.in`; Dockerfile installs runtime only.
   `Faker` stays runtime (the boot-time `seed-dev-data` uses it). This has a licensing reason, not
   just size: **djlint is GPL-3.0-or-later** and ships in the distributed image today, along with
   its `cssbeautifier`/`jsbeautifier`/`EditorConfig`/`json5`/`pathspec`/`regex` closure.
3. When the split lands, CI installs runtime + dev instead of the flat lock — the only change the
   workflow needs.

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

- **`datetime.utcnow()` — 13 call sites.** Deprecated on 3.12, scheduled for removal, and the
  source of `DTZ011` noise. Migrate to `datetime.now(timezone.utc)` in line with
  `opennourish/time_utils.py`; this is the largest remaining behaviour-adjacent edit, so give it its
  own commit and read the timezone rules in `opennourish/AGENTS.md` first.
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
- **Unrelated but adjacent:** `.dockerignore` still lets `htmlcov/` and `.kilocode/` into every
  image, and `deploy_truenas.sh` prints `SECRET_KEY`/`ENCRYPTION_KEY`/`MAIL_PASSWORD` to stdout and
  only works from a directory named `opennourish`. Fix while you are in deployment-land.

## Deferred risk register

| risk | milestone | mitigation |
|---|---|---|
| Image boots into a loop on a fresh volume | M2 | boot with an empty volume before deploying; `set -e` makes failures loud |
| Mail silently stops sending | M3 | live SMTP round-trip test; `MAIL_SUPPRESS_SEND` hides failures in CI |
| Lint gate becomes noise | M1 before M2 | rule set pinned, families adopted one at a time |
| Dev env irrecoverably broken | M0 | `opennourish-py39-backup` clone |
| `pip freeze` reintroduces drift | M2 | resolver command documented in `DEV-README.md` |
