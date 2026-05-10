"""
BustAPI JWT Extension

High-performance JWT support with Rust backend.
Supports both Header and Cookie-based token storage.
"""

from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

from .http.request import request
from .http.response import Response


class JWT:
    """
    JWT extension for BustAPI.

    Provides JWT-based authentication with Rust-backed encoding/decoding.
    """

    def __init__(
        self,
        app=None,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_expires: int = 900,  # 15 minutes
        refresh_expires: int = 2592000,  # 30 days
        token_location: Union[str, List[str]] = "headers",
        access_cookie_name: str = "access_token_cookie",
        refresh_cookie_name: str = "refresh_token_cookie",
        cookie_secure: bool = False,
        cookie_httponly: bool = True,
        cookie_samesite: Optional[str] = "Lax",
    ):
        """
        Initialize JWT extension.

        Args:
            app: BustAPI application instance
            secret_key: Secret key for signing tokens (uses app.secret_key if not provided)
            algorithm: Algorithm to use (HS256, HS384, HS512)
            access_expires: Access token expiry in seconds (default: 15 min)
            refresh_expires: Refresh token expiry in seconds (default: 30 days)
            token_location: Where to look for tokens ("headers", "cookies", or ["headers", "cookies"])
            access_cookie_name: Name of the access token cookie
            refresh_cookie_name: Name of the refresh token cookie
            cookie_secure: Whether cookies require HTTPS
            cookie_httponly: Whether cookies are inaccessible to JavaScript
            cookie_samesite: SameSite attribute for cookies
        """
        self._app = None
        self._manager = None
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_expires = access_expires
        self._refresh_expires = refresh_expires

        # Cookie settings
        if isinstance(token_location, str):
            self._token_location = [token_location]
        else:
            self._token_location = token_location

        self._access_cookie_name = access_cookie_name
        self._refresh_cookie_name = refresh_cookie_name
        self._cookie_secure = cookie_secure
        self._cookie_httponly = cookie_httponly
        self._cookie_samesite = cookie_samesite

        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        """Initialize with application instance."""
        from .bustapi_core import JWTManager

        self._app = app
        app.extensions["jwt"] = self

        # Use provided secret or app's secret
        secret = self._secret_key or app.secret_key
        if not secret:
            raise ValueError(
                "JWT requires a secret key. Set app.secret_key or pass secret_key to JWT()"
            )

        self._manager = JWTManager(
            secret,
            self._algorithm,
            self._access_expires,
            self._refresh_expires,
        )

    def create_access_token(
        self,
        identity: Union[str, int],
        expires_delta: Optional[int] = None,
        fresh: bool = True,
        claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create an access token."""
        if self._manager is None:
            raise RuntimeError("JWT not initialized. Call init_app() first.")

        return self._manager.create_access_token(
            str(identity), expires_delta, fresh, claims
        )

    def create_refresh_token(
        self,
        identity: Union[str, int],
        expires_delta: Optional[int] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a refresh token."""
        if self._manager is None:
            raise RuntimeError("JWT not initialized. Call init_app() first.")

        return self._manager.create_refresh_token(str(identity), expires_delta, claims)

    def set_access_cookies(self, response: Response, encoded_access_token: str) -> None:
        """Set access token in cookies on the response."""
        response.set_cookie(
            self._access_cookie_name,
            encoded_access_token,
            max_age=self._access_expires,
            secure=self._cookie_secure,
            httponly=self._cookie_httponly,
            samesite=self._cookie_samesite,
        )

    def set_refresh_cookies(
        self, response: Response, encoded_refresh_token: str
    ) -> None:
        """Set refresh token in cookies on the response."""
        response.set_cookie(
            self._refresh_cookie_name,
            encoded_refresh_token,
            max_age=self._refresh_expires,
            secure=self._cookie_secure,
            httponly=self._cookie_httponly,
            samesite=self._cookie_samesite,
        )

    def unset_jwt_cookies(self, response: Response) -> None:
        """Unset all JWT cookies on the response."""
        response.delete_cookie(
            self._access_cookie_name,
            secure=self._cookie_secure,
            httponly=self._cookie_httponly,
            samesite=self._cookie_samesite,
        )
        response.delete_cookie(
            self._refresh_cookie_name,
            secure=self._cookie_secure,
            httponly=self._cookie_httponly,
            samesite=self._cookie_samesite,
        )

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify a token."""
        if self._manager is None:
            raise RuntimeError("JWT not initialized. Call init_app() first.")

        return self._manager.decode_token(token)

    def verify_token(self, token: str) -> bool:
        """Verify a token without decoding."""
        if self._manager is None:
            return False

        return self._manager.verify_token(token)

    def get_identity(self, token: str) -> Optional[str]:
        """Get identity from token (works even on expired tokens)."""
        if self._manager is None:
            return None

        return self._manager.get_identity(token)


# Global JWT instance for decorators
_jwt_instance: Optional[JWT] = None


def _get_jwt() -> JWT:
    """Get the global JWT instance."""
    global _jwt_instance

    if _jwt_instance is not None:
        return _jwt_instance

    # Try to get from current app
    if request and hasattr(request, "app") and request.app:
        jwt_ext = request.app.extensions.get("jwt")
        if jwt_ext:
            return jwt_ext

    raise RuntimeError(
        "No JWT instance found. Initialize JWT(app) on your main application."
    )


def _get_token_from_request() -> Optional[str]:
    """Extract JWT from Authorization header or cookies."""
    jwt_ext = _get_jwt()
    locations = jwt_ext._token_location

    # 1. Try Headers
    if "headers" in locations:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

    # 2. Try Cookies
    if "cookies" in locations:
        token = request.cookies.get(jwt_ext._access_cookie_name)
        if token:
            return token

        token = request.cookies.get(jwt_ext._refresh_cookie_name)
        if token:
            return token

    return None


def _get_refresh_token_from_request() -> Optional[str]:
    """Specifically extract refresh token from request."""
    jwt_ext = _get_jwt()
    locations = jwt_ext._token_location

    if "headers" in locations:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

    if "cookies" in locations:
        return request.cookies.get(jwt_ext._refresh_cookie_name)

    return None


def jwt_required(fn: Callable) -> Callable:
    """Decorator to require a valid JWT token."""
    # Cache the abort import at decoration time
    from .core.exceptions import abort as _abort

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_token_from_request()

        if not token:
            _abort(401, "Missing JWT token")

        try:
            jwt_ext = _get_jwt()
            claims = jwt_ext.decode_token(token)

            if claims.get("type") == "refresh":
                _abort(401, "Access token required, not refresh token")

            request.jwt_identity = claims.get("identity")
            request.jwt_claims = claims

        except ValueError as e:
            _abort(401, str(e))

        return fn(*args, **kwargs)

    return wrapper


def jwt_optional(fn: Callable) -> Callable:
    """Decorator for optional JWT."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_token_from_request()

        request.jwt_identity = None
        request.jwt_claims = None

        if token:
            try:
                jwt_ext = _get_jwt()
                claims = jwt_ext.decode_token(token)
                request.jwt_identity = claims.get("identity")
                request.jwt_claims = claims
            except ValueError:
                pass

        return fn(*args, **kwargs)

    return wrapper


def fresh_jwt_required(fn: Callable) -> Callable:
    """Decorator to require a fresh JWT token."""
    from .core.exceptions import abort as _abort

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_token_from_request()

        if not token:
            _abort(401, "Missing JWT token")

        try:
            jwt_ext = _get_jwt()
            claims = jwt_ext.decode_token(token)

            if not claims.get("fresh", False):
                _abort(401, "Fresh token required")

            request.jwt_identity = claims.get("identity")
            request.jwt_claims = claims

        except ValueError as e:
            _abort(401, str(e))

        return fn(*args, **kwargs)

    return wrapper


def jwt_refresh_token_required(fn: Callable) -> Callable:
    """Decorator to require a refresh token."""
    from .core.exceptions import abort as _abort

    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = _get_refresh_token_from_request()

        if not token:
            _abort(401, "Missing Refresh token")

        try:
            jwt_ext = _get_jwt()
            claims = jwt_ext.decode_token(token)

            if claims.get("type") != "refresh":
                _abort(401, "Refresh token required")

            request.jwt_identity = claims.get("identity")
            request.jwt_claims = claims

        except ValueError as e:
            _abort(401, str(e))

        return fn(*args, **kwargs)

    return wrapper
