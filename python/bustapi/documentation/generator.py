"""
Optional documentation support for BustAPI.

This module provides the BustAPIDocs extension, which adds OpenAPI (Swagger)
and ReDoc documentation to a BustAPI application.
"""

import inspect
import json
from typing import Any, Dict, List, Optional

from ..app import BustAPI
from ..http.response import Response


class BustAPIDocs:
    """
    Extension for adding OpenAPI documentation to BustAPI.

    Usage:
        app = BustAPI()
        docs = BustAPIDocs(app, title="My API")
    """

    def __init__(
        self,
        app: Optional[BustAPI] = None,
        title: str = "BustAPI",
        version: str = "0.3.0",
        description: str = "",
        docs_url: Optional[str] = "/docs",
        redoc_url: Optional[str] = "/redoc",
        openapi_url: Optional[str] = "/openapi.json",
    ):
        self.title = title
        self.version = version
        self.description = description
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_url = openapi_url
        self._schema_cache: Optional[Dict[str, Any]] = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: BustAPI):
        """Initialize the extension with the application."""
        self.app = app

        if self.openapi_url:
            app.add_url_rule(
                self.openapi_url, "openapi_schema", self._openapi_route, methods=["GET"]
            )

        if self.docs_url and self.openapi_url:
            app.add_url_rule(
                self.docs_url, "swagger_ui", self._swagger_ui_route, methods=["GET"]
            )

        if self.redoc_url and self.openapi_url:
            app.add_url_rule(
                self.redoc_url, "redoc_ui", self._redoc_ui_route, methods=["GET"]
            )

    def _openapi_route(self) -> Response:
        """Route handler for OpenAPI JSON schema."""
        schema = self.get_openapi_schema()
        return Response(json.dumps(schema), mimetype="application/json")

    def _swagger_ui_route(self) -> Response:
        """Route handler for Swagger UI."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <title>{self.title} - Swagger UI</title>
        </head>
        <body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>
        const ui = SwaggerUIBundle({{
            url: '{self.openapi_url}',
            dom_id: '#swagger-ui',
            presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            deepLinking: true,
            showExtensions: true,
            showCommonExtensions: true
        }})
        </script>
        </body>
        </html>
        """
        return Response(html, mimetype="text/html")

    def _redoc_ui_route(self) -> Response:
        """Route handler for ReDoc UI."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>{self.title} - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
            body {{
            margin: 0;
            padding: 0;
            }}
        </style>
        </head>
        <body>
        <redoc spec-url='{self.openapi_url}'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"> </script>
        </body>
        </html>
        """
        return Response(html, mimetype="text/html")

    def get_openapi_schema(self) -> Dict[str, Any]:
        """Generate or return cached OpenAPI schema."""
        if self._schema_cache:
            return self._schema_cache

        schema = {
            "openapi": "3.0.2",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": {},
            "components": {"schemas": {}},
        }

        # Inspect routes
        routes = getattr(self.app, "_url_rules", [{"rule": r, "endpoint": info["endpoint"], "methods": info["methods"]} for r, info in self.app.url_map.items()])
        for route_info in routes:
            rule = route_info["rule"]
            endpoint_name = route_info["endpoint"]
            methods = route_info["methods"]

            # Skip internal routes
            if endpoint_name in ["openapi_schema", "swagger_ui", "redoc_ui", "static"]:
                continue

            # Get handler function
            view_func = self.app.view_functions.get(endpoint_name)
            if not view_func:
                continue

            path_item = {}

            # Convert Flask rule to OpenAPI path
            # e.g., /user/<int:name> -> /user/{name}
            import re

            openapi_path = re.sub(r"<(?:int:|float:|path:)?([^>]+)>", r"{\1}", rule)

            docstring = inspect.getdoc(view_func) or ""
            summary = docstring.split("\n")[0] if docstring else endpoint_name
            description = docstring

            for method in methods:
                method_lower = method.lower()
                if method_lower not in [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                ]:
                    continue

                operation = {
                    "summary": summary,
                    "description": description,
                    "operationId": f"{endpoint_name}_{method_lower}",
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                        },
                        "400": {
                            "description": "Validation Error",
                        },
                    },
                }

                # Extract path parameters with Path metadata
                if "{" in openapi_path:
                    parameters = []

                    # Extract param names and types from rule
                    param_matches = re.findall(
                        r"<((?:int|float|path)?:?([^>]+))>", rule
                    )
                    param_info = {}
                    for match in param_matches:
                        full_match, param_name = match
                        if ":" in full_match:
                            param_type, _ = full_match.split(":", 1)
                        else:
                            param_type = "str"
                        param_info[param_name] = param_type

                    # Get Path validators from function signature
                    try:
                        from ..params import Path as PathValidator

                        sig = inspect.signature(view_func)

                        for param_name, param_type in param_info.items():
                            # Check if this parameter has a Path validator
                            path_validator = self.app.path_validators.get(
                                (rule, param_name)
                            )

                            # Determine OpenAPI type
                            if param_type == "int":
                                openapi_type = "integer"
                            elif param_type == "float":
                                openapi_type = "number"
                            else:
                                openapi_type = "string"

                            if path_validator and path_validator.include_in_schema:
                                # Use Path validator to generate parameter
                                param_obj = path_validator.to_openapi_parameter(
                                    param_name, openapi_type, required=True
                                )
                                parameters.append(param_obj)
                            else:
                                # Basic parameter without validation
                                parameters.append(
                                    {
                                        "name": param_name,
                                        "in": "path",
                                        "required": True,
                                        "schema": {"type": openapi_type},
                                    }
                                )
                    except Exception:
                        # Fallback to basic parameters if inspection fails
                        param_names = re.findall(r"\{([^}]+)\}", openapi_path)
                        for name in param_names:
                            parameters.append(
                                {
                                    "name": name,
                                    "in": "path",
                                    "required": True,
                                    "schema": {"type": "string"},
                                }
                            )

                    if parameters:
                        operation["parameters"] = parameters

                # Extract query parameters
                query_vals = self.app.query_validators.get((rule, method))
                if query_vals:
                    if "parameters" not in operation:
                        operation["parameters"] = []
                    for q_name, (q_default, q_anno) in query_vals.items():
                        q_type = "string"
                        if q_anno == int:
                            q_type = "integer"
                        elif q_anno == float:
                            q_type = "number"
                        elif q_anno == bool:
                            q_type = "boolean"
                        
                        operation["parameters"].append({
                            "name": q_name,
                            "in": "query",
                            "required": q_default is inspect.Parameter.empty,
                            "schema": {"type": q_type}
                        })

                # Extract request body
                body_vals = self.app.body_validators.get((rule, method))
                if body_vals:
                    # Collect all body parameters into a single object schema
                    props = {}
                    required_props = []
                    for b_name, (b_default, b_anno) in body_vals.items():
                        b_type_str = "string"
                        if b_anno == int:
                            b_type_str = "integer"
                        elif b_anno == float:
                            b_type_str = "number"
                        elif b_anno == bool:
                            b_type_str = "boolean"
                        elif hasattr(b_anno, "__annotations__"):
                            b_type_str = "object"
                        
                        props[b_name] = {"type": b_type_str}
                        if b_default is inspect.Parameter.empty:
                            required_props.append(b_name)
                    
                    schema_ref = {"type": "object", "properties": props}
                    if required_props:
                        schema_ref["required"] = required_props

                    operation["requestBody"] = {
                        "required": len(required_props) > 0,
                        "content": {
                            "application/json": {
                                "schema": schema_ref
                            }
                        }
                    }

                path_item[method_lower] = operation

            if path_item:
                schema["paths"][openapi_path] = path_item

        self._schema_cache = schema
        return schema
