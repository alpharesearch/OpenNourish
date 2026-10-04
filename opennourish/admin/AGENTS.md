# opennourish/admin — administration and USDA curation

## Purpose

Instance-level controls: system stats, user management (verify, enable, key-user, public/private, onboarding), application settings, SMTP settings stored in the database, orphan-record cleanup, and — through the sibling `usda_admin` blueprint — curation of USDA portion rows.

## Ownership

- `admin/routes.py` (~580 lines, 17 routes): `index`, `dashboard`, `settings`, `email_settings`, `users`, ten user-toggle POST routes, `cleanup`, and the cleanup runner. Refer to them by name, never by line number.
- `opennourish/usda_admin/routes.py` (~200 lines, 5 routes): add/edit/delete/move-up/move-down of USDA portions. Governed by this doc; it has no doc of its own.
- `forms.py` (61 lines).
- Not owned here: the privilege flags themselves (`User`, root `models.py`), the decorators (`opennourish/decorators.py`).

## Local Contracts

- Every admin route is `@login_required` **and** `@admin_required`. Every USDA-admin route is `@login_required` **and** `@key_user_required` (admin implies key user). No exceptions, including the GET pages.
- Never trust the navbar to gate anything: the secondary admin bar in `_navbar.html` keys off `request.blueprint` only. The decorator is the gate.
- Users list must exclude disabled accounts from login but keep them visible and re-enableable. A user cannot disable themselves; that guard exists and must not regress.
- Mail settings: `email_settings` stores `MAIL_PASSWORD` encrypted in `SystemSetting` via `encrypt_value` with `current_app.config["ENCRYPTION_KEY"]`, and `config.get_setting_from_db` decrypts it at boot. Consequences to preserve:
  - `SystemSetting.value` is `String(100)` while a Fernet token for a ≥16-character password is 120 characters. SQLite tolerates it; any move to Postgres/MySQL needs the column widened first.
  - Rotating `ENCRYPTION_KEY` makes decryption fail, and `get_setting_from_db` swallows the error and returns an empty password, so SMTP silently loses credentials. Surface it rather than spreading the silent fallback.
  - The form must never echo the stored password back; it is masked when rendered.
- `MAIL_CONFIG_SOURCE` is a `SystemSetting` row written only by this `email_settings` save and read by `create_app`; it is not an environment variable, whatever `.env.example` appears to offer. Root's `AGENTS.md` owns which source wins.
- The cleanup runner is destructive: it removes rows orphaned by account deletion (foods, recipes, meals, portions). It must list what it will remove, require an explicit POST, and be idempotent.
- `ALLOW_REGISTRATION` and email-verification toggles are `SystemSetting` rows read through `utils.get_allow_registration_status()`, not environment variables. `Config.ALLOW_REGISTRATION` is a `@property` that Flask stores in `app.config` as a truthy object — never branch on `app.config["ALLOW_REGISTRATION"]`.
- USDA portion edits touch rows shared by every user; portion `seq_num` ordering and `gram_weight` must stay consistent, and re-seeding (`flask seed-usda-portions`) deletes rows flagged `was_imported` before re-importing, so non-curated edits are not durable.

## Work Guidance

- Route-level privilege tests exist (`test_admin.py`, `test_admin_users.py`, `test_usda_admin.py`); when adding a privileged route, add the negative case (non-admin / non-key-user) in the same change.
- Any admin action that changes another user's data should flash an outcome and record who did it if a durable audit trail is ever requested — there is none today.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_admin.py tests/test_admin_users.py tests/test_admin_features.py tests/test_admin_cleanup.py tests/test_user_management.py tests/test_usda_admin.py tests/test_admin_coverage.py
```

62 tests; `admin/routes.py` and `usda_admin/routes.py` are both at 100% (`tests/test_admin_coverage.py` carries the email-settings encryption round-trip and the negative privilege cases).

## Child DOX Index

No child docs. `opennourish/usda_admin/` is governed here.
