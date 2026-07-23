//! Python route handlers

use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::OnceLock;

use crate::bindings::converters::*;
use crate::bindings::request::create_py_request;
use crate::bindings::typed_turbo::params_to_py_dict;
use crate::request::RequestData;
use crate::response::ResponseData;
use crate::router::RouteHandler;

// Reuse ParamType (and TypedValue for external consumers) from typed_turbo
pub use crate::bindings::typed_turbo::ParamType;
#[allow(unused_imports)]
pub use crate::bindings::typed_turbo::TypedValue;

/// Python route handler - calls Python function for each request
/// Path params arrive pre-extracted from the matchit radix tree.
pub struct PyRouteHandler {
    handler: Py<PyAny>,
    /// Pre-parsed param specs: (name, type) in order
    param_specs: Vec<(String, ParamType)>,
}

impl PyRouteHandler {
    /// Create handler with pattern for path param extraction
    pub fn with_pattern(
        handler: Py<PyAny>,
        pattern: String,
        param_types: HashMap<String, String>,
    ) -> Self {
        let param_specs = Self::parse_pattern(&pattern, &param_types);
        Self {
            handler,
            param_specs,
        }
    }

    /// Legacy constructor (no path params)
    pub fn new(handler: Py<PyAny>) -> Self {
        Self {
            handler,
            param_specs: Vec::new(),
        }
    }

    /// Parse route pattern to extract param specs
    fn parse_pattern(
        pattern: &str,
        param_types: &HashMap<String, String>,
    ) -> Vec<(String, ParamType)> {
        let mut specs = Vec::new();

        for part in pattern.split('/') {
            if part.starts_with('<') && part.ends_with('>') {
                let inner = &part[1..part.len() - 1];
                let (type_hint, name) = if let Some((t, n)) = inner.split_once(':') {
                    (t.trim(), n.trim())
                } else {
                    ("str", inner.trim())
                };

                // Use explicit type from registration, or infer from pattern
                let param_type = param_types
                    .get(name)
                    .map(|t| ParamType::from_str(t))
                    .unwrap_or_else(|| ParamType::from_str(type_hint));

                specs.push((name.to_string(), param_type));
            }
        }

        specs
    }
}

impl RouteHandler for PyRouteHandler {
    fn handle(&self, req: RequestData) -> ResponseData {
        Python::attach(|py| {
            // Convert router-extracted params (extracted ONCE by matchit)
            let py_params = if !self.param_specs.is_empty() && !req.path_params.is_empty() {
                params_to_py_dict(py, &req.path_params, &self.param_specs).ok()
            } else {
                None
            };

            // Create request object (moves req)
            let py_req = create_py_request(py, req);

            match py_req {
                Ok(py_req_obj) => {
                    // Call Python handler with (rust_request, path_params)
                    let call_result = match py_params {
                        Some(params) => self
                            .handler
                            .bind(py)
                            .call1((py_req_obj.clone_ref(py), params))
                            .map(|b| b.unbind()),
                        None => unsafe {
                            let res_ptr = pyo3::ffi::PyObject_CallFunctionObjArgs(
                                self.handler.as_ptr(),
                                py_req_obj.as_ptr(),
                                std::ptr::null_mut::<pyo3::ffi::PyObject>(),
                            );
                            if res_ptr.is_null() {
                                Err(PyErr::fetch(py))
                            } else {
                                Ok(pyo3::Bound::from_owned_ptr(py, res_ptr).unbind())
                            }
                        },
                    };

                    match call_result {
                        Ok(result) => {
                            let headers = &py_req_obj.borrow(py).inner.headers;
                            convert_py_result_to_response(py, result, headers)
                        }
                        Err(e) => {
                            tracing::error!("Python handler error: {:?}", e);
                            ResponseData::error(
                                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                                Some("Handler error"),
                            )
                        }
                    }
                }
                Err(e) => {
                    tracing::error!("Request creation error: {:?}", e);
                    ResponseData::error(
                        actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                        Some("Request error"),
                    )
                }
            }
        })
    }
}

/// Cached `asyncio` module handle — imported once, not per request.
static ASYNCIO_MODULE: OnceLock<Py<PyAny>> = OnceLock::new();

fn get_asyncio(py: Python<'_>) -> PyResult<&Py<PyAny>> {
    if let Some(m) = ASYNCIO_MODULE.get() {
        return Ok(m);
    }
    let module: Py<PyAny> = py.import("asyncio")?.into_any().unbind();
    Ok(ASYNCIO_MODULE.get_or_init(|| module))
}

/// Async Python route handler
pub struct PyAsyncRouteHandler {
    handler: Py<PyAny>,
}

impl PyAsyncRouteHandler {
    pub fn new(handler: Py<PyAny>) -> Self {
        Self { handler }
    }
}

impl RouteHandler for PyAsyncRouteHandler {
    fn handle(&self, req: RequestData) -> ResponseData {
        // For async handlers, call and check if coroutine
        Python::attach(|py| {
            // Create request object (moves req)
            let py_req = create_py_request(py, req);

            match py_req {
                Ok(py_req_obj) => {
                    match self.handler.call1(py, (py_req_obj.clone_ref(py),)) {
                        Ok(result) => {
                            // Check if coroutine (module handle cached in OnceLock)
                            let asyncio = get_asyncio(py);
                            if let Ok(asyncio) = asyncio {
                                match asyncio.call_method1(py, "iscoroutine", (&result,)) {
                                    Ok(is_coro) => {
                                        let is_coro_bool =
                                            is_coro.extract::<bool>(py).unwrap_or(false);

                                        if is_coro_bool {
                                            // Run coroutine
                                            if let Ok(loop_obj) =
                                                asyncio.call_method0(py, "get_event_loop")
                                            {
                                                if let Ok(awaited) = loop_obj
                                                    .call_method1(py, "run_until_complete", (&result,))
                                                {
                                                    let headers =
                                                        &py_req_obj.borrow(py).inner.headers;
                                                    return convert_py_result_to_response(
                                                        py, awaited, headers,
                                                    );
                                                } else {
                                                    tracing::error!("run_until_complete failed");
                                                }
                                            } else {
                                                // Try new loop if get_event_loop fails
                                                if let Ok(loop_obj) =
                                                    asyncio.call_method0(py, "new_event_loop")
                                                {
                                                    let _ = asyncio.call_method1(
                                                        py,
                                                        "set_event_loop",
                                                        (&loop_obj,),
                                                    );
                                                    if let Ok(awaited) = loop_obj.call_method1(
                                                        py,
                                                        "run_until_complete",
                                                        (&result,),
                                                    ) {
                                                        let headers =
                                                            &py_req_obj.borrow(py).inner.headers;
                                                        return convert_py_result_to_response(
                                                            py, awaited, headers,
                                                        );
                                                    }
                                                }
                                                tracing::error!("Failed to get/create event loop");
                                            }
                                        }
                                    }
                                    Err(e) => tracing::error!("iscoroutine check failed: {:?}", e),
                                }
                            }
                            let headers = &py_req_obj.borrow(py).inner.headers;
                            convert_py_result_to_response(py, result, headers)
                        }
                        Err(e) => {
                            tracing::error!("Async handler error: {:?}", e);
                            ResponseData::error(
                                actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                                Some("Async handler error"),
                            )
                        }
                    }
                }
                Err(e) => {
                    tracing::error!("Request creation error: {:?}", e);
                    ResponseData::error(
                        actix_web::http::StatusCode::INTERNAL_SERVER_ERROR,
                        Some("Request error"),
                    )
                }
            }
        })
    }
}
