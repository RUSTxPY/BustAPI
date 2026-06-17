import asyncio

import pytest
from bustapi import BustAPI, current_user, login_required
from bustapi.auth import BaseUser, LoginManager, login_user
from bustapi.testing import BustTestClient


class User(BaseUser):
    def __init__(self, id, name):
        self.id = id
        self.name = name

    def get_id(self):
        return str(self.id)


def test_async_user_loader():
    app = BustAPI()
    app.secret_key = "test-secret"
    login_manager = LoginManager(app)

    # Mock async database
    async def get_user_from_db(user_id):
        await asyncio.sleep(0.01)  # Simulate I/O
        if user_id == "1":
            return User(1, "Async User")
        return None

    @login_manager.user_loader
    async def load_user(user_id):
        return await get_user_from_db(user_id)

    @app.route("/profile")
    @login_required
    async def profile():
        return {"id": current_user.id, "name": current_user.name}

    client = BustTestClient(app)

    # 1. Login
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"

    # 2. Access profile (should trigger async load_user)
    response = client.get("/profile")
    if response.status_code != 200:
        print(response.data.decode())
    assert response.status_code == 200
    assert response.json == {"id": 1, "name": "Async User"}


def test_sync_user_loader_still_works():
    app = BustAPI()
    app.secret_key = "test-secret"
    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == "1":
            return User(1, "Sync User")
        return None

    @app.route("/profile")
    @login_required
    def profile():
        return {"id": current_user.id, "name": current_user.name}

    client = BustTestClient(app)

    with client.session_transaction() as sess:
        sess["_user_id"] = "1"

    response = client.get("/profile")
    if response.status_code != 200:
        print(response.data.decode())
    assert response.status_code == 200
    assert response.json == {"id": 1, "name": "Sync User"}


def test_login_user_with_async_user_loader():
    app = BustAPI()
    app.secret_key = "test-secret"
    login_manager = LoginManager(app)

    async def get_user_from_db(user_id):
        await asyncio.sleep(0.001)
        if user_id == "42":
            return User(42, "Direct Async User")
        return None

    @login_manager.user_loader
    async def load_user(user_id):
        return await get_user_from_db(user_id)

    @app.route("/login-raw")
    def login_raw():
        # Call login_user with raw ID
        login_user("42")
        # Check if the resolved user is loaded immediately
        return {"id": current_user.id, "name": current_user.name}

    client = BustTestClient(app)
    response = client.get("/login-raw")
    assert response.status_code == 200
    assert response.json == {"id": 42, "name": "Direct Async User"}


if __name__ == "__main__":
    pytest.main([__file__])
