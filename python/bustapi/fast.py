"""
BustAPI Fast Core - Next-Gen Ultra-High Performance Micro Framework Engine
Zero WSGI, zero Flask overhead, direct Rust C-API dispatch!
"""

from typing import Callable, List, Optional
from .bustapi_core import create_app

class FastBust:
    """
    Ultra-Fast Micro Engine for BustAPI.
    Designed for maximum RPS (100k+) without Flask/WSGI abstractions.
    """

    def __init__(self):
        self._app = create_app()

    def native_static(self, path: str, response_text: str, content_type: str = "text/plain; charset=utf-8"):
        """Register a Rust-native static response bypassing Python entirely for 200k-500k+ RPS!"""
        self._app.add_native_route("GET", path, response_text, 200, content_type)

    def get(self, path: str):
        """Register a GET route directly to Rust engine."""
        def decorator(fn: Callable):
            self._app.add_route("GET", path, fn)
            return fn
        return decorator

    def post(self, path: str):
        """Register a POST route directly to Rust engine."""
        def decorator(fn: Callable):
            self._app.add_route("POST", path, fn)
            return fn
        return decorator

    def put(self, path: str):
        """Register a PUT route directly to Rust engine."""
        def decorator(fn: Callable):
            self._app.add_route("PUT", path, fn)
            return fn
        return decorator

    def delete(self, path: str):
        """Register a DELETE route directly to Rust engine."""
        def decorator(fn: Callable):
            self._app.add_route("DELETE", path, fn)
            return fn
        return decorator

    def route(self, path: str, methods: Optional[List[str]] = None):
        """Register a route with custom methods directly to Rust engine."""
        if methods is None:
            methods = ["GET"]
        def decorator(fn: Callable):
            for method in methods:
                self._app.add_route(method.upper(), path, fn)
            return fn
        return decorator

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 8090,
        workers: int = 4,
        debug: bool = False,
    ):
        """Start high-performance Rust HTTP server."""
        self._app.run(host, port, workers, debug, False)
