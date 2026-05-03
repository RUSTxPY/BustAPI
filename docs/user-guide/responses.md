# Responses

BustAPI is flexible in what you can return from a view function. It attempts to smartly convert your return values into a valid HTTP response.

## Return Types

### Strings

Returning a plain string results in a `text/html` response with a `200 OK` status.

```python
@app.route("/")
def home():
    return "<h1>Hello</h1>"
```

### Dictionaries & Lists

Returning a dictionary or a list will automatically serialize it to JSON and set the content-type to `application/json`.

```python
@app.route("/api/user")
def user():
    return {"name": "Alice", "role": "admin"}
```

### Tuples

You can return a tuple in the form `(body, status)` or `(body, status, headers)`.

```python
@app.route("/created")
def created():
    return {"id": 123}, 201, {"X-Custom-Header": "foo"}
```

## The `make_response` Helper

For more control, wrap your content in a `Response` object.

```python
from bustapi import make_response

@app.route("/xml")
def xml():
    resp = make_response("<data>value</data>")
```

## Headers

BustAPI provides a robust `Headers` object that supports case-insensitive access and multi-value headers.

### Accessing Headers

Headers are case-insensitive, so `resp.headers['Content-Type']` is the same as `resp.headers['content-type']`.

```python
from bustapi import make_response

@app.route("/")
def home():
    resp = make_response("Hello")
    resp.headers["X-Custom"] = "Value"
    # Case-insensitive access
    print(resp.headers["x-custom"])  # "Value"
    return resp
```

### Multi-Value Headers

To add multiple values for the same header (e.g., multiple `Link` or `Set-Cookie` headers), use the `.add()` method instead of assignment.

```python
resp.headers.add("Link", "<https://example.com/p1>; rel=\"prev\"")
resp.headers.add("Link", "<https://example.com/p3>; rel=\"next\"")

# Get all values as a list
links = resp.headers.getlist("Link")
```

## Cookies

You can set and delete cookies easily using the `Response` object.

### Setting Cookies

```python
@app.route("/set-cookie")
def set_cookie():
    resp = make_response("Cookie set!")
    resp.set_cookie(
        "user_id", 
        "123", 
        max_age=3600, 
        httponly=True, 
        samesite="Lax",
        secure=True
    )
    return resp
```

### Deleting Cookies

```python
@app.route("/logout")
def logout():
    resp = make_response("Logged out")
    resp.delete_cookie("user_id", path="/", domain=None)
    return resp
```

### StreamingResponse

You can stream data to the client using `StreamingResponse`. This is highly efficient as it uses the Rust backend to poll your iterator without blocking other requests. It supports both synchronous and asynchronous iterators.

```python
from bustapi import StreamingResponse
import asyncio

async def fast_stream():
    for i in range(10):
        yield f"Chunk {i}\n"
        await asyncio.sleep(0.1)

@app.route("/stream")
async def stream():
    # Rust handles the streaming polling in the background
    return StreamingResponse(fast_stream(), media_type="text/plain")
```

### FileResponse

For serving files efficiently, use `FileResponse`. It uses the Rust backend's zero-copy file serving (via `actix-files`), making it significantly faster than reading files into memory in Python.

```python
from bustapi import FileResponse

@app.route("/download")
def download():
    return FileResponse(
        path="path/to/large_file.zip",
        media_type="application/zip",
        filename="custom_name.zip"
    )
```

`FileResponse` also automatically supports **HTTP Range Requests**, allowing browsers to seek through videos or resume large downloads.

## Redirections & Errors

Use the helper functions `redirect` and `abort`.

```python
from bustapi import redirect, abort

@app.route("/old")
def old():
    return redirect("/new")

@app.route("/protected")
def protected():
    if not is_authorized:
        abort(403, "You shall not pass!")
```
