import asyncio

import pytest
from bustapi import BaseUser, BustAPI, LoginManager, current_user
from bustapi.utils import async_to_sync, get_event_loop


# Mock Async ORM that tracks which loop it was initialized in
class MockAsyncORM:
    def __init__(self):
        self.init_loop = None

    async def connect(self):
        # Record the loop that runs this coroutine
        self.init_loop = asyncio.get_running_loop()
        print(f"DEBUG: ORM initialized on loop {id(self.init_loop)}")

    async def get_user_by_id(self, user_id):
        current_loop = asyncio.get_running_loop()
        print(f"DEBUG: ORM accessed on loop {id(current_loop)}")
        if current_loop is not self.init_loop:
            raise RuntimeError(
                f"ORM accessed from wrong loop! "
                f"Init: {id(self.init_loop)}, Current: {id(current_loop)}"
            )
        return {"id": user_id, "username": "testuser"}


orm = MockAsyncORM()


class User(BaseUser):
    def __init__(self, data):
        self.id = data["id"]
        self.username = data["username"]


@pytest.fixture
def app():
    app = BustAPI(__name__)
    app.secret_key = "secret"
    login_manager = LoginManager(app)

    # Initialize the ORM in the background loop
    # In a real app, this would be done once.
    async_to_sync(orm.connect())

    @login_manager.user_loader
    async def load_user(user_id):
        # This is an async user loader using the ORM
        data = await orm.get_user_by_id(user_id)
        return User(data)

    @app.route("/profile")
    def profile():
        # current_user triggers user_loader synchronously via async_to_sync
        if current_user.is_authenticated:
            return f"Hello, {current_user.username}!"
        return "Not logged in", 401

    return app


def test_async_orm_in_sync_context(app):
    client = app.test_client()

    # Simulate a logged-in user session
    with client.session_transaction() as sess:
        sess["_user_id"] = "123"

    # This request will trigger current_user -> user_loader -> orm.get_user_by_id
    response = client.get("/profile")

    assert response.status_code == 200
    assert "Hello, testuser!" in response.text
