import pytest
from bustapi import BustAPI, redirect


def test_sync_before_request_redirect():
    """Verify that returning a redirect from a synchronous before_request hook works without raising RuntimeError."""
    app = BustAPI()
    app.secret_key = "test-secret"

    @app.before_request
    def redirect_hook():
        return redirect("/target")

    @app.route("/")
    def index():
        return "Home"

    @app.route("/target")
    def target():
        return "Target"

    client = app.test_client()
    # This request should be intercepted by the redirect_hook and return 302
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/target"


def test_async_before_request_redirect():
    """Verify that returning a redirect from an asynchronous before_request hook also works correctly."""
    app = BustAPI()
    app.secret_key = "test-secret"

    @app.before_request
    async def redirect_hook():
        return redirect("/target")

    @app.route("/")
    def index():
        return "Home"

    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/target"
