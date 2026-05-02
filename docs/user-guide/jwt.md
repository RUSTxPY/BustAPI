# JWT Authentication

BustAPI provides Rust-backed JWT (JSON Web Token) authentication for high-performance token-based auth. This is ideal for stateless APIs and mobile backends.

## Quick Start

```python
from bustapi import BustAPI, JWT, jwt_required

app = BustAPI(__name__)
app.secret_key = "your-secret-key"

# Initialize JWT
jwt = JWT(app)

@app.post("/login")
def login():
    # Create an access token for a user
    token = jwt.create_access_token(identity="user123")
    return {"access_token": token}

@app.get("/protected")
@jwt_required
def protected(request):
    # Identity is available on the request object
    return {"user": request.jwt_identity}
```

## Configuration Options

The `JWT` class supports various configuration options for security and flexibility.

```python
jwt = JWT(
    app,
    secret_key="optional-override",  # Uses app.secret_key if not set
    algorithm="HS256",               # HS256, HS384, HS512
    access_expires=900,              # 15 minutes (seconds)
    refresh_expires=2592000,         # 30 days (seconds)
    
    # Token Storage Location
    token_location="headers",        # "headers", "cookies", or ["headers", "cookies"]
    
    # Cookie Settings (if using cookies)
    access_cookie_name="access_token_cookie",
    refresh_cookie_name="refresh_token_cookie",
    cookie_secure=False,             # Set True in production (HTTPS)
    cookie_httponly=True,            # Prevent JS access to cookies
    cookie_samesite="Lax",           # "Strict", "Lax", or "None"
)
```

## Using Cookies

Using cookies instead of the `Authorization` header is often more secure for web applications as it prevents XSS attacks from stealing tokens (when using `HttpOnly`).

### 1. Enable Cookie Support

```python
jwt = JWT(app, token_location=["headers", "cookies"])
```

### 2. Set Cookies in Login

```python
from bustapi import make_response

@app.post("/login")
def login():
    access_token = jwt.create_access_token(identity="user123")
    refresh_token = jwt.create_refresh_token(identity="user123")
    
    resp = make_response({"login": True})
    
    # Set tokens in cookies
    jwt.set_access_cookies(resp, access_token)
    jwt.set_refresh_cookies(resp, refresh_token)
    
    return resp
```

### 3. Clear Cookies on Logout

To log out a user, use `jwt.unset_jwt_cookies()`. This will correctly clear both access and refresh cookies from the response, ensuring the user is fully logged out.

```python
@app.post("/logout")
def logout():
    resp = make_response({"logout": True})
    # This now robustly handles security flags like httponly and samesite
    jwt.unset_jwt_cookies(resp)
    return resp
```

!!! tip "Full Example"
    See a complete working example in [examples/security/18_jwt_cookies.py](https://github.com/RUSTxPY/BustAPI/blob/main/examples/security/18_jwt_cookies.py).

## Creating Tokens

```python
# Access token (for API access)
token = jwt.create_access_token(
    identity="user123",
    expires_delta=3600,      # Custom expiry in seconds (optional)
    fresh=True,              # Fresh token from login
    claims={"role": "admin"} # Custom claims (optional)
)

# Refresh token (for getting new access tokens)
refresh = jwt.create_refresh_token(identity="user123")
```

## Decoding & Manual Verification

```python
# Decode and verify (raises ValueError if invalid/expired)
claims = jwt.decode_token(token)
# Returns: {"identity": "user123", "exp": ..., "iat": ..., "type": "access"}

# Verify only (returns bool)
is_valid = jwt.verify_token(token)

# Get identity without verification (works even on expired tokens)
identity = jwt.get_identity(token)
```

## Decorators

Decorators provide a declarative way to protect your routes. When a token is verified, it sets `request.jwt_identity` and `request.jwt_claims` for the current request.

### @jwt_required

Require a valid JWT. Looks in the locations specified in `token_location` (Default: `Authorization: Bearer <token>` header).

```python
@app.get("/protected")
@jwt_required
def protected(request):
    user_id = request.jwt_identity  # User identity string
    claims = request.jwt_claims     # All token claims (dict)
    return {"user": user_id}
```

### @jwt_optional

Allow both authenticated and anonymous access. If no token or an invalid token is provided, `request.jwt_identity` will be `None`.

```python
@app.get("/feed")
@jwt_optional
def feed(request):
    if request.jwt_identity:
        return {"feed": "personalized for " + request.jwt_identity}
    return {"feed": "public"}
```

### @fresh_jwt_required

Require a **fresh** token. Fresh tokens are typically those created during a login operation (`fresh=True`), while tokens created via a refresh operation are usually marked as non-fresh.

```python
@app.post("/change-password")
@fresh_jwt_required
def change_password(request):
    # Only allow with fresh token (security sensitive)
    return {"status": "password changed"}
```

### @jwt_refresh_token_required

Require a **refresh token**. This is used on the endpoint that issues new access tokens.

```python
@app.post("/refresh")
@jwt_refresh_token_required
def refresh(request):
    # Use the identity from the refresh token to issue a new access token
    new_token = jwt.create_access_token(request.jwt_identity, fresh=False)
    
    resp = make_response({"access_token": new_token})
    
    # If using cookies, update the access cookie
    if "cookies" in jwt._token_location:
        jwt.set_access_cookies(resp, new_token)
        
    return resp
```

## Algorithms

| Algorithm | Description |
|-----------|-------------|
| HS256 | HMAC-SHA256 (default, recommended) |
| HS384 | HMAC-SHA384 |
| HS512 | HMAC-SHA512 |

## Error Responses

- `401 Missing JWT token` - No token provided in any configured location
- `401 Token has expired` - Token past expiration
- `401 Invalid token signature` - Wrong secret key
- `401 Fresh token required` - Need fresh token for sensitive operations
- `401 Refresh token required` - Wrong token type for refresh endpoint
