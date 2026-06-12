from bustapi import Blueprint, BustAPI
from bustapi.core.helpers import url_for


def test_blueprint_routes_in_url_map():
    app = BustAPI()
    bp = Blueprint("api", __name__, url_prefix="/api")

    @bp.route("/users", methods=["GET"])
    def get_users():
        return {"users": []}

    app.register_blueprint(bp)

    # Check if the route is in url_map
    assert "/api/users" in app.url_map
    assert app.url_map["/api/users"]["endpoint"] == "api.get_users"

    # Check if url_for works correctly
    from bustapi.testing import BustTestClient

    @app.route("/test")
    def test_url_for():
        return {"url": url_for("api.get_users")}

    with BustTestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json["url"] == "/api/users"
