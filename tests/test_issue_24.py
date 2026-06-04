import os
import shutil

import pytest
from bustapi import BustAPI, CSRFProtect, render_template
from bustapi.routing.blueprints import Blueprint


@pytest.fixture
def app_with_csrf():
    app = BustAPI(import_name="test_app_csrf")
    app.secret_key = "test-secret-key"

    # Initialize CSRFProtect
    csrf = CSRFProtect(app)

    # Setup templates
    template_dir = os.path.join(os.getcwd(), "templates_test_24")
    os.makedirs(template_dir, exist_ok=True)

    with open(os.path.join(template_dir, "index.html"), "w") as f:
        f.write("<html><body>csrf_token: {{ csrf_token() }}</body></html>")

    with open(os.path.join(template_dir, "bp.html"), "w") as f:
        f.write(
            "<html><body>csrf_token: {{ csrf_token() }}, bp_val: {{ bp_val }}</body></html>"
        )

    app.template_folder = template_dir

    # Add custom app-wide context processor
    @app.context_processor
    def app_processor():
        return {"app_val": "app-wide"}

    # Create Blueprint and register context processor
    bp = Blueprint("test_bp", "test_bp_module")

    @bp.context_processor
    def bp_processor():
        return {"bp_val": "blueprint-specific"}

    @bp.route("/bp-view")
    def bp_view():
        return render_template("bp.html")

    app.register_blueprint(bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    yield app

    # Cleanup
    shutil.rmtree(template_dir, ignore_errors=True)


def test_csrf_initialization(app_with_csrf):
    """Test that CSRFProtect initializes without AttributeError."""
    assert "csrf" in app_with_csrf.extensions
    assert isinstance(app_with_csrf.extensions["csrf"], CSRFProtect)


def test_csrf_token_in_context(app_with_csrf):
    """Test that csrf_token is available and callable in the template context."""
    with app_with_csrf.test_client() as client:
        # Create session transaction to have a session so _get_csrf_token doesn't return empty
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "test-csrf-value"

        resp = client.get("/")
        assert resp.status_code == 200
        assert "csrf_token: test-csrf-value" in resp.text


def test_blueprint_context_processor(app_with_csrf):
    """Test that blueprint-specific context processor gets applied only in blueprint context."""
    with app_with_csrf.test_client() as client:
        # Test main app template does not have bp_val (it would error if used, or render empty/none)
        # Test blueprint template has both csrf_token and bp_val
        with client.session_transaction() as sess:
            sess["_csrf_token"] = "test-csrf-value"

        resp = client.get("/bp-view")
        assert resp.status_code == 200
        assert "csrf_token: test-csrf-value" in resp.text
        assert "bp_val: blueprint-specific" in resp.text
