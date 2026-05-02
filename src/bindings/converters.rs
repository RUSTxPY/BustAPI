//! Conversion utilities between Python and Rust types

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyString, PyTuple};
use std::collections::HashMap;

/// Convert Python result to ResponseData
pub fn convert_py_result_to_response(
    py: Python,
    result: Py<PyAny>,
    _req_headers: &HashMap<String, String>,
) -> crate::response::ResponseData {
    use crate::response::ResponseData;
    use http::StatusCode;
    use std::path::Path;

    // Convert result to Bound
    let result_bound = result.bind(py);

    // FIRST: Check for explicit path attribute (FileResponse optimization)
    if let Ok(path_obj) = result_bound.getattr("path") {
        if let Ok(path_str) = path_obj.extract::<String>() {
            let path = Path::new(&path_str);
            if path.exists() {
                let mut resp = ResponseData::new();
                resp.file_path = Some(path_str);

                if let Ok(status_code) = result_bound.getattr("status_code") {
                    if let Ok(status) = status_code.extract::<u16>() {
                        resp.set_status(StatusCode::from_u16(status).unwrap_or(StatusCode::OK));
                    }
                }

                if let Ok(headers) = result_bound.getattr("headers") {
                    if let Ok(items) = headers.call_method0("items") {
                        if let Ok(iter) = items.try_iter() {
                            for item in iter.flatten() {
                                if let Ok((k, v)) = item.extract::<(String, String)>() {
                                    if k.to_lowercase() != "content-length" {
                                        resp.add_header(&k, &v);
                                    }
                                }
                            }
                        }
                    }
                }
                return resp;
            }
        }
    }

    // STREAMING: Check for content attribute
    if let Ok(content_obj) = result_bound.getattr("content") {
        if !content_obj.is_none() {
            let mut resp = ResponseData::new();
            resp.stream_iterator = Some(content_obj.unbind());

            if let Ok(status_code) = result_bound.getattr("status_code") {
                if let Ok(status) = status_code.extract::<u16>() {
                    resp.set_status(StatusCode::from_u16(status).unwrap_or(StatusCode::OK));
                }
            }

            if let Ok(headers) = result_bound.getattr("headers") {
                if let Ok(items) = headers.call_method0("items") {
                    if let Ok(iter) = items.try_iter() {
                        for item in iter.flatten() {
                            if let Ok((k, v)) = item.extract::<(String, String)>() {
                                if k.to_lowercase() != "content-length" {
                                    resp.set_header(&k, &v);
                                }
                            }
                        }
                    }
                }
            }

            if let Ok(ct_prop) = result_bound.getattr("content_type") {
                if let Ok(ct) = ct_prop.extract::<String>() {
                    let has_ct = resp
                        .headers
                        .iter()
                        .any(|(k, _)| k.to_lowercase() == "content-type");
                    if !has_ct {
                        resp.set_header("Content-Type", &ct);
                    }
                }
            }

            return resp;
        }
    }

    // Check if tuple (body, status) or (body, status, headers)
    if let Ok(tuple) = result_bound.downcast::<PyTuple>() {
        match tuple.len() {
            2 => {
                if let (Ok(body), Ok(status)) = (
                    tuple.get_item(0),
                    tuple.get_item(1).and_then(|s| s.extract::<u16>()),
                ) {
                    let response_body = python_to_response_body(py, body.unbind());
                    let mut resp = ResponseData::with_body(response_body.into_bytes());
                    resp.set_status(StatusCode::from_u16(status).unwrap_or(StatusCode::OK));
                    resp.set_header("Content-Type", "application/json");
                    return resp;
                }
            }
            3 => {
                if let (Ok(body), Ok(status), Ok(hdrs)) = (
                    tuple.get_item(0),
                    tuple.get_item(1).and_then(|s| s.extract::<u16>()),
                    tuple.get_item(2),
                ) {
                    let response_body = python_to_response_body(py, body.unbind());
                    let status_code = StatusCode::from_u16(status).unwrap_or(StatusCode::OK);
                    let mut resp = ResponseData::with_status(status_code);
                    let mut has_ct = false;

                    // Support headers as dict or list of tuples
                    if let Ok(items) = hdrs.call_method0("items") {
                        if let Ok(iter) = items.try_iter() {
                            for item in iter.flatten() {
                                if let Ok((k, v)) = item.extract::<(String, String)>() {
                                    if k.to_lowercase() == "content-type" {
                                        has_ct = true;
                                    }
                                    resp.add_header(k, v);
                                }
                            }
                        }
                    } else if let Ok(iter) = hdrs.try_iter() {
                        for item in iter.flatten() {
                            if let Ok((k, v)) = item.extract::<(String, String)>() {
                                if k.to_lowercase() == "content-type" {
                                    has_ct = true;
                                }
                                resp.add_header(k, v);
                            }
                        }
                    }

                    if !has_ct {
                        resp.set_header("Content-Type", "application/json");
                    }
                    resp.set_body(response_body.into_bytes());
                    return resp;
                }
            }
            _ => {}
        }
    }

    // Check for Response object (duck typing)
    if let Ok(status_code) = result_bound.getattr("status_code") {
        if let Ok(headers) = result_bound.getattr("headers") {
            if let Ok(get_data) = result_bound.getattr("get_data") {
                let status = status_code.extract::<u16>().unwrap_or(200);
                let body_obj = get_data.call0().unwrap_or_else(|_| result_bound.clone());
                let body_bytes = if let Ok(bytes) = body_obj.extract::<Vec<u8>>() {
                    bytes
                } else if let Ok(s) = body_obj.extract::<String>() {
                    s.into_bytes()
                } else {
                    Vec::new()
                };

                let mut resp = ResponseData::with_body(body_bytes);
                resp.set_status(StatusCode::from_u16(status).unwrap_or(StatusCode::OK));

                if let Ok(items) = headers.call_method0("items") {
                    if let Ok(iter) = items.try_iter() {
                        for item in iter.flatten() {
                            if let Ok((k, v)) = item.extract::<(String, String)>() {
                                resp.add_header(&k, &v);
                            }
                        }
                    }
                }
                return resp;
            }
        }
    }

    // Default: treat as response body
    let body = python_to_response_body(py, result);
    let trimmed = body.trim();

    if trimmed.starts_with("<") {
        ResponseData::html(body)
    } else if trimmed.starts_with("{") || trimmed.starts_with("[") {
        let mut resp = ResponseData::with_body(body.into_bytes());
        resp.set_header("Content-Type", "application/json");
        resp
    } else {
        ResponseData::text(body)
    }
}

use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};

/// Convert Python object to response body bytes
pub fn python_to_response_body(py: Python, obj: Py<PyAny>) -> String {
    let obj_bound = obj.bind(py);
    if let Ok(bytes) = obj_bound.downcast::<PyBytes>() {
        return String::from_utf8_lossy(bytes.as_bytes()).to_string();
    }

    if let Ok(string) = obj_bound.downcast::<PyString>() {
        return string.to_string();
    }

    if obj_bound.is_instance_of::<PyDict>()
        || obj_bound.is_instance_of::<pyo3::types::PyList>()
        || obj_bound.is_instance_of::<pyo3::types::PyTuple>()
    {
        let serializer = PyJson(obj_bound);
        match serde_json::to_string(&serializer) {
            Ok(s) => return s,
            Err(e) => tracing::warn!("Native zero-copy serialization failed: {:?}", e),
        }
    }

    if let Ok(json_module) = py.import("json") {
        if let Ok(json_str) = json_module.call_method1("dumps", (obj_bound,)) {
            if let Ok(s) = json_str.extract::<String>() {
                return s;
            }
        }
    }

    "{}".to_string()
}

struct PyJson<'a>(&'a Bound<'a, PyAny>);

impl<'a> Serialize for PyJson<'a> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        use pyo3::types::*;
        let obj = self.0;

        if obj.is_none() {
            return serializer.serialize_none();
        }

        if let Ok(s) = obj.downcast::<PyString>() {
            return serializer.serialize_str(s.to_string_lossy().as_ref());
        }

        if let Ok(b) = obj.downcast::<PyBool>() {
            return serializer.serialize_bool(b.is_true());
        }

        if let Ok(i) = obj.downcast::<PyInt>() {
            if let Ok(val) = i.extract::<i64>() {
                return serializer.serialize_i64(val);
            }
            return serializer.serialize_str(&i.to_string());
        }

        if let Ok(f) = obj.downcast::<PyFloat>() {
            if let Ok(val) = f.extract::<f64>() {
                return serializer.serialize_f64(val);
            }
        }

        if let Ok(l) = obj.downcast::<PyList>() {
            let mut seq = serializer.serialize_seq(Some(l.len()))?;
            for item in l {
                seq.serialize_element(&PyJson(&item))?;
            }
            return seq.end();
        }

        if let Ok(t) = obj.downcast::<PyTuple>() {
            let mut seq = serializer.serialize_seq(Some(t.len()))?;
            for item in t {
                seq.serialize_element(&PyJson(&item))?;
            }
            return seq.end();
        }

        if let Ok(d) = obj.downcast::<PyDict>() {
            let mut map = serializer.serialize_map(Some(d.len()))?;
            for (k, v) in d {
                let key_str = k.extract::<String>().map_err(serde::ser::Error::custom)?;
                map.serialize_entry(&key_str, &PyJson(&v))?;
            }
            return map.end();
        }

        serializer.serialize_str(&obj.to_string())
    }
}

pub fn json_value_to_python(py: Python, value: &serde_json::Value) -> PyResult<Py<PyAny>> {
    use pyo3::types::PyBool;

    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => Ok(PyBool::new(py, *b).to_owned().into_any().unbind()),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(pyo3::types::PyInt::new(py, i).into_any().unbind())
            } else if let Some(f) = n.as_f64() {
                Ok(pyo3::types::PyFloat::new(py, f).into_any().unbind())
            } else {
                Ok(py.None())
            }
        }
        serde_json::Value::String(s) => Ok(PyString::new(py, s).into_any().unbind()),
        serde_json::Value::Array(arr) => {
            let py_list = pyo3::types::PyList::empty(py);
            for item in arr {
                py_list.append(json_value_to_python(py, item)?)?;
            }
            Ok(py_list.into_any().unbind())
        }
        serde_json::Value::Object(obj) => {
            let py_dict = PyDict::new(py);
            for (key, val) in obj {
                py_dict.set_item(key, json_value_to_python(py, val)?)?;
            }
            Ok(py_dict.into_any().unbind())
        }
    }
}
