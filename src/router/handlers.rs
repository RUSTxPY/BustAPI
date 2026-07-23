//! Route registration and matching system
//!
//! Uses matchit radix tree for O(log n) route matching instead of O(n) linear iteration.
//! Route parameters are extracted exactly once during matching and handed to the
//! handler via `RequestData::path_params` — no double parsing.

use crate::request::RequestData;
use crate::response::ResponseData;
use http::Method;
use std::collections::HashMap;
use std::sync::Arc;

/// Trait for handling HTTP requests
pub trait RouteHandler: Send + Sync {
    fn handle(&self, req: RequestData) -> ResponseData;

    /// Whether this handler needs the fully-built request
    /// (headers copied, body read, query params parsed).
    ///
    /// Handlers that only use method/path/path_params (turbo, static file,
    /// fast routes) should return `false` so the server can skip building
    /// the expensive parts of `RequestData`.
    fn needs_full_request(&self) -> bool {
        true
    }

    /// Whether dispatch should be offloaded to the blocking thread pool.
    ///
    /// Python-bound handlers must offload so the async reactor is never
    /// stalled. Pure-Rust handlers that run in nanoseconds (e.g. static
    /// responses) can stay on the worker thread.
    fn should_offload(&self) -> bool {
        true
    }
}

/// Route information
#[allow(dead_code)]
pub struct Route {
    pub path: String,
    pub method: Method,
    pub handler: Arc<dyn RouteHandler>,
}

/// Handler wrapper that stores the handler and original path pattern
#[derive(Clone)]
struct HandlerEntry {
    handler: Arc<dyn RouteHandler>,
    method: Method,
    original_pattern: String,
    /// Pre-compiled parameter type constraints (name -> type)
    param_types: Vec<(String, ParamType)>,
}

/// Parameter type for validation (pre-compiled at registration time)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ParamType {
    /// String parameter (accepts any non-empty string)
    Str,
    /// Integer parameter (must parse as i64)
    Int,
    /// Float parameter (must parse as f64)
    Float,
    /// Path wildcard (captures everything remaining)
    Path,
}

/// Parse a BustAPI pattern and extract parameter types
/// Returns (matchit_pattern, param_types)
fn parse_pattern(pattern: &str) -> (String, Vec<(String, ParamType)>) {
    let mut result = String::with_capacity(pattern.len());
    let mut param_types = Vec::new();
    let mut chars = pattern.chars().peekable();

    while let Some(c) = chars.next() {
        if c == '<' {
            // Find the closing >
            let mut param = String::new();
            while let Some(&nc) = chars.peek() {
                if nc == '>' {
                    chars.next(); // consume '>'
                    break;
                }
                param.push(chars.next().unwrap());
            }

            // Parse the parameter: type:name or just name
            let (type_str, param_name) = if let Some((t, n)) = param.split_once(':') {
                (t.trim(), n.trim())
            } else {
                ("str", param.trim())
            };

            // Convert type string to ParamType
            let param_type = match type_str {
                "int" => ParamType::Int,
                "float" => ParamType::Float,
                "path" => ParamType::Path,
                _ => ParamType::Str,
            };

            // Store pre-compiled type info
            param_types.push((param_name.to_string(), param_type));

            // Convert to matchit syntax
            if param_type == ParamType::Path {
                // Wildcard/catch-all parameter
                result.push_str("{*");
                result.push_str(param_name);
                result.push('}');
            } else {
                // Regular parameter
                result.push('{');
                result.push_str(param_name);
                result.push('}');
            }
        } else {
            result.push(c);
        }
    }

    (result, param_types)
}

/// Validate a single extracted param value against its pre-compiled type
fn validate_param_value(value: &str, param_type: &ParamType) -> bool {
    match param_type {
        ParamType::Int => value.parse::<i64>().is_ok(),
        ParamType::Float => value.parse::<f64>().is_ok(),
        ParamType::Str => !value.is_empty(),
        ParamType::Path => true,
    }
}

/// Outcome of matching a request against the router
pub enum RouteMatch {
    /// Matched handler plus router-extracted path params (name, raw value)
    Handler(Arc<dyn RouteHandler>, Vec<(String, String)>),
    /// Trailing-slash redirect target (full Location, query string included)
    Redirect(String),
    /// No route matched
    NotFound,
}

/// Router for managing routes and dispatching requests
/// Uses matchit radix tree for O(log n) route matching
pub struct Router {
    /// Matchit routers per HTTP method for fast lookup
    method_routers: HashMap<Method, matchit::Router<usize>>,
    /// Handler storage indexed by ID
    handlers: Vec<HandlerEntry>,
    /// Legacy routes map for redirect slash checking (static routes only)
    pub(crate) routes: HashMap<(Method, String), Arc<dyn RouteHandler>>,
    pub(crate) middleware: Vec<Arc<dyn super::middleware::Middleware>>,
    pub(crate) redirect_slashes: bool,
    pub not_found_handler: Option<Arc<dyn RouteHandler>>,
}

/// Clone is used for copy-on-write snapshots (arc_swap) at registration
/// time. The radix trees are rebuilt from the handler entries; handler
/// `Arc`s are refcount-bumped, never deep-cloned.
impl Clone for Router {
    fn clone(&self) -> Self {
        let mut method_routers: HashMap<Method, matchit::Router<usize>> = HashMap::new();
        for (id, entry) in self.handlers.iter().enumerate() {
            let (matchit_pattern, _) = parse_pattern(&entry.original_pattern);
            let method_router = method_routers.entry(entry.method.clone()).or_default();
            // Same conflict policy as add_route: warn and keep the first
            if let Err(e) = method_router.insert(&matchit_pattern, id) {
                tracing::warn!(
                    "Route re-insertion warning for {}: {:?}",
                    matchit_pattern,
                    e
                );
            }
        }
        Self {
            method_routers,
            handlers: self.handlers.clone(),
            routes: self.routes.clone(),
            middleware: self.middleware.clone(),
            redirect_slashes: self.redirect_slashes,
            not_found_handler: self.not_found_handler.clone(),
        }
    }
}

impl Router {
    /// Create a new router
    pub fn new() -> Self {
        Self {
            method_routers: HashMap::new(),
            handlers: Vec::new(),
            routes: HashMap::new(),
            middleware: Vec::new(),
            redirect_slashes: true,
            not_found_handler: None,
        }
    }

    /// Add a route to the router
    pub fn add_route<H>(&mut self, method: Method, path: String, handler: H)
    where
        H: RouteHandler + 'static,
    {
        tracing::debug!("Adding route: {} {}", method, path);

        let handler_arc = Arc::new(handler);
        let handler_id = self.handlers.len();

        // Parse pattern and extract pre-compiled type information
        let (matchit_pattern, param_types) = parse_pattern(&path);

        // Store handler with pre-compiled param types
        self.handlers.push(HandlerEntry {
            handler: handler_arc.clone(),
            method: method.clone(),
            original_pattern: path.clone(),
            param_types,
        });

        // Also store in legacy routes map for compatibility
        self.routes
            .insert((method.clone(), path.clone()), handler_arc);

        // Get or create method router
        let method_router = self.method_routers.entry(method).or_default();

        // Insert route (ignore errors for duplicate routes)
        if let Err(e) = method_router.insert(&matchit_pattern, handler_id) {
            tracing::warn!("Route insertion warning for {}: {:?}", matchit_pattern, e);
        }
    }

    /// Add middleware to the router
    #[allow(dead_code)]
    pub fn add_middleware<M>(&mut self, middleware: M)
    where
        M: super::middleware::Middleware + 'static,
    {
        tracing::debug!("Adding middleware");
        self.middleware.push(Arc::new(middleware));
    }

    /// Whether any Rust-side middleware is registered
    pub fn has_middleware(&self) -> bool {
        !self.middleware.is_empty()
    }

    /// Get all registered routes (for debugging/inspection)
    #[allow(dead_code)]
    pub fn get_routes(&self) -> Vec<(Method, String, Arc<dyn RouteHandler>)> {
        self.routes
            .iter()
            .map(|((method, path), handler)| (method.clone(), path.clone(), handler.clone()))
            .collect()
    }

    /// Get number of registered routes
    #[allow(dead_code)]
    pub fn route_count(&self) -> usize {
        self.handlers.len()
    }

    /// Process incoming request through middleware and handlers
    pub fn process_request(&self, request_data: RequestData) -> ResponseData {
        // Process middleware (request phase)
        let mut req_data = request_data;
        for middleware in &self.middleware {
            if let Err(response) = middleware.process_request(&mut req_data) {
                return response;
            }
        }

        let matched = self.match_request(&req_data.method, &req_data.path, &req_data.query_string);

        if self.middleware.is_empty() {
            // FAST PATH: no middleware, move the request into the handler
            match matched {
                RouteMatch::Handler(handler, params) => {
                    req_data.path_params = params;
                    handler.handle(req_data)
                }
                RouteMatch::Redirect(location) => Self::redirect_response(location),
                RouteMatch::NotFound => match self.not_found_handler {
                    Some(ref handler) => handler.handle(req_data),
                    None => ResponseData::error(http::StatusCode::NOT_FOUND, Some("Not Found")),
                },
            }
        } else {
            // Middleware path: response phase needs &RequestData after the
            // handler runs, so one clone is unavoidable here — but it is
            // cheap now (body is `Bytes`, an O(1) refcount bump).
            let mut response_data = match matched {
                RouteMatch::Handler(handler, params) => {
                    req_data.path_params = params;
                    handler.handle(req_data.clone())
                }
                RouteMatch::Redirect(location) => Self::redirect_response(location),
                RouteMatch::NotFound => match self.not_found_handler {
                    Some(ref handler) => handler.handle(req_data.clone()),
                    None => ResponseData::error(http::StatusCode::NOT_FOUND, Some("Not Found")),
                },
            };

            for middleware in &self.middleware {
                middleware.process_response(&req_data, &mut response_data);
            }
            response_data
        }
    }

    /// Match a request: radix-tree lookup with HEAD->GET fallback, then
    /// trailing-slash redirect resolution. Does NOT clone the request.
    pub fn match_request(&self, method: &Method, path: &str, query_string: &str) -> RouteMatch {
        let handler_opt = self.match_route(method, path).or_else(|| {
            // HEAD -> GET fallback (match-only, no request clone needed)
            if *method == Method::HEAD {
                self.match_route(&Method::GET, path)
            } else {
                None
            }
        });

        if let Some((handler, params)) = handler_opt {
            return RouteMatch::Handler(handler, params);
        }

        if let Some(location) = self.try_redirect(method, path, query_string) {
            return RouteMatch::Redirect(location);
        }

        RouteMatch::NotFound
    }

    /// Match a route using matchit radix tree.
    /// Validates params against pre-compiled type constraints and returns
    /// the extracted params exactly once (single pass, no re-parsing later).
    fn match_route(
        &self,
        method: &Method,
        path: &str,
    ) -> Option<(Arc<dyn RouteHandler>, Vec<(String, String)>)> {
        let method_router = self.method_routers.get(method)?;
        let matched = method_router.at(path).ok()?;
        let entry = self.handlers.get(*matched.value)?;

        // Extract + validate in a single pass
        let mut params: Vec<(String, String)> = Vec::with_capacity(entry.param_types.len());
        for (name, value) in matched.params.iter() {
            params.push((name.to_string(), value.to_string()));
        }

        if !entry.param_types.is_empty() {
            for (name, param_type) in &entry.param_types {
                let value = params
                    .iter()
                    .find(|(n, _)| n == name)
                    .map(|(_, v)| v.as_str())
                    .unwrap_or("");
                if !validate_param_value(value, param_type) {
                    return None;
                }
            }
        }

        Some((entry.handler.clone(), params))
    }

    /// Try to redirect with/without trailing slash
    fn try_redirect(&self, method: &Method, path: &str, query_string: &str) -> Option<String> {
        if !self.redirect_slashes {
            return None;
        }

        // Check redirect for current method
        let redirect_path = if let Some(trimmed) = path.strip_suffix('/') {
            if self
                .routes
                .contains_key(&(method.clone(), trimmed.to_string()))
            {
                Some(trimmed.to_string())
            } else {
                None
            }
        } else {
            let slashed = format!("{}/", path);
            if self.routes.contains_key(&(method.clone(), slashed.clone())) {
                Some(slashed)
            } else {
                None
            }
        };

        // HEAD -> GET fallback for redirect
        let redirect_path = redirect_path.or_else(|| {
            if *method == Method::HEAD {
                let get_method = Method::GET;
                if let Some(trimmed) = path.strip_suffix('/') {
                    if self
                        .routes
                        .contains_key(&(get_method.clone(), trimmed.to_string()))
                    {
                        return Some(trimmed.to_string());
                    }
                } else {
                    let slashed = format!("{}/", path);
                    if self
                        .routes
                        .contains_key(&(get_method.clone(), slashed.clone()))
                    {
                        return Some(slashed);
                    }
                }
            }
            None
        });

        redirect_path.map(|new_path| {
            if !query_string.is_empty() {
                format!("{}?{}", new_path, query_string)
            } else {
                new_path
            }
        })
    }

    /// Build the 307 redirect response for a resolved Location
    pub fn redirect_response(location: String) -> ResponseData {
        let mut resp = ResponseData::new();
        resp.status = http::StatusCode::TEMPORARY_REDIRECT;
        resp.set_header("Location", location);
        resp
    }
}

impl Default for Router {
    fn default() -> Self {
        Self::new()
    }
}

/// Simple function-based route handler
#[allow(dead_code)]
pub struct FunctionHandler<F> {
    func: F,
}

impl<F> FunctionHandler<F> {
    #[allow(dead_code)]
    pub fn new(func: F) -> Self {
        Self { func }
    }
}

impl<F> RouteHandler for FunctionHandler<F>
where
    F: Fn(RequestData) -> ResponseData + Send + Sync,
{
    fn handle(&self, req: RequestData) -> ResponseData {
        (self.func)(req)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pattern_conversion() {
        assert_eq!(parse_pattern("/users/<id>").0, "/users/{id}");
        assert_eq!(parse_pattern("/users/<int:id>").0, "/users/{id}");
        assert_eq!(parse_pattern("/files/<path:rest>").0, "/files/{*rest}");
        assert_eq!(
            parse_pattern("/api/<version>/users/<int:id>").0,
            "/api/{version}/users/{id}"
        );
    }
}
