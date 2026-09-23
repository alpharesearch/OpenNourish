# Dependency and Python version research — 2026-09-23

Baseline audited: `requirements.txt` (72 pinned distributions), conda env `opennourish` on
Python 3.9.23, `Dockerfile` on `python:3.9` / `python:3.9-slim`.

## Verdict

1. **Yes — leave Python 3.9.** It has been end-of-life since **2025-10-31** (11 months without
   security patches), and five advisories in the shipped set are now **structurally unfixable**
   on 3.9 because every patched release declares `requires_python >= 3.10`.
2. Target **Python 3.12** (security-supported to 2028-10-31, and the version this research
   validated end to end). Nothing in the current pin set blocks it: the existing
   `requirements.txt` installs unmodified under 3.12.
3. Take the dependency upgrade in the same change: **48 of 72 pins are behind**, and the full
   suite (**972 passed**) is already green on 3.12 with every package at its latest release.

## 1. Python version

| release | latest patch | active support ends | security support ends |
|---|---|---|---|
| 3.14 | 3.14.7 | 2027-10-01 | 2030-10-31 |
| 3.13 | 3.13.15 | 2026-10-01 (now) | 2029-10-31 |
| **3.12** | 3.12.14 | ended 2025-04-02 | **2028-10-31** |
| 3.11 | 3.11.16 | ended 2024-04-01 | 2027-10-31 |
| 3.10 | 3.10.21 | ended 2023-04-05 | 2026-10-31 (≈5 weeks) |
| **3.9** | 3.9.25 | ended 2022-05-17 | **ended 2025-10-31** |

([endoflife.date/python](https://endoflife.date/python))

### The blocking argument: 3.9 has reached its upgrade ceiling

These advisories affect the shipped set, and no 3.9-compatible release contains the fix:

| package | pinned | fixed in | fixed release needs | exposure |
|---|---|---|---|---|
| anyio | 4.9.0 | 4.14.2 | ≥3.10 | **CVE-2026-63374 CRITICAL** — TLS certificate spoofing |
| aiosmtplib | 4.0.1 | 5.1.1 / 5.1.2 | ≥3.10 | CVE-2026-53533 SMTP command injection, CVE-2026-55558 STARTTLS response injection |
| click | 8.1.8 | 8.3.3 | ≥3.10 | CVE-2026-7246 (no 3.9-compatible fix exists at all) |
| python-dotenv | 1.1.1 | 1.2.2 | ≥3.10 | CVE-2026-28684 symlink following → arbitrary file overwrite |
| pytest | 8.4.1 | 9.0.3 | ≥3.10 | CVE-2025-71176 tmpdir handling (dev-only) |

`aiosmtplib` is the one that matters operationally: it is the SMTP client this app sends
password-reset and verification mail through (`opennourish/utils.py:68,86`). `click` and
`python-dotenv` are unconditional runtime imports of every Flask container. `anyio` reaches the
image only through the unused `httpx` chain — which is itself an argument for §3.

Also note `cryptography` 50.0.1 declares `!=3.9.0,!=3.9.1,>=3.9`: staying on 3.9 puts a
**patch-level floor** on the interpreter (≥3.9.2) just to take crypto fixes.

### 3.9 also freezes whole libraries

| library | pinned | latest | gap |
|---|---|---|---|
| djlint | 1.36.4 | 1.46.2 | 10 minor releases frozen by `requires_python >=3.10` at 1.37.0 |
| Faker | 25.8.0 | 40.39.0 | 15 majors |
| alembic | 1.16.2 | 1.20.0 | |
| Flask-WTF | 1.2.2 | 1.3.0 | |
| pytest | 8.4.1 | 9.1.1 | 1 major |

The `AGENTS.md` note that djlint is pinned for 3.9 reasons is correct today and becomes moot on
3.10+ — the pin should be removed as part of the move, not kept.

### Why 3.12 rather than 3.13/3.14

- **3.12** is validated here (972 passed, two dependency profiles) and has security support to
  2028-10-31. It is also the interpreter available on the host (`/usr/bin/python3.12`) and in the
  local conda package cache (3.12.12), so `python:3.12-slim` and the dev env line up.
- **3.13** only buys one extra year of security support while dropping to security-only status on
  2026-10-01; it is a fine follow-up but has no advantage worth re-validating for right now.
- **3.14** is the longest runway (2030-10-31) and key tools already declare 3.14/3.15 support
  (`djlint 1.46.2`, `pytest 9.1.1`, `SQLAlchemy 2.0.54`, `cryptography 50.0.1`, `greenlet 3.5.6`).
  Budget it as the next refresh once 3.12 is shipping.

## 2. Security fixes that are needed regardless of interpreter version

Scanned every installed version against OSV (`api.osv.dev`): **13 of 64 distributions carry open
advisories**. All of these fixes *do* install on 3.9:

| package | pinned | fix needed | max on 3.9 |
|---|---|---|---|
| cryptography | 45.0.5 | 46.0.5 / 46.0.6 / 46.0.7 / 48.0.1 / 49.0.0 / 50.0.0 | 50.0.1 ✔ (4 HIGH: Bleichenbacher oracle, SECT subgroup attack, path-building DoS, bundled OpenSSL) |
| PyJWT | 2.10.1 | 2.12.0, 2.13.0 | 2.15.0 ✔ (2 HIGH: `crit` header acceptance, JWK-as-HMAC-secret forgery) |
| Mako | 1.3.10 | 1.3.11, 1.3.12 | 1.3.12 ✔ (2 HIGH path traversal, Windows `TemplateLookup` only) |
| Werkzeug | 3.1.3 | 3.1.4, 3.1.5, 3.1.6 | 3.1.8 ✔ (3 `safe_join` advisories, Windows-only impact) |
| Flask | 3.1.1 | 3.1.3 | 3.1.3 ✔ (CVE-2026-27205 missing `Vary: Cookie`) |
| idna | 3.10 | 3.15 | 3.20 ✔ |
| certifi | 2025.7.14 | — | 2026.7.22 ✔ (14-month-old CA bundle) |

The `Mako`/`Werkzeug` advisories are Windows-path-traversal class and this deployment is Linux on
TrueNAS, so they are not exploitable here — but they are free to clear. `cryptography` and `PyJWT`
are the ones to treat as urgent: this app uses Fernet for `MAIL_PASSWORD` at rest and `SECRET_KEY`
HMAC for reset/verification tokens.

## 3. Prune first — roughly a fifth of the file is dead weight

Resolved the graph from installed metadata with roots = modules the repo actually imports:

| remove | why |
|---|---|
| `aioredis==2.0.1` | abandoned project (last release 2021-12-27), imported nowhere; pulled in only as a `Flask-Mailing 0.2.3` requirement |
| `httpx`, `httpcore`, `h11`, `anyio`, `sniffio`, `certifi` | `httpx` is imported nowhere — it is a `Flask-Mailing 0.2.3` requirement. This chain is what makes the *CRITICAL* anyio advisory reachable in the image at all |
| `soupsieve` | no requirers and no `import` — `beautifulsoup4` is not even installed |
| `SQLAlchemy-Utils` | no requirers, no `sqlalchemy_utils` reference anywhere in `*.py` or templates |
| `pytz` | installed (2025.2) but not even listed in `requirements.txt`; the app uses stdlib `zoneinfo`. Pure environment drift |
| `importlib_metadata`, `zipp` | `Flask` requires `importlib_metadata` only on `python_version < "3.10"` — they disappear with the interpreter bump |
| `tomli`, `exceptiongroup`, `async-timeout` | backports needed only below 3.11 / 3.11 |
| `six`, `python-dateutil` | only reachable via `Faker → python-dateutil`; `Faker 40.x` dropped that dependency |

`Flask-Mailing 0.2.3` is the single largest dependency tax in the file: 12 distributions
(`aioredis`, `httpx` + its chain, `asgiref`, `pydantic`, `pydantic-settings`, `annotated-types`,
`pydantic_core`, `email-validator`, `typing-extensions`, `blinker`) exist because of it. It has
been unmaintained since 2023-09, and its successor `3.0.0` (2025-11-29) requires ≥3.10 — another
reason the interpreter bump unlocks the prune. See §6.1 for the one code change that migration
needs.

**Sequencing caveat:** none of this is removable by hand while `Flask-Mailing==0.2.3` is still
pinned — a resolver re-adds whatever its metadata requires. `soupsieve`, `SQLAlchemy-Utils` and the
`pytz` env drift go immediately; `aioredis` and the `httpx` chain only leave with the 3.0.0
migration (`PLAN.md` M3).

**Drift found while auditing:** the conda env is not what `requirements.txt` describes.
`djlint`, `colorama`, `cssbeautifier`, `jsbeautifier`, `EditorConfig`, `json5`, `pathspec`,
`regex`, `tqdm` are all absent, so the documented template-lint command
(`$P -m djlint templates …`) currently fails with `No module named djlint`; `pytz` is present but
unpinned. Re-creating the env from a regenerated lock file fixes both directions.

## 4. Full upgrade surface (48 of 72 pins are behind)

Sorted with security-relevant, 3.9-blocked rows first. “max on 3.9” is the newest release whose
`requires_python` still admits 3.9.

| package | pinned | max on 3.9 | latest | note |
|---|---|---|---|---|
| anyio | 4.9.0 | 4.12.1 | 4.15.1 | **CRITICAL** TLS spoofing; latest requires ≥3.10 |
| soupsieve | 2.7 | 2.8.4 | 2.9.2 | 2 HIGH (unused pkg); latest requires ≥3.10 |
| aiosmtplib | 4.0.1 | 4.0.2 | 5.1.3 | SMTP injection ×2; latest requires ≥3.10 |
| python-dotenv | 1.1.1 | 1.2.1 | 1.2.3 | symlink overwrite; latest requires ≥3.10 |
| Mako | 1.3.10 | 1.3.12 | 1.4.3 | 2 HIGH (Windows); latest requires ≥3.10 |
| click | 8.1.8 | 8.1.8 | 8.5.0 | CVE-2026-7246; latest requires ≥3.10 |
| pytest | 8.4.1 | 8.4.2 | 9.1.1 | tmpdir (dev); latest requires ≥3.10 |
| PyJWT | 2.10.1 | 2.15.0 | 2.15.0 | 2 HIGH / 6 advisories |
| cryptography | 45.0.5 | 50.0.1 | 50.0.1 | 4 HIGH / 7 advisories |
| Flask | 3.1.1 | 3.1.3 | 3.1.3 | CVE-2026-27205 |
| idna | 3.10 | 3.20 | 3.20 | CVE-2026-45409 |
| Werkzeug | 3.1.3 | 3.1.8 | 3.1.8 | 3 × safe_join |
| Pygments | 2.19.2 | 2.21.0 | 2.21.0 | ReDoS (dev) |
| Faker | 25.8.0 | 37.12.0 | 40.39.0 | latest requires ≥3.10 |
| Flask-Mailing | 0.2.3 | 0.2.3 | 3.0.0 | latest requires ≥3.10 |
| Flask-WTF | 1.2.2 | 1.2.2 | 1.3.0 | latest requires ≥3.10 |
| WTForms | 3.2.1 | 3.2.1 | 3.2.2 | latest requires ≥3.10 |
| alembic | 1.16.2 | 1.16.5 | 1.20.0 | latest requires ≥3.10 |
| annotated-types | 0.7.0 | 0.7.0 | 0.8.0 | latest requires ≥3.10 |
| asgiref | 3.9.1 | 3.11.1 | 3.12.1 | latest requires ≥3.10 |
| cffi | 1.17.1 | 2.0.0 | 2.1.1 | latest requires ≥3.10 |
| coverage | 7.10.0 | 7.10.7 | 7.16.1 | latest requires ≥3.10 |
| djlint | 1.36.4 | 1.36.4 | 1.46.2 | latest requires ≥3.10 |
| dnspython | 2.7.0 | 2.7.0 | 2.8.0 | latest requires ≥3.10 |
| greenlet | 3.2.3 | 3.2.5 | 3.5.6 | latest requires ≥3.10 |
| importlib_metadata | 8.7.0 | 8.7.1 | 9.0.1 | latest requires ≥3.10 |
| iniconfig | 2.1.0 | 2.1.0 | 2.3.0 | latest requires ≥3.10 |
| pycparser | 2.22 | 2.23 | 3.0 | latest requires ≥3.10 |
| pydantic-settings | 2.10.1 | 2.11.0 | 2.15.0 | latest requires ≥3.10 |
| pydantic_core | 2.33.2 | 2.46.5 | 2.49.0 | latest requires ≥3.10 |
| regex | 2026.1.15 | 2026.1.15 | 2026.9.10 | latest requires ≥3.10 |
| typing-inspection | 0.4.1 | 0.4.2 | 0.4.4 | latest requires ≥3.10 |
| zipp | 3.23.0 | 3.23.1 | 4.1.0 | latest requires ≥3.10 |
| MarkupSafe | 3.0.2 | 3.0.3 | 3.0.3 | — |
| PyYAML | 6.0.1 | 6.0.3 | 6.0.3 | — |
| SQLAlchemy | 2.0.41 | 2.0.54 | 2.0.54 | — |
| SQLAlchemy-Utils | 0.41.1 | 0.42.1 | 0.42.1 | — |
| WTForms-SQLAlchemy | 0.3 | 0.4.2 | 0.4.2 | — |
| certifi | 2025.7.14 | 2026.7.22 | 2026.7.22 | — |
| email_validator | 2.2.0 | 2.3.0 | 2.3.0 | — |
| exceptiongroup | 1.3.0 | 1.3.1 | 1.3.1 | — |
| packaging | 25.0 | 26.3 | 26.3 | — |
| pydantic | 2.11.7 | 2.13.5 | 2.13.5 | — |
| pytest-cov | 6.2.1 | 7.1.0 | 7.1.0 | — |
| pytest-mock | 3.14.1 | 3.15.1 | 3.15.1 | — |
| ruff | 0.5.5 | 0.16.8 | 0.16.8 | — |
| tomli | 2.2.1 | 2.4.1 | 2.4.1 | — |
| typing_extensions | 4.14.0 | 4.16.0 | 4.16.0 | — |

## 5. Verification — what was actually run

Every claim above is from a run on this machine on 2026-09-23, not from release notes.

| profile | interpreter | dependency set | suite | lint gates |
|---|---|---|---|---|
| baseline | 3.9.23 (conda `opennourish`) | the 72-pin `requirements.txt` of that day | **972 passed**, 1 deselected, 175 warnings | `ruff check` clean, `ruff format --check` clean |
| A — security patch, stay on 3.9 | 3.9.23 | 3.9 ceiling set, 79 pkgs (artifact deleted once 3.9 was abandoned) | not run (resolution verified only) | — |
| B — **adopted** | 3.12.3 | 61 pkgs, everything latest except Flask-Mailing — this is the live `requirements.txt` today | **972 passed**, 1 deselected, 290 warnings | see §6 |
| C — target end state | 3.12.3 | `lock-py312-flaskmailing-3.0.0.txt` (54 pkgs, *everything* latest) | **972 passed** — once `MAIL_SERVER`/`MAIL_USERNAME`/`MAIL_PASSWORD` are present | see §6 |

The current pinned file also installs unmodified under 3.12 (`pip install --dry-run` resolves all
72 entries), so the interpreter bump and the dependency bump are separable commits.

## 6. Real costs — the four things that are not free

1. **Flask-Mailing 0.2.3 → 3.0.0 is not drop-in.** `Mail.init_app` now hard-validates
   `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_SERVER` and raises
   `ValueError: Missing required configuration` — 916 test errors until satisfied. This collides
   with a deliberate design choice: `opennourish/__init__.py:148-152` sets
   `USE_CREDENTIALS = False` when credentials are absent, and mail settings load from the DB with
   `default=""`. The fix is to give those three keys non-empty fallbacks before `mail.init_app`,
   or to skip mail init when no server is configured. `Message(...)` kwargs and
   `asyncio.run(mail.send_message(msg))` are unchanged (verified against the installed 3.0.0
   signatures); only two call sites exist.
   **Do profile B first, then C separately** — it isolates the mail migration from the version bump.
2. **`ruff 0.5.5 → 0.16.8` turns a green gate red: 372 findings** (136 auto-fixable). Nothing in
   the code got worse — ruff's *default* rule set expanded (confirmed with `--isolated`, no
   project config). Top offenders: `I001` 124 (import sorting), `DTZ011` 108, `RUF059` 65,
   `BLE001` 13, `DTZ003/001/005` 30. Pin the current behaviour explicitly before upgrading:
   add `[lint] select = ["E4", "E7", "E9", "F"]` to `ruff.toml`, then adopt rule families one at
   a time. `ruff format --check` also wants 8 files reformatted.
3. **`datetime.utcnow()` — 13 call sites.** Deprecated in 3.12 and scheduled for removal; it is
   the bulk of the warning increase (1 DeprecationWarning at baseline → 14 on 3.12, plus
   flask_login's own uses). Not a blocker today, but it will become a hard failure eventually,
   and `DTZ011` will keep firing until it is fixed. Migrate to timezone-aware
   `datetime.now(timezone.utc)` alongside the timezone work already in `opennourish/time_utils.py`.
4. **`pytest-flask 1.3.0` is stale** (classifiers stop at 3.9, last release 2023-10). It does work
   on pytest 9 here, but it is the one dev dependency with no maintenance behind it — budget to
   drop it in favour of plain fixtures.

Advisory template lint under djlint 1.46.2: 204 findings across 43 templates — same shape as the
~230 documented for 1.36.4, so the `AGENTS.md` advisory framing still holds; the pin comment and
the "last release supporting Python 3.9" rationale should be deleted when 3.12 lands.

## 7. What became of this recommendation

Superseded — [`PLAN.md`](PLAN.md) owns the sequencing and the live status. Short version: steps 2–4
and 6 landed the same day, as M0–M2 (`requirements.in` + a generated 61-package
`requirements.txt`, conda env and both Docker stages on 3.12, ruff rule set pinned). Steps 1 and 5
are M3, and step 7 is M5.

One correction to this section as first written: step 1 over-promised. Deleting `aioredis` and the
`httpx` chain from `requirements.txt` by hand accomplishes nothing while
`Flask-Mailing==0.2.3` is still pinned — the resolver re-adds them from its metadata, so 11
packages left at M2 and the remaining 7 leave at M3.

## Files in this folder

The audit ran against the **pre-move** state. M0–M2 landed the same day, so two of the candidate
locks below were consumed and deleted; see `PLAN.md` for current status.

| file | what it is |
|---|---|
| [`PLAN.md`](PLAN.md) | the sequenced migration plan (M0–M5) and the live status record |
| `lock-py312-flaskmailing-3.0.0.txt` | 54 packages, **test-verified green** on 3.12, needs the §6.1 mail-config fallback — this is the M3 target that removes the `aioredis`/`httpx` chain |

`requirements.in` now lives at the repo root as the hand-edited dependency surface. The 61-package
M2 lock and the 3.9-ceiling lock were deleted once `requirements.txt` superseded the first and the
interpreter move made the second moot.

None of these are wired into the build; `requirements.txt`, `Dockerfile`, and the conda env are
untouched by this research.

**Docs:** only the root `AGENTS.md` Child DOX Index changed, to record that this folder exists and
carries no authority over the Toolchain contract. `opennourish/AGENTS.md`, `templates/AGENTS.md`,
`tests/AGENTS.md`, and `migrations/AGENTS.md` were left unchanged — no blueprint, template,
fixture, or migration contract moved. The Toolchain section's djlint claims (the 1.36.4 pin, its
transitive deps shipping in the image) are still accurate for the code as it stands and must be
rewritten when step 3 or 4 of §7 is actually applied, not before.
