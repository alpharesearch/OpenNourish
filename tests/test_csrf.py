"""CSRF enforcement — `CSRFProtect` registered in `create_app` (PLAN.md M6.1).

`tests/conftest.py` builds the shared app with `WTF_CSRF_ENABLED = False` so that form tests
can POST freely, which also means the rest of the suite cannot see whether CSRF works at all:
on that fixture a rejection never happens and a missing token never matters. Every behavioural
test here therefore builds its own app with the flag left at its default, and the two
source-level tests pin the invariants that make enforcement survivable — a token in every
POST form, and a header on the one POST that no form submits.
"""

import pathlib
import re

import pytest
from flask import url_for

from models import User, db
from opennourish import create_app

TEMPLATE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "templates"

FORM_OPEN = re.compile(r"<form\b[^>]*>", re.IGNORECASE)
IS_POST = re.compile(r"""method\s*=\s*["']?\s*post""", re.IGNORECASE)
HAS_TOKEN = re.compile(
    r"""hidden_tag\(\)|name\s*=\s*["']csrf_token["']""", re.IGNORECASE
)


@pytest.fixture
def csrf_app():
    """A real app with CSRF left on — the only way to observe the gate.

    `create_app(dict)` replaces `config.Config` wholesale, so anything the production class
    sets for CSRF has to be repeated here; `WTF_CSRF_TIME_LIMIT` is the one that matters, and
    `test_real_config_...` in `test_config.py` pins that the shipped value matches.
    """
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"usda": "sqlite:///:memory:"},
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "SECRET_KEY": "test_secret_key",
            "ALLOW_REGISTRATION": True,
            "SERVER_NAME": "localhost.localdomain:5000",
            "WTF_CSRF_TIME_LIMIT": None,
        }
    )
    with app.app_context():
        db.create_all()
        user = User(username="csrfuser", email="csrfuser@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        app.config["CSRF_TEST_USER_ID"] = user_id
        yield app
        db.session.remove()
        db.drop_all()


def _login(app, client):
    with client.session_transaction() as sess:
        sess["_user_id"] = app.config["CSRF_TEST_USER_ID"]
        sess["_fresh"] = True


def _url(app, endpoint):
    """Resolve from the endpoint name. The URL is hyphenated (`/settings/set-timezone`)
    while the function is not, and a hand-typed path would 404 — which silently skips the
    check, because `CSRFProtect` returns as soon as it sees no endpoint matched."""
    with app.app_context():
        return url_for(endpoint)


def _token_from(client, path="/auth/login"):
    """Scrape the token out of a rendered page, the way a browser gets it."""
    page = client.get(path)
    match = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"|name="csrf-token" content="([^"]+)"',
        page.data.decode(),
    )
    assert match, f"no CSRF token rendered by {path}"
    return next(group for group in match.groups() if group)


def test_csrf_protect_is_registered_on_the_app(csrf_app):
    hooks = csrf_app.before_request_funcs.get(None) or []
    assert any(getattr(f, "__name__", "") == "csrf_protect" for f in hooks)


def test_a_post_without_a_token_is_rejected(csrf_app):
    client = csrf_app.test_client()

    response = client.post(
        "/auth/login", data={"username": "csrfuser", "password": "password"}
    )

    assert response.status_code == 400


def test_a_post_with_the_rendered_token_is_accepted(csrf_app):
    """The other half of the gate: a token minted by a page of ours must work, or every
    form in the application has just been turned into a 400."""
    client = csrf_app.test_client()
    token = _token_from(client)

    response = client.post(
        "/auth/login",
        data={
            "username": "csrfuser",
            "password": "password",
            "csrf_token": token,
        },
    )

    assert response.status_code != 400


def test_a_wrong_token_is_rejected(csrf_app):
    client = csrf_app.test_client()

    response = client.post(
        "/auth/login",
        data={
            "username": "csrfuser",
            "password": "password",
            "csrf_token": "not-a-real-token",
        },
    )

    assert response.status_code == 400


def test_a_json_post_is_rejected_without_the_header(csrf_app):
    """`CSRFProtect` looks in the form fields and then in two headers — never in a JSON
    body — which is why the timezone probe in `base.html` has to send `X-CSRFToken`."""
    client = csrf_app.test_client()
    _login(csrf_app, client)

    response = client.post(
        _url(csrf_app, "settings.set_timezone"),
        json={"timezone": "Europe/Berlin"},
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_a_json_post_with_the_header_is_accepted(csrf_app):
    client = csrf_app.test_client()
    _login(csrf_app, client)
    token = _token_from(client, "/settings/")

    response = client.post(
        _url(csrf_app, "settings.set_timezone"),
        json={"timezone": "Europe/Berlin"},
        headers={"Content-Type": "application/json", "X-CSRFToken": token},
    )

    assert response.status_code == 200
    with csrf_app.app_context():
        user = User.query.filter_by(username="csrfuser").one()
        assert user.timezone == "Europe/Berlin"


def test_get_requests_stay_open():
    """Not a tautology: registering the protector makes it tempting to assume GET is fine.
    `WTF_CSRF_METHODS` defaults to POST/PUT/DELETE/PATCH, and the email-verification link is
    a GET that a mail client cannot turn into a POST."""
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_BINDS": {"usda": "sqlite:///:memory:"},
            "SECRET_KEY": "test_secret_key",
            "SERVER_NAME": "localhost.localdomain:5000",
        }
    )
    with app.app_context():
        db.create_all()
    assert app.test_client().get("/auth/login").status_code == 200


def test_every_post_form_in_the_tree_carries_a_token():
    """The invariant that makes the gate deployable: a form added tomorrow without a token
    is a form that 400s for every user, and no test would notice on the shared fixture.

    Both accepted shapes are Flask-WTF's own — `hidden_tag()` where a `FlaskForm` is in
    context, the hidden input elsewhere. A token generated by this repo is not a third
    option (`templates/AGENTS.md`)."""
    unguarded = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        text = path.read_text()
        for open_tag in FORM_OPEN.finditer(text):
            if not IS_POST.search(open_tag.group(0)):
                continue
            end = text.find("</form>", open_tag.end())
            body = text[open_tag.end() : end if end != -1 else len(text)]
            if not HAS_TOKEN.search(body):
                line = text[: open_tag.start()].count("\n") + 1
                unguarded.append(f"{path.relative_to(TEMPLATE_ROOT.parent)}:{line}")

    assert not unguarded, f"POST forms with no CSRF token: {unguarded}"


def test_the_base_layout_publishes_the_token_for_scripts():
    """`set_timezone` is the only POST the app makes outside a form, so the meta tag and the
    header are a matched pair — lose either and the timezone auto-detect silently 400s."""
    base = (TEMPLATE_ROOT / "base.html").read_text()

    assert '<meta name="csrf-token" content="{{ csrf_token() }}">' in base
    assert "'X-CSRFToken'" in base
    assert "querySelector('meta[name=\"csrf-token\"]')" in base
