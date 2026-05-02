"""
Example: JWT Authentication with Cookies in BustAPI

This example demonstrates how to use JWT with HttpOnly cookies for
enhanced security against XSS attacks.

Run:
    python examples/security/18_jwt_cookies.py

Test with:
    # 1. Login (Sets cookies in browser)
    curl -v -X POST http://localhost:5000/login -H "Content-Type: application/json" \
         -d '{"username": "admin", "password": "secret123"}'

    # 2. Access protected route (Cookies are automatically sent by browser)
    # Using curl: extract the cookie from the login response and pass it:
    curl -v http://localhost:5000/protected --cookie "access_token_cookie=<token>"

    # 3. Logout (Clears cookies)
    curl -v -X POST http://localhost:5000/logout
"""

from bustapi import (
    JWT,
    BustAPI,
    hash_password,
    jwt_required,
    make_response,
    verify_password,
)

app = BustAPI(__name__)
app.secret_key = "your-super-secret-key"

# Initialize JWT with cookie support
jwt = JWT(
    app,
    token_location=["cookies"],  # Only look in cookies
    cookie_secure=False,  # Set True in production with HTTPS
    cookie_httponly=True,  # JS cannot access token
    cookie_samesite="Lax",
)

# Simulated user database
USERS = {
    "admin": hash_password("secret123"),
}


@app.post("/login")
def login(request):
    """Login and set JWT in HttpOnly cookies."""
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    stored_hash = USERS.get(username)
    if not stored_hash or not verify_password(password, stored_hash):
        return {"error": "Invalid credentials"}, 401

    # Create tokens
    access_token = jwt.create_access_token(identity=username)
    refresh_token = jwt.create_refresh_token(identity=username)

    # Create response and set cookies
    resp = make_response({"message": "Successfully logged in"})
    jwt.set_access_cookies(resp, access_token)
    jwt.set_refresh_cookies(resp, refresh_token)

    return resp


@app.get("/protected")
@jwt_required
def protected(request):
    """Protected route - automatically extracts JWT from cookies."""
    return {
        "message": f"Hello, {request.jwt_identity}!",
        "auth_method": "HttpOnly Cookie",
    }


@app.post("/logout")
def logout():
    """Logout by clearing JWT cookies."""
    resp = make_response({"message": "Successfully logged out"})
    jwt.unset_jwt_cookies(resp)
    return resp


if __name__ == "__main__":
    print("JWT Cookie Authentication Example")
    print("-" * 40)
    print("Endpoints:")
    print("  POST /login     - Sets HttpOnly cookies")
    print("  GET  /protected - Requires valid cookies")
    print("  POST /logout    - Clears cookies")
    print("-" * 40)
    app.run(debug=True)
