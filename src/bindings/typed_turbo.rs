//! Typed Turbo Route Handler
//!
//! Ultra-fast handler for routes with typed path parameters.
//! Parameters are parsed and converted in Rust before calling Python.
//! Optional response caching for maximum performance.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyInt, PyString};
use std::collections::HashMap;
use std::sync::RwLock;
use std::time::{Duration, Instant};

use crate::bindings::converters::convert_py_result_to_response;
use crate::request::RequestData;
use crate::response::ResponseData;
use crate::router::RouteHandler;

/// Convert router-extracted path params to a Python dict, applying the
/// handler's pre-compiled type specs. The router already matched and
/// validated these values, so no re-parsing of the path happens here.
pub fn params_to_py_dict(
    py: Python,
    path_params: &[(String, String)],
    param_specs: &[(String, ParamType)],
) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);

    for (name, value) in path_params {
        // Look up the param's pre-compiled type by name (specs are few)
        let param_type = param_specs.iter().find(|(n, _)| n == name).map(|(_, t)| t);

        match param_type {
            Some(ParamType::Int) => match value.parse::<i64>() {
                Ok(n) => {
                    dict.set_item(name, PyInt::new(py, n))?;
                }
                Err(_) => {
                    // Router validated this, but stay graceful: hand big
                    // integers to Python's arbitrary-precision int.
                    let int_type = py.get_type::<PyInt>();
                    let py_int = int_type.call1((value,))?;
                    dict.set_item(name, py_int)?;
                }
            },
            Some(ParamType::Float) => {
                let n: f64 = value.parse().map_err(|_| {
                    pyo3::exceptions::PyValueError::new_err(format!(
                        "Parameter '{}': expected float, got '{}'",
                        name, value
                    ))
                })?;
                dict.set_item(name, PyFloat::new(py, n))?;
            }
            // Str / Path / unknown params pass through as strings
            _ => {
                dict.set_item(name, PyString::new(py, value))?;
            }
        }
    }

    Ok(dict.into())
}

/// Cached response with expiration time
#[derive(Clone)]
struct CachedResponse {
    response: ResponseData,
    expires_at: Instant,
}

impl CachedResponse {
    fn new(response: ResponseData, ttl_secs: u64) -> Self {
        Self {
            response,
            expires_at: Instant::now() + Duration::from_secs(ttl_secs),
        }
    }

    fn is_expired(&self) -> bool {
        Instant::now() > self.expires_at
    }
}

/// Parameter type specification
#[derive(Debug, Clone)]
pub enum ParamType {
    Int,
    Float,
    Str,
    Path, // Wildcard path segment
}

impl ParamType {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "int" => ParamType::Int,
            "float" => ParamType::Float,
            "path" => ParamType::Path,
            _ => ParamType::Str,
        }
    }
}

/// Parsed parameter value (kept for external consumers / future use)
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub enum TypedValue {
    Int(i64),
    BigInt(String), // For overflow, let Python handle
    Float(f64),
    Str(String),
}

/// Typed turbo route handler with optional caching
pub struct PyTypedTurboHandler {
    handler: Py<PyAny>,
    #[allow(dead_code)]
    pattern: String,
    /// (param_name, param_type) in order of appearance in route
    param_specs: Vec<(String, ParamType)>,
    /// Cache TTL in seconds (0 = no caching)
    cache_ttl: u64,
    /// Response cache: path -> cached response
    cache: RwLock<HashMap<String, CachedResponse>>,
}

impl PyTypedTurboHandler {
    #[allow(dead_code)]
    pub fn new(handler: Py<PyAny>, pattern: String, param_types: HashMap<String, String>) -> Self {
        Self::with_cache(handler, pattern, param_types, 0)
    }

    pub fn with_cache(
        handler: Py<PyAny>,
        pattern: String,
        param_types: HashMap<String, String>,
        cache_ttl: u64,
    ) -> Self {
        // Parse pattern to get param order
        let param_specs = Self::parse_pattern(&pattern, &param_types);

        Self {
            handler,
            pattern,
            param_specs,
            cache_ttl,
            cache: RwLock::new(HashMap::new()),
        }
    }

    /// Parse route pattern and build ordered param specs
    fn parse_pattern(
        pattern: &str,
        param_types: &HashMap<String, String>,
    ) -> Vec<(String, ParamType)> {
        let mut specs = Vec::new();

        for part in pattern.split('/') {
            if part.starts_with('<') && part.ends_with('>') {
                let inner = &part[1..part.len() - 1];
                let name = if let Some((_, n)) = inner.split_once(':') {
                    n.trim().to_string()
                } else {
                    inner.trim().to_string()
                };

                let param_type = param_types
                    .get(&name)
                    .map(|t| ParamType::from_str(t))
                    .unwrap_or(ParamType::Str);

                specs.push((name, param_type));
            }
        }

        specs
    }
}

impl RouteHandler for PyTypedTurboHandler {
    fn handle(&self, req: RequestData) -> ResponseData {
        // Check cache first (if caching is enabled)
        if self.cache_ttl > 0 {
            if let Ok(cache) = self.cache.read() {
                if let Some(cached) = cache.get(&req.path) {
                    if !cached.is_expired() {
                        return cached.response.clone();
                    }
                }
            }
        }

        let response = Python::attach(|py| {
            // Convert router-extracted params (matchit already parsed and
            // validated them — no second pass over the path here)
            let py_params = match params_to_py_dict(py, &req.path_params, &self.param_specs) {
                Ok(d) => d,
                Err(e) => {
                    tracing::error!("Failed to convert params to Python: {:?}", e);
                    return ResponseData::error(
                        actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                        Some("Parameter conversion error"),
                    );
                }
            };

            // Call Python handler with (rust_request=None, path_params=dict)
            // We pass None for rust_request since typed turbo doesn't use it
            match self.handler.call1(py, (py.None(), py_params)) {
                Ok(result) => convert_py_result_to_response(py, result, &req.headers),
                Err(e) => {
                    tracing::error!("Typed turbo handler error: {:?}", e);
                    ResponseData::error(
                        actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                        Some("Handler error"),
                    )
                }
            }
        });

        // Store in cache (if caching is enabled and response is successful)
        if self.cache_ttl > 0 && response.status.is_success() {
            if let Ok(mut cache) = self.cache.write() {
                cache.insert(
                    req.path.clone(),
                    CachedResponse::new(response.clone(), self.cache_ttl),
                );
            }
        }

        response
    }

    /// Typed turbo handlers only need method/path/path_params — the
    /// server skips header copies, body reads and query parsing for them.
    fn needs_full_request(&self) -> bool {
        false
    }
}
