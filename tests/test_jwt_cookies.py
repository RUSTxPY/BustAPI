import pytest
from bustapi import JWT, BustAPI, jwt_required, make_response


@pytest.fixture
def app():
    app = BustAPI(__name__)
    app.secret_key = "test-secret-long-enough-for-jwt"

    jwt = JWT(
        app,
        token_location=["cookies"],
        access_cookie_name="access_token",
        refresh_cookie_name="refresh_token",
    )

    @app.post("/login")
    def login():
        access_token = jwt.create_access_token(identity="test_user")
        refresh_token = jwt.create_refresh_token(identity="test_user")
        resp = make_response({"login": True})
        jwt.set_access_cookies(resp, access_token)
        jwt.set_refresh_cookies(resp, refresh_token)
        return resp

    @app.get("/protected")
    @jwt_required
    def protected(request):
        return {"user": request.jwt_identity}

    @app.post("/logout")
    def logout():
        resp = make_response({"logout": True})
        jwt.unset_jwt_cookies(resp)
        return resp

    return app


def test_jwt_cookie_flow(app):
    client = app.test_client()

    # 1. Access protected without cookie -> 401
    resp = client.get("/protected")
    assert resp.status_code == 401

    # 2. Login -> Should set cookies
    resp = client.post("/login")
    assert resp.status_code == 200

    # Check cookies are in the response
    cookies = resp.headers.getlist("Set-Cookie")
    print(f"DEBUG: Cookies received: {cookies}")
    assert any("access_token=" in c for c in cookies)
    assert any("refresh_token=" in c for c in cookies)

    # 3. Access protected with cookie -> 200
    resp = client.get("/protected")
    assert resp.status_code == 200
    assert resp.json["user"] == "test_user"

    # 4. Logout -> Should clear cookies
    resp = client.post("/logout")
    assert resp.status_code == 200
    cookies = resp.headers.getlist("Set-Cookie")
    assert any("access_token=;" in c or "Max-Age=0" in c for c in cookies)

    # 5. Access protected again -> 401
    resp = client.get("/protected")
    assert resp.status_code == 401
