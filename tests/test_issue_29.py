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


def test_blueprint_advanced_features():
    app = BustAPI()
    bp = Blueprint("api", __name__, url_prefix="/api")

    # 1. Relative url_for
    @bp.route("/users")
    def get_users():
        return {"users": []}

    @bp.route("/url")
    def get_url():
        return {"url": url_for(".get_users")}

    # 2. Before request, after request, teardown request
    hook_runs = []
    @bp.before_request
    def bp_before():
        hook_runs.append("before")

    @bp.after_request
    def bp_after(response):
        hook_runs.append("after")
        return response

    @bp.teardown_request
    def bp_teardown(exc):
        hook_runs.append("teardown")

    # 3. Blueprint error handler
    @bp.errorhandler(400)
    def bp_handle_400(e):
        return {"error": "bp_400"}, 400

    @bp.route("/trigger_400")
    def trigger_400():
        from bustapi import abort
        abort(400)

    # 4. App-wide decorators registered on blueprint
    @bp.before_app_request
    def bp_before_app():
        hook_runs.append("before_app")

    @bp.after_app_request
    def bp_after_app(response):
        hook_runs.append("after_app")
        return response

    @bp.teardown_app_request
    def bp_teardown_app(exc):
        hook_runs.append("teardown_app")

    @bp.app_errorhandler(401)
    def bp_handle_401(e):
        return {"error": "app_401"}, 401

    app.register_blueprint(bp)

    @app.route("/trigger_401")
    def trigger_401():
        from bustapi import abort
        abort(401)

    from bustapi.testing import BustTestClient

    with BustTestClient(app) as client:
        # Test relative url_for and hooks
        hook_runs.clear()
        res = client.get("/api/url")
        assert res.status_code == 200
        assert res.json["url"] == "/api/users"
        assert "before" in hook_runs
        assert "before_app" in hook_runs
        assert "after" in hook_runs
        assert "after_app" in hook_runs

        # Test bp error handler
        res = client.get("/api/trigger_400")
        assert res.status_code == 400
        assert res.json["error"] == "bp_400"

        # Test app-wide error handler registered on bp
        res = client.get("/trigger_401")
        assert res.status_code == 401
        assert res.json["error"] == "app_401"
