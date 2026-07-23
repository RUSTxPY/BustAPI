//! Actix-web HTTP Server implementation for maximum performance

use actix_multipart::Multipart;
use actix_web::{web, HttpRequest, HttpResponse};
use arc_swap::ArcSwap;
use futures::{StreamExt, TryStreamExt};
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::request::RequestData;
use crate::response::ResponseData;
use crate::router::{RouteHandler, RouteMatch, Router};
use std::time::Instant;

/// Default maximum request body size: 16 MiB
pub const DEFAULT_MAX_BODY_SIZE: usize = 16 * 1024 * 1024;

/// Configuration for the BustAPI server
#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub host: String,
    pub port: u16,
    #[allow(dead_code)]
    pub debug: bool,
    pub workers: usize,
    pub show_banner: Option<usize>,
    pub ssl_cert: Option<String>,
    pub ssl_key: Option<String>,
    /// Maximum accepted request body size in bytes (DoS protection)
    pub max_body_size: usize,
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 5000,
            debug: false,
            workers: num_cpus::get(),
            show_banner: Some(num_cpus::get()),
            ssl_cert: None,
            ssl_key: None,
            max_body_size: DEFAULT_MAX_BODY_SIZE,
        }
    }
}

/// Fast route handler that returns static response (no Python needed)
pub struct FastRouteHandler {
    response_body: String,
    content_type: String,
}

impl FastRouteHandler {
    pub fn new(response_body: String) -> Self {
        Self {
            response_body,
            content_type: "application/json".to_string(),
        }
    }

    #[allow(dead_code)]
    pub fn with_content_type(mut self, content_type: &str) -> Self {
        self.content_type = content_type.to_string();
        self
    }
}

impl RouteHandler for FastRouteHandler {
    fn handle(&self, _req: RequestData) -> crate::response::ResponseData {
        let mut resp =
            crate::response::ResponseData::with_body(self.response_body.as_bytes().to_vec());
        resp.set_header("Content-Type", &self.content_type);
        resp
    }

    /// Static body — the request is never touched, skip building it fully.
    fn needs_full_request(&self) -> bool {
        false
    }

    /// Runs in nanoseconds; offloading to the blocking pool would cost
    /// more than the handler itself.
    fn should_offload(&self) -> bool {
        false
    }
}

use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use crate::websocket::{TurboWebSocketHandler, WebSocketConfig};

// Type aliases to avoid complexity warnings
type WsRoute = (Py<PyAny>, Option<WebSocketConfig>);
type TurboWsRoute = (Arc<TurboWebSocketHandler>, Option<WebSocketConfig>);

/// Shared application state
pub struct AppState {
    /// Copy-on-write router snapshot: lock-free reads on the request path
    pub routes: ArcSwap<Router>,
    pub debug: AtomicBool,
    pub websocket_handlers: RwLock<HashMap<String, WsRoute>>,
    pub turbo_websocket_handlers: RwLock<HashMap<String, TurboWsRoute>>,
    /// Maximum accepted request body size in bytes
    pub max_body_size: AtomicUsize,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            routes: ArcSwap::new(Arc::new(Router::new())),
            debug: AtomicBool::new(false),
            websocket_handlers: RwLock::new(HashMap::new()),
            turbo_websocket_handlers: RwLock::new(HashMap::new()),
            max_body_size: AtomicUsize::new(DEFAULT_MAX_BODY_SIZE),
        }
    }

    /// Copy-on-write router update. Registration is rare (startup) so the
    /// clone-and-swap cost is fine; request-path reads stay lock-free.
    pub fn update_router<F>(&self, f: F)
    where
        F: FnOnce(&mut Router),
    {
        let current = self.routes.load_full();
        let mut fresh = (*current).clone();
        f(&mut fresh);
        self.routes.store(Arc::new(fresh));
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new()
    }
}

/// Run a full router dispatch on the blocking pool so Python handler
/// execution never stalls the async reactor. Panics become 500s.
async fn offload_router(routes: Arc<Router>, req: RequestData) -> ResponseData {
    tokio::task::spawn_blocking(move || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| routes.process_request(req)))
            .unwrap_or_else(|_| {
                tracing::error!("Panic caught in request handler");
                ResponseData::error(
                    actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                    Some("Internal Server Error"),
                )
            })
    })
    .await
    .unwrap_or_else(|e| {
        tracing::error!("Blocking dispatch join error: {:?}", e);
        ResponseData::error(
            actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
            Some("Internal Server Error"),
        )
    })
}

/// Run a single handler on the blocking pool (see `offload_router`).
async fn offload_handler(handler: Arc<dyn RouteHandler>, req: RequestData) -> ResponseData {
    tokio::task::spawn_blocking(move || {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler.handle(req)))
            .unwrap_or_else(|_| {
                tracing::error!("Panic caught in route handler");
                ResponseData::error(
                    actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                    Some("Internal Server Error"),
                )
            })
    })
    .await
    .unwrap_or_else(|e| {
        tracing::error!("Blocking handler join error: {:?}", e);
        ResponseData::error(
            actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
            Some("Internal Server Error"),
        )
    })
}

/// Build the complete RequestData: header map, query params, body/multipart.
/// Returns Err(HttpResponse) for early rejects (413 Payload Too Large).
/// Takes `payload` by value so actix-multipart can own the stream.
async fn build_full_request_data(
    req: &HttpRequest,
    mut payload: web::Payload,
    method: http::Method,
    path: String,
    query_string: String,
    max_body_size: usize,
) -> Result<RequestData, HttpResponse> {
    let mut headers = std::collections::HashMap::new();
    for (key, value) in req.headers() {
        if let Ok(v) = value.to_str() {
            headers.insert(key.to_string(), v.to_string());
        }
    }

    // Cheap pre-check: reject oversized bodies via Content-Length
    // before reading a single byte.
    if let Some(len) = headers
        .get("content-length")
        .and_then(|v| v.parse::<usize>().ok())
    {
        if len > max_body_size {
            return Err(HttpResponse::PayloadTooLarge().body("Request body too large"));
        }
    }

    // Parse query params slightly redundantly but accurately
    let query_params = if !req.query_string().is_empty() {
        url::form_urlencoded::parse(req.query_string().as_bytes())
            .into_owned()
            .collect()
    } else {
        std::collections::HashMap::new()
    };

    let mut files = std::collections::HashMap::new();
    let mut multipart_form = std::collections::HashMap::new();
    let mut body_bytes = Vec::new();

    let content_type = headers
        .get("content-type")
        .map(|ct| ct.to_lowercase())
        .unwrap_or_default();

    if content_type.contains("multipart/form-data") {
        let mut total: usize = 0;
        let mut multipart = Multipart::new(req.headers(), payload);
        while let Ok(Some(mut field)) = multipart.try_next().await {
            // Note: In some versions content_disposition returns Option, compiler says it does.
            if let Some(content_disposition) = field.content_disposition() {
                let name = content_disposition.get_name().unwrap_or("").to_string();
                let filename = content_disposition.get_filename().map(|f| f.to_string());

                let mut field_bytes = Vec::new();
                while let Some(chunk) = field.next().await {
                    if let Ok(data) = chunk {
                        total += data.len();
                        if total > max_body_size {
                            return Err(
                                HttpResponse::PayloadTooLarge().body("Request body too large")
                            );
                        }
                        field_bytes.extend_from_slice(&data);
                    }
                }

                if let Some(fname) = filename {
                    files.insert(
                        name,
                        crate::request::UploadedFile {
                            filename: fname,
                            content_type: field
                                .content_type()
                                .map(|ct| ct.to_string())
                                .unwrap_or_default(),
                            content: field_bytes,
                        },
                    );
                } else if let Ok(s) = String::from_utf8(field_bytes) {
                    multipart_form.insert(name, s);
                }
            }
        }
    } else {
        // Regular body, with a hard size cap
        while let Some(chunk) = payload.next().await {
            if let Ok(data) = chunk {
                if body_bytes.len() + data.len() > max_body_size {
                    return Err(HttpResponse::PayloadTooLarge().body("Request body too large"));
                }
                body_bytes.extend_from_slice(&data);
            }
        }
    }

    Ok(RequestData {
        method,
        path,
        query_string,
        headers,
        body: bytes::Bytes::from(body_bytes), // single move, no double copy
        query_params,
        files,
        multipart_form,
        path_params: Vec::new(), // filled from the router match below
    })
}

/// Main request handler - dispatches to registered route handlers
pub async fn handle_request(
    req: HttpRequest,
    payload: web::Payload,
    state: web::Data<AppState>,
) -> HttpResponse {
    let start_time = Instant::now();
    tracing::debug!("handle_request path={} method={}", req.path(), req.method());
    for (k, v) in req.headers() {
        tracing::debug!("Header: {} = {:?}", k, v);
    }

    // Check for WebSocket upgrade request
    let is_websocket = req
        .headers()
        .get("upgrade")
        .and_then(|v| v.to_str().ok())
        .map(|v| v.to_lowercase() == "websocket")
        .unwrap_or(false);

    if is_websocket {
        let path = req.path().to_string();

        // Check for Turbo WebSocket handlers first (pure Rust, maximum performance)
        {
            let turbo_handlers = state.turbo_websocket_handlers.read().await;
            if let Some((handler, config)) = turbo_handlers.get(&path) {
                let handler_clone = handler.clone();
                let config_clone = config.clone();
                drop(turbo_handlers);

                match crate::websocket::handle_turbo_websocket(
                    req,
                    payload,
                    handler_clone,
                    config_clone,
                )
                .await
                {
                    Ok(response) => return response,
                    Err(e) => {
                        return HttpResponse::InternalServerError()
                            .body(format!("Turbo WebSocket error: {}", e));
                    }
                }
            }
        }

        // Fall back to Python WebSocket handlers
        let ws_handlers = state.websocket_handlers.read().await;

        if let Some((handler, config)) = ws_handlers.get(&path) {
            tracing::debug!("Found WebSocket handler for path: {}", path);
            let handler_clone = Python::attach(|py| handler.clone_ref(py));
            let config_clone = config.clone();
            drop(ws_handlers);

            // Extract Headers
            let mut headers = HashMap::new();
            for (key, value) in req.headers() {
                if let Ok(v) = value.to_str() {
                    headers.insert(key.to_string(), v.to_string());
                }
            }

            // Extract Cookies
            let mut cookies = HashMap::new();
            if let Ok(cookies_ref) = req.cookies() {
                for c in cookies_ref.iter() {
                    cookies.insert(c.name().to_string(), c.value().to_string());
                }
            }

            match crate::websocket::handle_websocket(
                req,
                payload,
                handler_clone,
                config_clone,
                headers,
                cookies,
            )
            .await
            {
                Ok(response) => return response,
                Err(e) => {
                    return HttpResponse::InternalServerError()
                        .body(format!("WebSocket error: {}", e));
                }
            }
        }
        // If no WS handler registered for this path, fall through to normal handling
        drop(ws_handlers);
    }

    let method = req.method().clone();
    let path = req.path().to_string();
    let query_string = req.query_string().to_string();

    // Lock-free snapshot of the router (no RwLock on the request path)
    let routes = state.routes.load_full();

    // Match BEFORE building RequestData: handlers that never touch
    // headers/body/query (turbo, static, fast) skip that work entirely.
    let route_match = routes.match_request(&method, &path, &query_string);
    let router_has_middleware = routes.has_middleware();

    let needs_full = router_has_middleware
        || match &route_match {
            RouteMatch::Handler(handler, _) => handler.needs_full_request(),
            RouteMatch::Redirect(_) => false,
            // The 404 fallback is a Python handler and needs the request
            RouteMatch::NotFound => true,
        };

    let mut request_data = if needs_full {
        let max_body = state.max_body_size.load(Ordering::Relaxed);
        match build_full_request_data(&req, payload, method, path, query_string, max_body).await {
            Ok(rd) => rd,
            Err(resp) => return resp,
        }
    } else {
        // Payload intentionally unused — actix drains leftover bytes on keep-alive
        drop(payload);
        RequestData::minimal(method, path, query_string)
    };

    // Dispatch. Python execution happens on the blocking pool so the
    // actix reactor threads are never stalled by the GIL or slow handlers.
    let response_data = if router_has_middleware {
        offload_router(routes, request_data).await
    } else {
        match route_match {
            RouteMatch::Handler(handler, params) => {
                request_data.path_params = params;
                if handler.should_offload() {
                    offload_handler(handler, request_data).await
                } else {
                    handler.handle(request_data)
                }
            }
            RouteMatch::Redirect(location) => Router::redirect_response(location),
            RouteMatch::NotFound => offload_router(routes, request_data).await,
        }
    };

    // Convert ResponseData to Actix Response

    // Check if it's a streaming response
    if let Some(iterator) = response_data.stream_iterator {
        let stream = crate::server::stream::PythonStream::new(iterator);
        let mut builder = HttpResponse::build(response_data.status);

        for (k, v) in response_data.headers {
            builder.append_header((k.as_str(), v.as_str()));
        }

        if state.debug.load(Ordering::Relaxed) {
            crate::logger::log_request_optimized(
                req.method().as_ref(),
                req.path(),
                response_data.status.as_u16(),
                start_time.elapsed().as_secs_f64(),
                true,
            );
        }
        return builder.streaming(stream);
    }

    // Check if it's a file response
    if let Some(path_str) = response_data.file_path {
        let path = std::path::Path::new(&path_str);
        if path.exists() {
            let named_file = actix_files::NamedFile::open(path);
            match named_file {
                Ok(nf) => {
                    // NamedFile handles Range requests automatically!
                    // We can still apply custom headers
                    let mut response = nf.into_response(&req);

                    // Apply custom headers from ResponseData
                    for (k, v) in response_data.headers {
                        response.headers_mut().append(
                            actix_web::http::header::HeaderName::from_bytes(k.as_bytes()).unwrap(),
                            actix_web::http::header::HeaderValue::from_str(&v).unwrap(),
                        );
                    }

                    if state.debug.load(Ordering::Relaxed) {
                        crate::logger::log_request_optimized(
                            req.method().as_ref(),
                            req.path(),
                            response.status().as_u16(),
                            start_time.elapsed().as_secs_f64(),
                            true,
                        );
                    }

                    return response;
                }
                Err(_) => {
                    if state.debug.load(Ordering::Relaxed) {
                        crate::logger::log_request_optimized(
                            req.method().as_ref(),
                            req.path(),
                            500,
                            start_time.elapsed().as_secs_f64(),
                            true,
                        );
                    }
                    return HttpResponse::InternalServerError().body("File Open Error");
                }
            }
        }
    }

    let mut builder = HttpResponse::build(response_data.status);

    for (k, v) in response_data.headers {
        builder.append_header((k.as_str(), v.as_str()));
    }

    if state.debug.load(Ordering::Relaxed) {
        crate::logger::log_request_optimized(
            req.method().as_ref(),
            req.path(),
            response_data.status.as_u16(),
            start_time.elapsed().as_secs_f64(),
            true,
        );
    }

    builder.body(response_data.body)
}
