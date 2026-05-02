"""
Testing utilities for BustAPI - Flask-compatible test client
"""

import json as json_module
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode

from ..http.response import Headers


class TestResponse:
    """
    Test response object for BustAPI test client.
    """

    def __init__(
        self,
        response_data: bytes,
        status_code: int,
        headers: Union[Dict, List, Headers],
    ):
        self.data = response_data
        self.status_code = status_code
        self.headers = Headers(headers)
        self._json_cache = None

    @property
    def status(self) -> str:
        return f"{self.status_code}"

    def get_data(self, as_text: bool = False) -> Union[bytes, str]:
        if as_text:
            return self.data.decode("utf-8", errors="replace")
        return self.data

    @property
    def text(self) -> str:
        return self.get_data(as_text=True)

    def get_json(self, force: bool = False, silent: bool = False) -> Optional[Any]:
        if self._json_cache is not None:
            return self._json_cache

        content_type = self.headers.get("Content-Type", "")
        if not force and "application/json" not in content_type.lower():
            return None

        try:
            self._json_cache = json_module.loads(self.get_data(as_text=True))
            return self._json_cache
        except (ValueError, TypeError):
            if not silent:
                raise
            return None

    @property
    def json(self) -> Optional[Any]:
        return self.get_json()

    @property
    def is_json(self) -> bool:
        content_type = self.headers.get("Content-Type", "")
        return "application/json" in content_type.lower()

    def __repr__(self) -> str:
        content_type = self.headers.get("Content-Type", "")
        return f"<TestResponse {self.status_code} [{content_type}]>"


class BustTestClient:
    """
    Test client for BustAPI applications (Flask-compatible).
    """

    def __init__(
        self,
        application,
        response_wrapper=None,
        use_cookies=True,
        allow_subdomain_redirects=False,
    ):
        self.application = application
        self.response_wrapper = response_wrapper or TestResponse
        self.use_cookies = use_cookies
        self.allow_subdomain_redirects = allow_subdomain_redirects

        # Cookie jar for session management
        self.cookie_jar: Dict[str, str] = {}

    def open(
        self,
        path: str,
        method: str = "GET",
        data: Optional[Union[str, bytes, dict]] = None,
        json: Optional[Any] = None,
        query_string: Optional[Union[str, dict]] = None,
        headers: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        **kwargs,
    ) -> TestResponse:
        headers = headers or {}

        if json is not None:
            headers["Content-Type"] = "application/json"
            data = json_module.dumps(json)

        if content_type:
            headers["Content-Type"] = content_type

        if query_string:
            if isinstance(query_string, dict):
                query_string = urlencode(query_string)
            if "?" in path:
                path += "&" + query_string
            else:
                path += "?" + query_string

        if data is not None:
            if isinstance(data, dict):
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    data = urlencode(data)
                elif headers.get("Content-Type") == "application/json":
                    data = json_module.dumps(data)

            if isinstance(data, str):
                data = data.encode("utf-8")

        if self.use_cookies and self.cookie_jar:
            cookie_header = "; ".join([f"{k}={v}" for k, v in self.cookie_jar.items()])
            headers["Cookie"] = cookie_header

        if isinstance(data, str):
            data_bytes = data.encode("utf-8")
        elif isinstance(data, dict):
            data_bytes = urlencode(data).encode("utf-8")
        elif data is None:
            data_bytes = b""
        else:
            data_bytes = data

        mock_request = MockRequest(method, path, headers, data_bytes)

        try:
            response_obj = self._call_application(mock_request)

            status_code = getattr(response_obj, "status_code", 200)
            response_headers = getattr(response_obj, "headers", {})
            body_data = getattr(response_obj, "data", b"")

            # Update cookies from response
            if self.use_cookies and "Set-Cookie" in response_headers:
                # Headers object can return a list for getlist
                cookie_headers = response_headers.getlist("Set-Cookie")
                for cookie_header in cookie_headers:
                    self._update_cookies(cookie_header)

            return self.response_wrapper(body_data, status_code, response_headers)

        except Exception as e:
            error_msg = f"Test client error: {str(e)}"
            return self.response_wrapper(error_msg.encode(), 500, {})

    def _call_application(self, request: "MockRequest") -> Any:
        from io import BytesIO

        environ = {
            "REQUEST_METHOD": request.method,
            "PATH_INFO": request.path,
            "QUERY_STRING": (
                urlencode(request.query_params) if request.query_params else ""
            ),
            "wsgi.input": BytesIO(request.body),
            "CONTENT_LENGTH": str(len(request.body)),
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "5000",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.errors": BytesIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
        }

        for key, value in request.headers.items():
            key = key.upper().replace("-", "_")
            if key == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = value
            elif key == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = value
            else:
                environ[f"HTTP_{key}"] = value

        response_data: Dict[str, Any] = {"status": None, "headers": []}

        def start_response(status, headers, exc_info=None):
            response_data["status"] = status
            response_data["headers"] = headers

        app_iter = self.application.wsgi_app(environ, start_response)
        body = b"".join(app_iter)

        from ..http.response import Response

        status_code = 200
        if response_data["status"]:
            try:
                status_code = int(response_data["status"].split(" ")[0])
            except (ValueError, IndexError):
                pass

        # Preserve ALL headers by passing the list of tuples directly to Response
        resp = Response(body, status=status_code, headers=response_data["headers"])
        return resp

    def _update_cookies(self, set_cookie_header: str) -> None:
        if "=" in set_cookie_header:
            cookie_parts = set_cookie_header.split(";")[0]
            if "=" in cookie_parts:
                name, value = cookie_parts.split("=", 1)
                self.cookie_jar[name.strip()] = value.strip()

    def get(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="GET", **kwargs)

    def post(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="POST", **kwargs)

    def put(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="PUT", **kwargs)

    def delete(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="DELETE", **kwargs)

    def patch(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="PATCH", **kwargs)

    def head(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="HEAD", **kwargs)

    def options(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="OPTIONS", **kwargs)

    def trace(self, path: str, **kwargs) -> TestResponse:
        return self.open(path, method="TRACE", **kwargs)

    def __enter__(self) -> "BustTestClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cookie_jar.clear()

    @contextmanager
    def session_transaction(self):
        app = self.application
        if not app.secret_key:
            raise RuntimeError("Sessions require a secret_key")

        headers = {}
        if self.use_cookies and self.cookie_jar:
            cookie_header = "; ".join([f"{k}={v}" for k, v in self.cookie_jar.items()])
            headers["Cookie"] = cookie_header

        from ..http.request import Request

        mock_req = Request._from_rust_request(MockRequest("GET", "/", headers, b""))
        mock_req.app = app

        session = app.session_interface.open_session(app, mock_req)
        yield session

        if session.modified:
            from ..http.response import Response

            resp = Response(b"")
            app.session_interface.save_session(app, session, resp)

            if "Set-Cookie" in resp.headers:
                cookie_headers = resp.headers.getlist("Set-Cookie")
                for cookie_header in cookie_headers:
                    self._update_cookies(cookie_header)


class MockRequest:
    def __init__(self, method: str, path: str, headers: Dict[str, str], body: bytes):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body

        if "?" in path:
            self.path, query_string = path.split("?", 1)
            self.query_params = dict(
                tuple(item.split("=", 1)) if "=" in item else (item, "")
                for item in query_string.split("&")
                if item
            )
        else:
            self.query_params = {}

    @property
    def cookies(self) -> Dict[str, str]:
        cookie_header = self.get_header("Cookie")
        if not cookie_header:
            return {}

        cookies = {}
        for part in cookie_header.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k] = v
        return cookies

    def get_header(self, name: str) -> Optional[str]:
        name_lower = name.lower()
        for key, value in self.headers.items():
            if key.lower() == name_lower:
                return value
        return None

    def is_json(self) -> bool:
        content_type = self.get_header("content-type") or ""
        return "application/json" in content_type.lower()

    def get_json(self) -> Optional[Any]:
        if not self.is_json():
            return None
        try:
            return json_module.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None


class FlaskClient(BustTestClient):
    pass


__all__ = [
    "BustTestClient",
    "TestResponse",
    "FlaskClient",
    "MockRequest",
]
