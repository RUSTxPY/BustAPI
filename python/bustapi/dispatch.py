"""
Request dispatch and wrapping logic for BustAPI.
Includes fast-path optimizations for request processing.

TurboMax: Every check that can be pre-computed at registration time IS pre-computed.
"""

import inspect
from functools import wraps
from typing import TYPE_CHECKING, Callable

from .http.request import Request, _request_ctx
from .utils import async_to_sync

if TYPE_CHECKING:
    from .app import BustAPI

# Pre-compute the set of fast-returnable types (module-level constant)
_FAST_TYPES = (dict, list, str, bytes)
_JSON_TYPES = (dict, list)


def create_turbo_wrapper(handler: Callable) -> Callable:
    """
    Zero-overhead wrapper for simple handlers.

    Skips: Request creation, context, sessions, middleware, parameter extraction.
    Use for handlers that take no arguments and return dict/list/str/bytes.
    """

    @wraps(handler)
    def wrapper(rust_request, path_params=None):
        result = handler()
        # Fast path: bytes returned directly — Rust handles as raw body with JSON content-type
        # This avoids creating a tuple object and saves ~5 Python object allocations
        if isinstance(result, bytes):
            return result
        if isinstance(result, dict):
            return (result, 200, {"Content-Type": "application/json"})
        elif isinstance(result, list):
            return (result, 200, {"Content-Type": "application/json"})
        elif isinstance(result, str):
            return (result, 200, {"Content-Type": "text/html; charset=utf-8"})
        elif isinstance(result, tuple):
            return result
        else:
            return (str(result), 200, {})

    return wrapper


def create_typed_turbo_wrapper(handler: Callable, param_names: list) -> Callable:
    """
    Turbo wrapper for handlers with typed path parameters.

    Path parameters are extracted and converted in Rust for maximum performance.
    The handler receives params as keyword arguments.

    Args:
        handler: The user's handler function
        param_names: List of parameter names in order (e.g., ["id", "name"])

    Note:
        - No request object available (use regular @app.route for that)
        - No middleware, sessions, or auth support
        - Only path params, no query params yet
    """

    @wraps(handler)
    def wrapper(rust_request, path_params: dict):
        # path_params already parsed and typed by Rust (e.g., {"id": 123})
        try:
            result = handler(**path_params)
        except TypeError as e:
            # Handler signature mismatch
            return (
                {"error": f"Handler parameter mismatch: {e}"},
                500,
                {"Content-Type": "application/json"},
            )

        if isinstance(result, dict):
            return (result, 200, {"Content-Type": "application/json"})
        elif isinstance(result, list):
            return (result, 200, {"Content-Type": "application/json"})
        elif isinstance(result, str):
            return (result, 200, {"Content-Type": "text/html; charset=utf-8"})
        elif isinstance(result, tuple):
            return result
        else:
            return (str(result), 200, {})

    return wrapper


def create_sync_wrapper(app: "BustAPI", handler: Callable, rule: str) -> Callable:
    """Wrap handler with request context, middleware, and path param support.

    TurboMax: All checks are pre-computed at registration time.
    """

    # ========== PRE-COMPUTE EVERYTHING AT REGISTRATION TIME ==========

    # Handler signature analysis (once, not per request)
    try:
        sig = inspect.signature(handler)
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        expected_args = set(sig.parameters.keys())
    except (ValueError, TypeError):
        has_kwargs = True
        expected_args = set()

    # Pre-compute boolean flags (these NEVER change after registration)
    _has_secret_key = bool(app.secret_key)
    _has_before_hooks = bool(app.before_request_funcs)
    _has_after_hooks = bool(app.after_request_funcs)
    _has_middleware = bool(app.middleware_manager.middlewares)
    _has_teardown = bool(app.teardown_request_funcs)
    _has_path_params = "<" in rule
    _needs_request_inject = "request" in expected_args
    _is_no_arg_handler = not expected_args and not _has_path_params

    # Pre-compute which extraction steps are needed
    _rule_method_key = (rule,)  # key for validator lookups
    _has_query_validators = bool(app.query_validators.get(_rule_method_key))
    _has_body_validators = bool(app.body_validators.get(_rule_method_key))
    _has_deps = bool(app.dependencies.get(_rule_method_key))

    # Cache method references (avoid attribute lookups per request)
    _session_open = app.session_interface.open_session
    _session_cookie = app.session_interface.get_cookie_header_value
    _ctx_set = _request_ctx.set
    _ctx_reset = _request_ctx.reset
    _from_rust = Request._from_rust_request
    _make_response = app._make_response
    _to_rust = app._response_to_rust_format
    _handle_exc = app._handle_exception
    _extract_query = app._extract_query_params
    _extract_body = app._extract_body_params
    _extract_path = app._extract_path_params
    _validate_path = app._validate_path_params
    _resolve_deps = app._resolve_dependencies

    # For the ultra-fast no-middleware path: can we skip Response objects entirely?
    _can_fast_return = not _has_middleware and not _has_after_hooks

    @wraps(handler)
    def wrapper(rust_request, path_params=None):
        try:
            # 1. Request + Context (unavoidable — Python needs the request object)
            request = _from_rust(rust_request)
            request.app = app
            token = _ctx_set(request)

            # 2. Session (skip entirely if no secret_key)
            session = None
            if _has_secret_key:
                session = _session_open(app, request)
                request.session = session

            # 3. Before-request hooks (skip check if empty at registration time)
            if _has_before_hooks:
                for before_func in app.before_request_funcs:
                    res = before_func()
                    if inspect.isawaitable(res):
                        res = async_to_sync(res)
                    if res is not None:
                        response = _make_response(res)
                        if session:
                            app.session_interface.save_session(app, session, response)
                        return _to_rust(response)

            # 4. Main request processing
            if _has_middleware:
                # ---- PATH WITH MIDDLEWARE ----
                mw_response = app.middleware_manager.process_request(request)
                if mw_response:
                    response = mw_response
                else:
                    # Build kwargs
                    if path_params is not None:
                        kwargs = dict(path_params)
                        if app.path_validators:
                            kwargs = _validate_path(rule, request.method, kwargs)
                    elif not _has_path_params:
                        kwargs = {}
                    else:
                        _, kwargs = _extract_path(rule, request.method, request.path)

                    kwargs.update(_extract_query(rule, request))
                    if request.method in ("POST", "PUT", "PATCH"):
                        kwargs.update(_extract_body(rule, request))

                    dep_kwargs, dep_cache = _resolve_deps(rule, request.method, kwargs)
                    kwargs.update(dep_kwargs)

                    for name in expected_args:
                        if name not in kwargs and name in request.args:
                            kwargs[name] = request.args.get(name)

                    if _needs_request_inject:
                        kwargs["request"] = request

                    call_kwargs = (
                        kwargs
                        if has_kwargs
                        else {k: v for k, v in kwargs.items() if k in expected_args}
                    )

                    try:
                        result = handler(**call_kwargs)
                    finally:
                        if dep_cache:
                            dep_cache.cleanup_sync()

                    response = (
                        _make_response(result)
                        if not isinstance(result, tuple)
                        else _make_response(*result)
                    )
            else:
                # ---- ULTRA-FAST PATH (no middleware) ----
                if _is_no_arg_handler and path_params is None:
                    # Zero-arg handler: just call it
                    result = handler()
                else:
                    # Build kwargs
                    if path_params is not None:
                        kwargs = dict(path_params)
                        if app.path_validators:
                            kwargs = _validate_path(rule, request.method, kwargs)
                    elif not _has_path_params:
                        kwargs = {}
                    else:
                        _, kwargs = _extract_path(rule, request.method, request.path)

                    # Query params — only if validators exist or handler expects args
                    if _has_query_validators or expected_args:
                        kwargs.update(_extract_query(rule, request))
                    if request.method in ("POST", "PUT", "PATCH") and _has_body_validators:
                        kwargs.update(_extract_body(rule, request))

                    if _has_deps:
                        dep_kwargs, dep_cache = _resolve_deps(
                            rule, request.method, kwargs
                        )
                        kwargs.update(dep_kwargs)
                    else:
                        dep_cache = None

                    # Auto-inject query params for handler args not yet in kwargs
                    if expected_args:
                        for name in expected_args:
                            if name not in kwargs and name in request.args:
                                kwargs[name] = request.args.get(name)

                    if _needs_request_inject:
                        kwargs["request"] = request

                    call_kwargs = (
                        kwargs
                        if has_kwargs
                        else {k: v for k, v in kwargs.items() if k in expected_args}
                    )

                    try:
                        result = handler(**call_kwargs)
                    finally:
                        if dep_cache:
                            dep_cache.cleanup_sync()

                # FAST RETURN: skip Response object creation entirely
                if _can_fast_return:
                    result_type = type(result)
                    is_modified = session is not None and getattr(session, 'modified', False)

                    if result_type in _FAST_TYPES:
                        if not is_modified:
                            # Fastest possible: return raw Python object to Rust
                            return result
                        else:
                            # Session modified: need to inject Set-Cookie header
                            cookie_val = _session_cookie(app, session)
                            if result_type in _JSON_TYPES:
                                ct = "application/json"
                            elif result_type is str:
                                ct = "text/html; charset=utf-8"
                            else:
                                ct = "application/octet-stream"
                            headers_list = [("Content-Type", ct)]
                            if cookie_val:
                                headers_list.append(("Set-Cookie", cookie_val))
                            return (result, 200, headers_list)

                    # Response object fast path (e.g., from jsonify())
                    elif hasattr(result, 'status_code') and hasattr(result, 'get_data'):
                        if is_modified:
                            cookie_val = _session_cookie(app, session)
                            if cookie_val:
                                result.headers.add("Set-Cookie", cookie_val)
                        return _to_rust(result)

                response = (
                    _make_response(result)
                    if not isinstance(result, tuple)
                    else _make_response(*result)
                )

            # 5. Pipeline cleanup
            if _has_middleware:
                response = app.middleware_manager.process_response(request, response)
            if _has_after_hooks:
                for after_func in app.after_request_funcs:
                    res = after_func(response)
                    if inspect.isawaitable(res):
                        res = async_to_sync(res)
                    response = res or response
            if session is not None:
                app.session_interface.save_session(app, session, response)

            return _to_rust(response)

        except Exception as e:
            return _to_rust(_handle_exc(e))
        finally:
            if _has_teardown:
                for f in app.teardown_request_funcs:
                    try:
                        res = f(None)
                        if inspect.isawaitable(res):
                            async_to_sync(res)
                    except:
                        pass
            _ctx_reset(token)

    return wrapper


def create_async_wrapper(app: "BustAPI", handler: Callable, rule: str) -> Callable:
    """Wrap asynchronous handler; returns a sync wrapper that uses async_to_sync."""

    # Inspect handler signature to filter kwargs later
    try:
        sig = inspect.signature(handler)
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        expected_args = set(sig.parameters.keys())
    except (ValueError, TypeError):
        has_kwargs = True
        expected_args = set()

    @wraps(handler)
    def wrapper(rust_request):
        async def run_logic():
            request = Request._from_rust_request(rust_request)
            request.app = app
            token = _request_ctx.set(request)

            try:
                session = None
                if app.secret_key:
                    session = app.session_interface.open_session(app, request)
                    request.session = session

                if app.before_request_funcs:
                    for before_func in app.before_request_funcs:
                        res = before_func()
                        if inspect.isawaitable(res):
                            res = await res
                        if res is not None:
                            response = app._make_response(res)
                            if session:
                                app.session_interface.save_session(
                                    app, session, response
                                )
                            return response

                if app.middleware_manager.middlewares:
                    mw_response = app.middleware_manager.process_request(request)
                    if mw_response:
                        response = mw_response
                    else:
                        args, kwargs = app._extract_path_params(
                            rule, request.method, request.path
                        )
                        kwargs.update(app._extract_query_params(rule, request))
                        if request.method in ("POST", "PUT", "PATCH"):
                            kwargs.update(app._extract_body_params(rule, request))

                        dep_kwargs, dep_cache = await app._resolve_dependencies_async(
                            rule, request.method, kwargs
                        )
                        kwargs.update(dep_kwargs)

                        for name in expected_args:
                            if name not in kwargs and name in request.args:
                                kwargs[name] = request.args.get(name)

                        if "request" in expected_args:
                            kwargs["request"] = request

                        call_kwargs = (
                            kwargs
                            if has_kwargs
                            else {
                                k: v for k, v in kwargs.items() if k in expected_args
                            }
                        )

                        try:
                            result = await handler(**call_kwargs)
                        finally:
                            if dep_cache:
                                await dep_cache.cleanup()

                        response = (
                            app._make_response(result)
                            if not isinstance(result, tuple)
                            else app._make_response(*result)
                        )
                else:
                    if "<" not in rule and not expected_args:
                        result = await handler()
                    else:
                        if "<" not in rule:
                            kwargs = {}
                        else:
                            args, kwargs = app._extract_path_params(
                                rule, request.method, request.path
                            )

                        kwargs.update(app._extract_query_params(rule, request))
                        if request.method in ("POST", "PUT", "PATCH"):
                            kwargs.update(app._extract_body_params(rule, request))
                        dep_kwargs, dep_cache = await app._resolve_dependencies_async(
                            rule, request.method, kwargs
                        )
                        kwargs.update(dep_kwargs)

                        for name in expected_args:
                            if name not in kwargs and name in request.args:
                                kwargs[name] = request.args.get(name)

                        if "request" in expected_args:
                            kwargs["request"] = request

                        call_kwargs = (
                            kwargs
                            if has_kwargs
                            else {
                                k: v for k, v in kwargs.items() if k in expected_args
                            }
                        )

                        try:
                            result = await handler(**call_kwargs)
                        finally:
                            if dep_cache:
                                await dep_cache.cleanup()

                    response = (
                        app._make_response(result)
                        if not isinstance(result, tuple)
                        else app._make_response(*result)
                    )

                if app.middleware_manager.middlewares:
                    response = app.middleware_manager.process_response(
                        request, response
                    )
                if app.after_request_funcs:
                    for after_func in app.after_request_funcs:
                        res = after_func(response)
                        if inspect.isawaitable(res):
                            res = await res
                        response = res or response
                if session is not None:
                    app.session_interface.save_session(app, session, response)

                return app._response_to_rust_format(response)
            except Exception as e:
                return app._response_to_rust_format(app._handle_exception(e))
            finally:
                if app.teardown_request_funcs:
                    for f in app.teardown_request_funcs:
                        try:
                            res = f(None)
                            if inspect.isawaitable(res):
                                await res
                        except Exception:
                            pass
                _request_ctx.reset(token)

        return async_to_sync(run_logic())

    return wrapper
