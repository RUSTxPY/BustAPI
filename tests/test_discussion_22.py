from datetime import timedelta

import pytest
from bustapi import BustAPI, session


def test_session_permanent_outside_context():
    """Verify that accessing session.permanent outside of a request context raises a RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        session.permanent = True
    assert "Working outside of request context" in str(exc_info.value)

    with pytest.raises(RuntimeError) as exc_info:
        _ = session.permanent
    assert "Working outside of request context" in str(exc_info.value)


def test_session_permanent_inside_view():
    """Verify that setting session.permanent inside a request view works and correctly sets max_age/expires on the cookie."""
    app = BustAPI()
    app.secret_key = "test-secret"
    app.permanent_session_lifetime = timedelta(days=5)

    @app.route("/login")
    def login():
        session["user_id"] = 123
        session.permanent = True
        return "logged in"

    client = app.test_client()
    resp = client.get("/login")
    assert resp.status_code == 200

    cookie_header = resp.headers.get("Set-Cookie", "")
    assert "session=" in cookie_header
    assert "Max-Age=" in cookie_header or "expires=" in cookie_header.lower()


def test_session_permanent_in_before_request():
    """Verify that setting session.permanent in a before_request hook works."""
    app = BustAPI()
    app.secret_key = "test-secret"
    app.permanent_session_lifetime = timedelta(days=5)

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.route("/test")
    def test_route():
        session["foo"] = "bar"
        return "ok"

    client = app.test_client()
    resp = client.get("/test")
    assert resp.status_code == 200

    cookie_header = resp.headers.get("Set-Cookie", "")
    assert "session=" in cookie_header
    assert "Max-Age=" in cookie_header or "expires=" in cookie_header.lower()
