"""
BustAPI Application class - Flask-compatible web framework
"""

import inspect
import os
from typing import Any, Callable, Dict, List, Optional, Type, Union

from .context import ContextManagement, _AppContext, _RequestContext
from .core.helpers import get_root_path
from .core.logging import get_logger
from .dispatch import create_async_wrapper, create_sync_wrapper
from .extraction import ParameterExtraction
from .hooks import RequestLifecycle
from .http.request import Request, _request_ctx
from .http.response import Response, make_response
from .middleware import MiddlewareManager
from .routing.blueprints import Blueprint
from .routing.decorators import RouteRegistration
from .server.wsgi import WSGIAdapter
from .sessions import SecureCookieSessionInterface
from .templating.mixin import TemplateRendering


class BustAPI(
    RouteRegistration,
    ParameterExtraction,
    RequestLifecycle,
    ContextManagement,
    TemplateRendering,
    WSGIAdapter,
):
    """
    Flask-compatible application class built on Rust backend.
    """

    def __init__(
        self,
        import_name: str = None,
        static_url_path: Optional[str] = None,
        static_folder: Optional[str] = None,
        template_folder: Optional[str] = None,
        instance_relative_config: bool = False,
        root_path: Optional[str] = None,
        redirect_slashes: bool = True,
    ):
        if import_name is None:
            import inspect

            frame = inspect.stack()[1]
            module = inspect.getmodule(frame[0])
            import_name = module.__name__ if module else self.__class__.__module__

        self.import_name = import_name

        if root_path is None:
            root_path = get_root_path(self.import_name)
        self.root_path = root_path

        self.static_url_path = static_url_path

        if static_folder is None:
            static_folder = "static"
        if not os.path.isabs(static_folder):
            static_folder = os.path.join(root_path, static_folder)
        self.static_folder = static_folder

        if template_folder is None:
            template_folder = "templates"
        if not os.path.isabs(template_folder):
            template_folder = os.path.join(root_path, template_folder)
        self.template_folder = template_folder

        self.instance_relative_config = instance_relative_config
        self.redirect_slashes = redirect_slashes
        self.config: Dict[str, Any] = {}
        self.extensions: Dict[str, Any] = {}
        self.view_functions: Dict[str, Callable] = {}
        self.error_handler_spec: Dict[Union[int, Type[Exception]], Callable] = {}
        self.before_request_funcs: List[Callable] = []
        self.after_request_funcs: List[Callable] = []
        self.teardown_request_funcs: List[Callable] = []
        self.teardown_appcontext_funcs: List[Callable] = []
        self.blueprints: Dict[str, Blueprint] = {}
        self.url_map: Dict[str, Dict] = {}
        self._url_rules: List[Dict[str, Any]] = []
        self.path_validators: Dict[tuple, Dict[str, Any]] = {}
        self.query_validators: Dict[tuple, Dict[str, tuple]] = {}
        self.body_validators: Dict[tuple, Dict[str, tuple]] = {}
        self.dependencies: Dict[tuple, Dict[str, Any]] = {}
        self.jinja_env = None

        try:
            self.logger = get_logger("bustapi.app")
        except Exception:
            self.logger = None

        self.debug = False
        self.testing = False
        self.secret_key = None
        self.permanent_session_lifetime = None
        self.use_x_sendfile = False
        self.json_encoder = None
        self.json_decoder = None
        self.jinja_options = {}
        self.got_first_request = False
        self.shell_context_processors = []
        self.cli = None
        self.instance_path = None
        self.open_session = None
        self.save_session = None
        self.response_class = None
        self.request_class = None
        self.test_client_class = None
        self.test_cli_runner_class = None
        self.url_rule_class = None
        self.url_map_class = None
        self.subdomain_matching = False
        self.url_defaults = None
        self.template_context_processors = {}
        self._template_fragment_cache = None

        self.middleware_manager = MiddlewareManager()
        self.session_interface = SecureCookieSessionInterface()
        self._rust_app = None
        self._init_rust_backend()
        self._rust_app.set_not_found_handler(self._dispatch_not_found)

    def _init_rust_backend(self):
        try:
            from . import bustapi_core

            self._rust_app = bustapi_core.create_app()
            if self.static_folder and os.path.isdir(self.static_folder):
                static_url = self.static_url_path or "/static"
                self._rust_app.add_static_route(static_url, self.static_folder)
            if self.template_folder and os.path.isdir(self.template_folder):
                self._rust_app.set_template_folder(self.template_folder)
        except ImportError as e:
            raise RuntimeError(
                f"BustAPI requires the Rust backend. Build with: maturin develop\n{e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Rust backend: {e}") from e

    def register_blueprint(self, blueprint: Blueprint, **options) -> None:
        url_prefix = options.get("url_prefix", blueprint.url_prefix)
        self.blueprints[blueprint.name] = blueprint
        for rule, endpoint, view_func, methods in blueprint.deferred_functions:
            if url_prefix:
                rule = url_prefix.rstrip("/") + "/" + rule.lstrip("/")
            full_endpoint = f"{blueprint.name}.{endpoint}"
            self.view_functions[full_endpoint] = view_func
            for method in methods:
                if inspect.iscoroutinefunction(view_func):
                    self._rust_app.add_async_route(
                        method, rule, create_async_wrapper(self, view_func, rule)
                    )
                else:
                    self._rust_app.add_route(
                        method, rule, create_sync_wrapper(self, view_func, rule)
                    )

    def add_websocket_route(
        self, path: str, handler: Any, config: Optional[Any] = None
    ) -> None:
        self._rust_app.add_websocket_route(path, handler, config)

    def add_turbo_websocket_route(
        self, path: str, response_prefix: str, config: Optional[Any] = None
    ) -> None:
        self._rust_app.add_turbo_websocket_route(path, response_prefix, config)

    def _make_response(self, *args) -> Response:
        return make_response(*args)

    def _handle_exception(self, exception: Exception) -> Response:
        for exc_class_or_code, handler in self.error_handler_spec.items():
            if isinstance(exc_class_or_code, type) and isinstance(
                exception, exc_class_or_code
            ):
                rv = handler(exception)
                return (
                    self._make_response(*rv)
                    if isinstance(rv, tuple)
                    else self._make_response(rv)
                )
            elif isinstance(exc_class_or_code, int):
                if hasattr(exception, "code") and exception.code == exc_class_or_code:
                    rv = handler(exception)
                    return (
                        self._make_response(*rv)
                        if isinstance(rv, tuple)
                        else self._make_response(rv)
                    )
        status = getattr(exception, "code", 500) if hasattr(exception, "code") else 500
        try:
            return Response(f"Internal Server Error: {str(exception)}", status=status)
        except Exception:
            return make_response("Internal Server Error", 500)

    def _dispatch_not_found(self, rust_request, params=None):
        from .core.exceptions import NotFound

        try:
            request = Request._from_rust_request(rust_request)
            request.app = self
            token = _request_ctx.set(request)
            try:
                response = self._handle_exception(NotFound())
                return self._response_to_rust_format(response)
            finally:
                _request_ctx.reset(token)
        except Exception as e:
            self.logger.error(f"Error in 404 fallback: {e}")
            return ("Not Found", 404, {"Content-Type": "text/plain"})

    def _response_to_rust_format(self, response: Response) -> tuple:
        """
        Convert Python Response object to format expected by Rust (body, status, headers).
        """
        if hasattr(response, "get_data"):
            body = response.get_data()
        else:
            body = str(response).encode("utf-8")

        status = getattr(response, "status_code", 200)

        # Extract headers as a list of tuples to preserve multi-value headers
        if hasattr(response.headers, "items"):
            headers = response.headers.items()
            if not isinstance(headers, list):
                headers = list(headers)
        else:
            headers = []

        return (body, status, headers)

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        debug: bool = False,
        verbose: bool = False,
        load_dotenv: bool = True,
        workers: Optional[int] = None,
        reload: bool = False,
        server: str = "rust",
        **options,
    ) -> None:
        if debug:
            self.config["DEBUG"] = True
        from .server import runner

        if reload or debug:
            runner.enable_hot_reload()
        if workers is None:
            import multiprocessing

            workers = 1 if debug else multiprocessing.cpu_count()
        if server == "rust":
            runner.run_server_rust(self, host, port, workers, debug, verbose)
        else:
            getattr(runner, f"run_server_{server}")(
                self, host, port, workers, debug, **options
            )

    async def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        debug: bool = False,
        verbose: bool = False,
        **options,
    ) -> None:
        if debug:
            self.config["DEBUG"] = True
            from .server import runner

            runner.setup_debug_logging(self)
        try:
            await self._rust_app.run_async(host, port, debug, verbose, 1)
        except Exception as e:
            print(f"❌ Async server error: {e}")

    def test_client(self, use_cookies: bool = True, **kwargs):
        from .testing import BustTestClient

        return BustTestClient(self, use_cookies=use_cookies, **kwargs)
