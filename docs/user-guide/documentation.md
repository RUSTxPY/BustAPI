# Auto-Documentation

BustAPI provides automatic OpenAPI (Swagger) and ReDoc documentation for your application via the `BustAPIDocs` extension. It extracts information from route signatures, docstrings, and parameter validators.

## Basic Setup

Initialize the `BustAPIDocs` extension with your application to enable the documentation endpoints.

```python
from bustapi import BustAPI, BustAPIDocs

app = BustAPI()

# Configure auto-documentation
docs = BustAPIDocs(
    app,
    title="My Store API",
    version="1.0.0",
    description="API for managing items and users",
    docs_url="/docs",       # Swagger UI path
    redoc_url="/redoc",     # ReDoc path
    openapi_url="/openapi.json"
)
```

## Documenting Parameters

BustAPI automatically documents parameters defined in your route handlers using `Path`, `Query`, and `Body` validators.

### Query Parameters

Use `Query()` to add constraints and metadata to query strings.

```python
from bustapi import Query

@app.route("/search")
def search(
    q: str = Query(..., min_length=3, description="Search query"),
    page: int = Query(1, ge=1, description="Page number")
):
    return {"q": q, "page": page}
```

### Path Parameters

`Path()` works similarly for URL path segments.

```python
from bustapi import Path

@app.route("/items/<int:item_id>")
def get_item(item_id: int = Path(..., ge=1, title="Item ID")):
    return {"id": item_id}
```

### Request Bodies

The `Body()` validator documents JSON request bodies. You can provide a `schema` dictionary to define fields and their constraints.

```python
from bustapi import Body

@app.route("/items", methods=["POST"])
def create_item(
    item: dict = Body(..., schema={
        "name": {"type": "str", "min_length": 1, "description": "Item name"},
        "price": {"type": "float", "gt": 0, "description": "Price in USD"},
        "tags": {"type": "list", "required": False}
    })
):
    return {"created": item}
```

## Route Metadata

You can further customize documentation for specific routes using decorator arguments:

```python
@app.route(
    "/protected", 
    methods=["GET"],
    tags=["Security"],
    summary="Access protected resource",
    description="This endpoint requires an active session.",
    deprecated=True
)
def protected_route():
    return {"status": "ok"}
```

### Custom Responses

Define specific response codes and their descriptions:

```python
@app.route(
    "/items/<int:id>",
    responses={
        200: {"description": "Item found"},
        404: {"description": "Item not in database"}
    }
)
def get_item_with_docs(id):
    return {"id": id}
```

## Response Models

If you use `Struct` from `bustapi.safe.types`, you can specify it as a `response_model` to automatically generate a reusable schema in the documentation.

```python
from bustapi.safe.types import Struct

class Item(Struct):
    id: int
    name: str

@app.route("/item", response_model=Item)
def get_item_model():
    return Item(id=1, name="Tool")
```

## UI Endpoints

Once initialized, your documentation is accessible at:

- **Swagger UI**: `http://127.0.0.1:5000/docs` (interactive "Try it out" support)
- **ReDoc**: `http://127.0.0.1:5000/redoc` (clean, readable layout)
- **OpenAPI JSON**: `http://127.0.0.1:5000/openapi.json` (raw specification)
