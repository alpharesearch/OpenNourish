# templates — Jinja presentation layer

## Purpose

Server-rendered Jinja markup for all 18 blueprints: one layout, 38 pages, 2 partials, 2 standalone email fragments. No build step; assets are vendored in `static/`.

## Ownership

- `base.html` (379 lines) — the only layout: head assets, flash area, navbar include, global `addItemModal`, timezone auto-detect, `_date_picker_modal.html` include.
- `_navbar.html`, `_date_picker_modal.html` — partials (leading `_`, no `extends`).
- `email/` — standalone fragments rendered by `opennourish/utils.py`; they use `_external=True` links and must stay self-contained HTML (no `extends`).
- Page templates in root and 13 blueprint subdirectories, all `{% extends "base.html" %}`.
- Not owned here: what the routes compute (`/opennourish/AGENTS.md`), the vendored asset files themselves (`static/`, root-owned).

## Local Contracts

- `base.html` exposes exactly three blocks: `title` (:6), `content` (:26), `scripts` (:99). The house style is to declare `{% block scripts %}` inside `{% block content %}` and call `{{ super() }}` — Jinja tolerates it, but every block must be closed exactly once and each name may be declared only once per template.
- Template syntax is not compiled at import time, so an unbalanced tag is a 500 at request time and a red dashboard test. After any structural edit, verify compilation:

  ```bash
  /home/markus/miniconda3/envs/opennourish/bin/python -c \
    "from jinja2 import Environment, FileSystemLoader as F; Environment(loader=F('templates')).get_template('dashboard.html')"
  ```

- Chart data crosses from Flask to JS only as inline `<script>` with `|tojson`. Chart.js v4.5.0 is already loaded globally by `base.html:11`; do not re-`<script src>` it (a stale re-load exists in `tracking/analytics.html:181`).
- CSRF: only Flask-WTF `FlaskForm` + `{{ form.hidden_tag() }}` is protected (29 occurrences in 20 templates). `CSRFProtect` is **not** registered globally, so the ~69 raw `<form method="post">` tags carry no token. Converting a raw form to a `FlaskForm`, or registering `CSRFProtect`, is the sanctioned way to close that gap — do not hand-roll a token field.
- URLs: `url_for` in markup; the only hardcoded paths are the two `fetch()` targets in `base.html` (`/api/get-remaining-calories/…`, `/search/api/get-portions/…`).
- Flash messages render only in `base.html:16-25`; categories are Bootstrap alert names (`success`, `danger`, `info`, `warning`).
- Read-only mode: `dashboard.html` and `diary/diary.html` are also rendered by the profile blueprint with `is_read_only=True`. Every edit affordance in those two files must stay guarded by it.
- Units: branch on `current_user.measurement_system` (`metric` / `us`) and use the conversion helpers from `opennourish/utils.py` in Python rather than duplicating factors like `2.20462` in inline JS.
- Timestamps: use the `user_time` filter (user-timezone aware). `user_date` exists but is unused; raw `date.strftime(...)` is acceptable only for plain dates.
- Theme: `data-bs-theme` comes from `current_user.theme_preference`; `navbar_preference` is injected as raw CSS classes into `_navbar.html:1` — keep it a class list, never markup.
- Reuse is thin by design: 2 includes and one macro (`render_pagination`, defined inside `search/search.html`). Promote a macro to its own file only when a second template needs it.

## Work Guidance

- Analytics charts have one canonical owner: `templates/tracking/analytics.html` plus `opennourish/tracking/analytics.py`. `dashboard.html` in the working tree currently pastes a verbatim copy of those five cards (lines 505-618) and their init scripts (851-1137). Do not extend that copy; extract a partial that both pages include, or delete it from the dashboard.
- The analytics copy-paste is also the reason `dashboard.html` does not compile right now: `{% block scripts %}` is declared twice (767 and 1269), `{% block content %}` (5) is never closed, and `{% endif %}` at 1268 is orphaned. The last committed version (945 lines) compiles. Fix all three, not just the reported line — Jinja only surfaces the first.
- `dashboard.html` references a `bodyCompositionChart` canvas that does not exist in that file; the scroll script targeting it is dead. Remove or point it at a real id.
- Keep inline `<script>` in templates only for chart init bound to page data (the current pattern); anything reusable belongs in `static/`. `static/style.css` is 155 lines and holds the few shared overrides, including dark-theme rules.

## Verification

```bash
P=/home/markus/miniconda3/envs/opennourish/bin/python
$P -c "from jinja2 import Environment, FileSystemLoader as F; e=Environment(loader=F('templates')); [e.get_template(t) for t in ['dashboard.html','diary/diary.html','tracking/analytics.html','base.html']]"
$P -m pytest -m "not integration" -q tests/test_dashboard.py tests/test_diary.py tests/test_analytics.py
```

`tests/test_main_routes.py` and the profile tests also render these templates, so template breakage shows up as unrelated red tests — check the traceback line number, it points at the template.

## Child DOX Index

No child docs.
