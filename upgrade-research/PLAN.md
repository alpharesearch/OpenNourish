# Migration plan — Python 3.12, dependency refresh, tooling gates

Target interpreter: **Python 3.12** (security-supported to 2028-10-31).
Evidence behind the numbers: [`README.md`](README.md). Candidate locks live in this folder until the
milestone that consumes them lands, and are deleted once `requirements.txt` supersedes them.

**Status as of 2026-09-23: M0, M1 and M2 have landed. M3, M4 and M5 are pending.**
Landed state: conda env `opennourish` and both Docker stages are on 3.12, `requirements.in` drives a
generated `requirements.txt` (61 packages, was 72), `ruff.toml` pins its rule families, and every
gate is green — 972 tests passed, `ruff check` clean, `ruff format --check` clean, djlint advisory
at 204 findings.

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

## M4 — Runtime/dev split, then CI

1. Split `requirements.in` into runtime and `requirements-dev.in`; Dockerfile installs runtime only.
   `Faker` stays runtime (the boot-time `seed-dev-data` uses it).
2. Add `.github/workflows/ci.yml`: `python-version: "3.12"`, install runtime + dev, run the three
   gates, `-m "not integration"`. CI must export `SECRET_KEY` and `ENCRYPTION_KEY` — `config.py`
   raises at import without them, which is exactly what bit the first 3.12 spike.
3. Do not gate djlint: 204 advisory findings would make CI red on day one.

**Verify:** the workflow goes green on a throwaway branch before it protects `main`.

## M5 — Follow-up cleanup (tracked, not blocking)

- **`datetime.utcnow()` — 13 call sites.** Deprecated on 3.12, scheduled for removal, and the
  source of `DTZ011` noise. Migrate to `datetime.now(timezone.utc)` in line with
  `opennourish/time_utils.py`; this is the largest remaining behaviour-adjacent edit, so give it its
  own commit and read the timezone rules in `opennourish/AGENTS.md` first.
- **Adopt ruff rules family by family** (`I001` 124, then `DTZ011` 108 with the utcnow work, then
  `RUF059` 65, `BLE001` 13) instead of a 372-finding big bang.
- **`pytest-flask`** works on pytest 9 but has been unmaintained since 2023-10 (classifiers stop at
  3.9). Replace with plain fixtures when convenient.
- **`THIRD-PARTY-LICENSES.md`** is already incomplete per AGENTS.md and goes further stale with
  these version moves — regenerate it in the same pass as M2 if you want it kept at all.
- **Next interpreter refresh: 3.14** (security to 2030-10-31). `djlint 1.46.2`, `pytest 9.1.1`,
  `SQLAlchemy 2.0.54`, `cryptography 50.0.1`, `greenlet 3.5.6` all declare 3.14/3.15 support.
  Re-run M0/M2 verification rather than assuming it carries over.
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
