# opennourish/auth — registration, login, verification, password reset

## Purpose

Account lifecycle: register, login, logout, e-mail verification, and password reset, plus the rules that decide who may register and who becomes an administrator.

## Ownership

- `routes.py` (212 lines, 7 routes): `login` L25, `logout` L63, `register` L69, `reset_password_request` L123, `reset_password/<token>` L146, `send-verification-email` L163, `verify-email/<token>` L186.
- `forms.py` (44 lines).
- Not owned here: token minting/verification lives on the model (`User.get_token` / `User.verify_token`, root `models.py`), mail sending in `opennourish/utils.py`, the `onboarding_required` gate in `opennourish/decorators.py` (its flow is owned by `opennourish/onboarding/`).

## Local Contracts

- Tokens are PyJWT HS256 signed with **`SECRET_KEY`**, not `ENCRYPTION_KEY`, and carry an expiry. Rotating `SECRET_KEY` invalidates every session, every outstanding reset link, and every verification link at once; `verify_token` returns `None` on any `PyJWTError` and the caller must treat that as "invalid or expired", never as a 500.
- Registration is gated by the `SystemSetting` row read through `utils.get_allow_registration_status()` (default: allow), not by an environment variable.
- Admin bootstrap has two paths and both must stay deliberate:
  - `INITIAL_ADMIN_USERNAME` grants admin to that username on login/registration.
  - With it unset, the **first registrant becomes admin** (`auth/routes.py:88-91`). On a fresh public deployment that is whoever signs up first. Keep the intended admin claim step documented before any public deploy.
- `ENABLE_PASSWORD_RESET` and `ENABLE_EMAIL_VERIFICATION` must be checked before sending mail and before honouring a verification-only action; both default to off, and `MAIL_SUPPRESS_SEND` defaults to `True`, so no mail leaves the process unless explicitly enabled.
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
