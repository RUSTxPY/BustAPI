# Error Handling

Applications fail. BustAPI allows you to handle these failures gracefully.

## Handling HTTP Errors

You can use the `errorhandler` decorator to catch specific HTTP status codes.

```python
from bustapi import render_template

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404
```

## Handling Exceptions

You can also handle generic Python exceptions.

```python
@app.errorhandler(ValueError)
def handle_value_error(e):
    return {"error": "Invalid value provided", "details": str(e)}, 400
```

## Raising Errors

You can stop request processing and return an error manually using `abort()`.

```python
from bustapi import abort

@app.route("/admin")
def admin():
    if not is_admin():
        abort(403, description="Admins only!")
    return "Welcome Admin"
```

## Catch-All Error Handler

To handle any unhandled exception (the "else" block), you can register a handler for the base `Exception` class.

```python
@app.errorhandler(Exception)
def handle_unexpected_error(e):
    # Log the error
    app.logger.error(f"Unexpected error: {e}")
    
    # If it's already an HTTP error, let it handle itself
    if hasattr(e, "get_response"):
        return e.get_response()
        
    return {"error": "An internal error occurred"}, 500
```

## Custom Exceptions

You can create your own exception classes and register handlers for them.

```python
class PaymentRequired(Exception):
    pass

@app.errorhandler(PaymentRequired)
def handle_payment_required(e):
    return "Please pay to continue", 402
```
