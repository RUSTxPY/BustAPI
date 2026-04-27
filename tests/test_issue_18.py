import os
import shutil

import pytest
from bustapi import BustAPI, render_template


@pytest.fixture
def app():
    app = BustAPI(import_name="test_app")

    # Setup templates
    template_dir = os.path.join(os.getcwd(), "templates_test_18")
    os.makedirs(template_dir, exist_ok=True)
    with open(os.path.join(template_dir, "err.html"), "w") as f:
        f.write(
            "<html><body><h1>Error {{ status_code }}</h1><p>{{ message }}</p></body></html>"
        )

    app.template_folder = template_dir

    @app.errorhandler(404)
    def page_not_found(e):
        return (
            render_template(
                "err.html", **{"status_code": 404, "message": "Custom 404 Page"}
            ),
            404,
        )

    @app.route("/")
    def index():
        return "Home"

    yield app

    # Cleanup
    shutil.rmtree(template_dir, ignore_errors=True)


def test_custom_404_handler(app):
    with app.test_client() as client:
        # Test valid route
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.text == "Home"

        # Test invalid route - should trigger custom handler
        resp = client.get("/non-existent")
        assert resp.status_code == 404
        assert "Custom 404 Page" in resp.text
        assert "<h1>Error 404</h1>" in resp.text


def test_default_500_handler(app):
    @app.route("/error")
    def cause_error():
        raise ValueError("Something went wrong")

    with app.test_client() as client:
        resp = client.get("/error")
        assert resp.status_code == 500
        assert "Internal Server Error" in resp.text
