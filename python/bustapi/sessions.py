import base64
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from .bustapi_core import Signer
from .http.request import Request
from .http.response import Response


class SessionMixin(dict):
    """Mixin for dict-based sessions."""

    def __init__(self, initial=None):
        super().__init__(initial or {})
        self.modified = False
        self._permanent = False

    @property
    def permanent(self) -> bool:
        return self._permanent

    @permanent.setter
    def permanent(self, value: bool) -> None:
        self._permanent = value
        self.modified = True

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.modified = True

    def __delitem__(self, key):
        super().__delitem__(key)
        self.modified = True

    def clear(self):
        super().clear()
        self.modified = True

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.modified = True

    def pop(self, key, default=None):
        val = super().pop(key, default)
        self.modified = True
        return val


class SecureCookieSession(SessionMixin):
    """Secure cookie-based session."""

    pass


class NullSession(SessionMixin):
    """Session class used when sessions are disabled or support is missing."""

    pass


class SessionInterface(ABC):
    """Base class for session interfaces."""

    @abstractmethod
    def open_session(self, app, request: Request) -> Optional[SessionMixin]:
        """Load session from request."""
        pass

    @abstractmethod
    def save_session(self, app, session: SessionMixin, response: Response) -> None:
        """Save session to response."""
        pass


class SecureCookieSessionInterface(SessionInterface):
    """Default session interface using secure cookies (Rust-backed signing).

    Uses Rust for all serialization operations:
    - encode_session: Dict → JSON → Base64 → Sign (single Rust call)
    - decode_session: Verify → Base64 → JSON → Dict (single Rust call)
    """

    session_class = SecureCookieSession
    session_cookie_name = "session"

    def _get_signer(self, app):
        if not hasattr(app, "_session_signer"):
            app._session_signer = Signer(app.secret_key)
        return app._session_signer

    def open_session(self, app, request: Request) -> Optional[SessionMixin]:
        if not app.secret_key:
            return None

        # Value from cookie (signed string)
        val = request.cookies.get(self.session_cookie_name)
        if not val:
            return self.session_class()

        signer = self._get_signer(app)

        # Decode and verify in a single Rust call (JSON+Base64+HMAC)
        try:
            data = signer.decode_session(self.session_cookie_name, val)
            if data is None:
                return self.session_class()
            return self.session_class(data)
        except Exception:
            return self.session_class()

    def get_cookie_header_value(self, app, session: SessionMixin) -> Optional[str]:
        """Generate the Set-Cookie header value without needing a Response object."""
        domain = app.config.get("SESSION_COOKIE_DOMAIN")
        path = app.config.get("SESSION_COOKIE_PATH", "/")
        
        if not session and session.modified:
            parts = [f"{self.session_cookie_name}="]
            parts.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            if domain: parts.append(f"Domain={domain}")
            if path: parts.append(f"Path={path}")
            return "; ".join(parts)
            
        if not app.secret_key or not session.modified:
            return None
            
        signer = self._get_signer(app)
        val = signer.encode_session(self.session_cookie_name, dict(session))
        
        parts = [f"{self.session_cookie_name}={val}"]
        
        if session.permanent and app.permanent_session_lifetime:
            expires = datetime.utcnow() + app.permanent_session_lifetime
            expires_str = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires_str}")
            max_age = int(app.permanent_session_lifetime.total_seconds())
            parts.append(f"Max-Age={max_age}")
            
        parts.append("HttpOnly")
        if domain: parts.append(f"Domain={domain}")
        if path: parts.append(f"Path={path}")
        if app.config.get("SESSION_COOKIE_SECURE", False):
            parts.append("Secure")
        
        samesite = app.config.get("SESSION_COOKIE_SAMESITE", "Lax")
        if samesite:
            parts.append(f"SameSite={samesite}")
            
        return "; ".join(parts)

    def save_session(self, app, session: SessionMixin, response: Response) -> None:
        val = self.get_cookie_header_value(app, session)
        if val:
            response.headers.add("Set-Cookie", val)
