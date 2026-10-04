# opennourish/auth — registration, login, verification, password reset

## Purpose

Account lifecycle: register, login, logout, e-mail verification, and password reset, plus the rules that decide who may register and who becomes an administrator.

## Ownership

- `routes.py` (~215 lines, 7 routes): `login`, `logout`, `register`, `reset_password_request`, `reset_password/<token>`, `send-verification-email`, `verify-email/<token>`. Refer to them by name, never by line number.
- `forms.py` — the login, register, and reset forms.
- Not owned here: token minting/verification lives on the model (`User.get_token` / `User.verify_token`, root `models.py`), mail sending in `opennourish/utils.py`, the `onboarding_required` gate in `opennourish/decorators.py` (its flow is owned by `opennourish/onboarding/`).

## Local Contracts

- Tokens are PyJWT HS256 signed with **`SECRET_KEY`**, not `ENCRYPTION_KEY`, and carry an expiry. Rotating `SECRET_KEY` invalidates every session, every outstanding reset link, and every verification link at once; `verify_token` returns `None` on any `PyJWTError` and the caller must treat that as "invalid or expired", never as a 500.
- Registration is gated by the `SystemSetting` row read through `utils.get_allow_registration_status()` (default: allow), not by an environment variable.
- Admin bootstrap has two paths and both must stay deliberate:
  - `INITIAL_ADMIN_USERNAME` grants admin to that username on login/registration.
  - With it unset, `register` makes the **first registrant admin**. On a fresh public deployment that is whoever signs up first. Keep the intended admin claim step documented before any public deploy.
- `ENABLE_PASSWORD_RESET` and `ENABLE_EMAIL_VERIFICATION` must be checked before sending mail and before honouring a verification-only action; both default to off, so no route here sends unless an administrator turned the feature on.
- **Suppression is not safe by default in a deployment.** `create_app` resolves it case-insensitively from whichever source is active — `os.getenv("MAIL_SUPPRESS_SEND", "True").lower() == "true"` in environment mode, `get_setting_from_db(app, "MAIL_SUPPRESS_SEND", default="True").lower() == "true"` in database mode — so the `True` default applies only when the key is **absent**: the empty value that `.env.example` and the generated TrueNAS YAML write when the field is left blank evaluates to `False`, and mail then really leaves the container. `MAIL_SUPPRESS_SEND=true` is what keeps it in-process. The admin form stores `str(bool)`, so `"True"` / `"False"` round-trip only because the comparison lower-cases — keep it case-insensitive. `create_app`'s `if app.testing` force does **not** protect a test run: that key is overwritten by the resolution block afterwards, so a testing app inherits the environment (`opennourish/AGENTS.md` owns the fix). Never assume a fresh host is silent — check the variable.
- Verification state is a privilege input, not a cosmetic flag: unverified users cannot send friend requests and their content is not exposed to friends. Do not grant a shortcut that sets `is_verified` from a user-facing form.
- Login must respect `User.is_active` (disabled accounts cannot authenticate) and must not reveal whether the account or the password was wrong.
- Password hashing is `werkzeug.security` (`generate_password_hash` / `check_password_hash`); do not compare hashes directly.
- Reset and verification e-mails use standalone fragments in `templates/email/` with `_external=True` URLs, so `ProxyFix` and the configured host must be correct or the links break.

## Work Guidance

- Tests patch `opennourish.utils.mail.send_message` to capture mail; the global conftest patch targets `flask_mailing.Mail.send_message`, which will not intercept these calls.
- Every token-consuming route needs three cases: valid, expired, and forged (wrong key). `test_email_verification.py` covers this surface; extend it rather than adding a parallel helper.
- Anonymisation and deletion of accounts is handled outside this blueprint (`opennourish/profile`, `opennourish/undo`, admin cleanup). Do not duplicate row-cleanup logic here.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -m pytest -m "not integration" -q tests/test_auth.py tests/test_email_verification.py tests/test_onboarding.py tests/test_account_deletion.py tests/test_retroactive_admin.py
```

## Child DOX Index

No child docs.
