# opennourish/dashboard — the day-at-a-glance aggregate

## Purpose

`/dashboard/` and `/dashboard/<log_date_str>`: today's or a chosen day's intake vs goals, meal breakdown, exercise, fasting status, weight trend, and read-only friend dashboards.

## Ownership

- `routes.py` (274 lines) contains a single handler, `index()` L39 — 236 lines — plus the date variant route.
- Not owned here: the analytics datasets it currently also computes (owned by `opennourish/tracking/AGENTS.md`), the aggregation helpers in `opennourish/utils.py`, the template (`templates/dashboard.html`).

## Local Contracts

- `@login_required` + `@onboarding_required` (L37-38). A test client whose user has not completed onboarding is redirected to onboarding and every content assertion silently passes — use the `auth_client_onboarded` fixture.
- The day is user-local: `get_user_today(current_user.timezone)` and `get_start_of_week(...)`; the optional `log_date_str` segment must be parsed defensively and never fall back to `date.today()`.
- Goal-less users must still get a 200 with a sane page; there is no hard dependency on a `UserGoal` row.
- `is_read_only` is passed through to the template when a friend's dashboard is rendered via the profile blueprint; all edit affordances depend on it.
- Keep the render context keys the template consumes stable, and add new ones through `context_processors.py` only when they are truly global.
- FDA scaled daily values (2,000 kcal basis) are computed in this handler for the nutrient cards; that scaling belongs here or in `utils.py`, not in the template.

## Work Guidance

- Do not grow `index()` with more cards. The working tree currently calls seven functions from `opennourish/tracking/analytics.py` and passes six extra datasets, while `templates/dashboard.html` pastes a copy of the analytics page markup. That duplication is the current breakage source; the fix direction is one owner per dataset — either drop the analytics block from the dashboard or extract a shared partial and compute the data once.
- The dashboard already renders a 30-day window per request; any new dataset must be a single aggregate query or a batched one, not a per-day loop of ORM lookups.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -c "from jinja2 import Environment, FileSystemLoader as F; Environment(loader=F('templates')).get_template('dashboard.html')"
$P -m pytest -m "not integration" -q tests/test_dashboard.py tests/test_weight_projection.py tests/test_fasting.py
```

Dashboard tests are the widest blast radius in the suite: 21 tests across 9 files render this template, so a template error looks like admin, onboarding, and profile failures.

## Child DOX Index

No child docs.
