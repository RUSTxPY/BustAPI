import asyncio

import pytest
from bustapi import BustAPI, Response
from bustapi.testing import BustTestClient


def test_async_post_request_hooks():
    app = BustAPI()

    hook_data = {"after": False, "teardown": False}

    @app.route("/")
    def index():
        return "Hello"

    @app.after_request
    async def after(response):
        await asyncio.sleep(0.01)
        hook_data["after"] = True
        return response

    @app.teardown_request
    async def teardown(exc):
        await asyncio.sleep(0.01)
        hook_data["teardown"] = True

    client = BustTestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.text == "Hello"
    assert hook_data["after"] is True
    assert hook_data["teardown"] is True


def test_async_after_request_modifies_response():
    app = BustAPI()

    @app.route("/")
    def index():
        return "Original"

    @app.after_request
    async def after(response):
        await asyncio.sleep(0.01)
        return Response("Modified")

    client = BustTestClient(app)
    response = client.get("/")

    assert response.text == "Modified"


if __name__ == "__main__":
    pytest.main([__file__])
