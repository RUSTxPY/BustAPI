import json
from collections import UserDict
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote


class Headers(UserDict):
    """
    Case-insensitive dict-like object for HTTP headers.
    Supports multiple values for the same key.
    """

    def __init__(self, headers=None):
        self._key_map: Dict[str, str] = {}
        super().__init__()
        if headers:
            if hasattr(headers, "items"):
                for k, v in headers.items():
                    if isinstance(v, list):
                        for item in v:
                            self.add(k, item)
                    else:
                        self.add(k, v)
            elif isinstance(headers, (list, tuple)):
                for k, v in headers:
                    self.add(k, v)

    def __setitem__(self, key: str, value: Any):
        lower_key = str(key).lower()
        if lower_key in self._key_map:
            # Delete the old key with original casing
            super().__delitem__(self._key_map[lower_key])

        self._key_map[lower_key] = key
        super().__setitem__(key, value)

    def __getitem__(self, key: str):
        lower_key = str(key).lower()
        if lower_key in self._key_map:
            return super().__getitem__(self._key_map[lower_key])
        raise KeyError(key)

    def __delitem__(self, key: str):
        lower_key = str(key).lower()
        if lower_key in self._key_map:
            super().__delitem__(self._key_map[lower_key])
            del self._key_map[lower_key]
        else:
            raise KeyError(key)

    def __contains__(self, key: Any) -> bool:
        if not isinstance(key, str):
            return False
        return key.lower() in self._key_map

    def get(self, key: str, default: Any = None) -> Any:
        lower_key = str(key).lower()
        if lower_key in self._key_map:
            return super().get(self._key_map[lower_key], default)
        return default

    def add(self, key: str, value: str):
        """Add a header, preserving existing values for the same key."""
        lower_key = str(key).lower()
        if lower_key in self._key_map:
            actual_key = self._key_map[lower_key]
            existing = super().__getitem__(actual_key)
            if not isinstance(existing, list):
                existing = [existing]

            if isinstance(value, list):
                existing.extend(value)
            else:
                existing.append(value)
            super().__setitem__(actual_key, existing)
        else:
            self._key_map[lower_key] = key
            super().__setitem__(key, value)

    def getlist(self, key: str) -> List[str]:
        val = self.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]

    def setlist(self, key: str, values: List[str]):
        self[key] = values

    def items(self) -> List[Tuple[str, str]]:
        """Return (key, value) pairs, flattening multi-value headers."""
        res = []
        for key, value in super().items():
            if isinstance(value, list):
                for v in value:
                    res.append((key, str(v)))
            else:
                res.append((key, str(value)))
        return res

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return self[key]

    def __repr__(self) -> str:
        return str(dict(self.items()))


ResponseType = Union[str, bytes, dict, list, tuple, "Response"]


class Response:
    """
    Flask-compatible response object.
    """

    def __init__(
        self,
        response: Any = None,
        status: Optional[int] = None,
        headers: Optional[Union[Dict, Headers, List[Tuple[str, str]]]] = None,
        mimetype: Optional[str] = None,
        content_type: Optional[str] = None,
    ):
        self.status_code = status or 200
        if isinstance(headers, Headers):
            self.headers = headers
        else:
            self.headers = Headers(headers)

        if response is not None:
            self.set_data(response)
        else:
            self.data = b""

        if content_type:
            self.content_type = content_type
        elif mimetype:
            self.content_type = mimetype
        elif not self.headers.get("Content-Type"):
            self.content_type = "text/html; charset=utf-8"

    @property
    def status(self) -> str:
        try:
            status_obj = HTTPStatus(self.status_code)
            return f"{self.status_code} {status_obj.phrase}"
        except ValueError:
            return f"{self.status_code}"

    @status.setter
    def status(self, value: Union[str, int]) -> None:
        if isinstance(value, str):
            self.status_code = int(value.split()[0])
        else:
            self.status_code = value

    @property
    def content_type(self) -> str:
        return self.headers.get("Content-Type", "")

    @content_type.setter
    def content_type(self, value: str) -> None:
        self.headers["Content-Type"] = value

    def set_data(self, data: Any) -> None:
        if isinstance(data, Response):
            self.data = data.data
            for k, v in data.headers.items():
                self.headers.add(k, v)
            if not self.headers.get("Content-Type"):
                self.content_type = data.content_type
            return

        if isinstance(data, str):
            self.data = data.encode("utf-8")
            if not self.headers.get("Content-Type"):
                self.content_type = "text/html; charset=utf-8"
        elif isinstance(data, bytes):
            self.data = data
        elif isinstance(data, (dict, list)):
            self.data = json.dumps(data).encode("utf-8")
            self.content_type = "application/json"
        else:
            self.data = str(data).encode("utf-8")
            if not self.headers.get("Content-Type"):
                self.content_type = "text/html; charset=utf-8"

    def get_data(self, as_text: bool = False) -> Union[bytes, str]:
        if as_text:
            return self.data.decode("utf-8", errors="replace")
        return self.data

    @property
    def is_json(self) -> bool:
        return self.content_type.startswith("application/json")

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: Optional[int] = None,
        expires: Optional[Union[datetime, int, float]] = None,
        path: str = "/",
        domain: Optional[str] = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Optional[str] = None,
    ) -> None:
        cookie_val = f"{key}={quote(value)}"
        if max_age is not None:
            cookie_val += f"; Max-Age={max_age}"
        if expires is not None:
            if isinstance(expires, (int, float)):
                expires = datetime.now(timezone.utc) + timedelta(seconds=expires)
            cookie_val += f"; Expires={expires.strftime('%a, %d-%b-%Y %H:%M:%S GMT')}"
        if path:
            cookie_val += f"; Path={path}"
        if domain:
            cookie_val += f"; Domain={domain}"
        if secure:
            cookie_val += "; Secure"
        if httponly:
            cookie_val += "; HttpOnly"
        if samesite:
            cookie_val += f"; SameSite={samesite}"

        self.headers.add("Set-Cookie", cookie_val)

    def delete_cookie(
        self,
        key: str,
        path: str = "/",
        domain: Optional[str] = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Optional[str] = None,
    ) -> None:
        self.set_cookie(
            key=key,
            value="",
            max_age=0,
            expires=datetime.now(timezone.utc) - timedelta(days=1),
            path=path,
            domain=domain,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
        )


def redirect(location: str, code: int = 302) -> Response:
    """Create a redirect response."""
    return Response(None, status=code, headers={"Location": location})


def make_response(*args: Any) -> Response:
    if not args:
        return Response()
    if len(args) == 1:
        rv = args[0]
        if isinstance(rv, Response):
            return rv
        return Response(rv)
    if len(args) == 2:
        return Response(args[0], status=args[1])
    if len(args) == 3:
        return Response(args[0], status=args[1], headers=args[2])
    return Response(args)


def jsonify(*args: Any, **kwargs: Any) -> Response:
    if args and kwargs:
        raise TypeError("jsonify() behavior undefined when passed both args and kwargs")
    elif len(args) == 1:
        data = args[0]
    else:
        data = args or kwargs

    return Response(data, content_type="application/json")
