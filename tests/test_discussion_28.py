from dataclasses import dataclass
from unittest.mock import patch

import pytest
from bustapi import BustAPI
from bustapi.auth.decorators import permission_required, roles_required
from bustapi.testing import BustTestClient

app = BustAPI()
app.secret_key = "test_secret"


@dataclass
class MockUser:
    is_authenticated: bool = True
    roles: list = None
    permissions: list = None

    def get_id(self):
        return "123"


# Setup routes
@app.route("/sync-role-or")
@roles_required("admin", "editor")
def sync_role_or():
    return "ok"


@app.route("/sync-role-and")
@roles_required("admin", "editor", require_all=True)
def sync_role_and():
    return "ok"


@app.route("/async-perm-and")
@permission_required("read", "write")
async def async_perm_and():
    return "ok"


@app.route("/async-perm-or")
@permission_required("read", "write", require_all=False)
async def async_perm_or():
    return "ok"


def test_roles_or():
    with patch("bustapi.auth.login.current_user", MockUser(roles=["editor"])):
        with BustTestClient(app) as client:
            assert client.get("/sync-role-or").status_code == 200

    with patch("bustapi.auth.login.current_user", MockUser(roles=["user"])):
        with BustTestClient(app) as client:
            assert client.get("/sync-role-or").status_code == 403


def test_roles_and():
    with patch("bustapi.auth.login.current_user", MockUser(roles=["admin", "editor"])):
        with BustTestClient(app) as client:
            assert client.get("/sync-role-and").status_code == 200

    with patch("bustapi.auth.login.current_user", MockUser(roles=["admin"])):
        with BustTestClient(app) as client:
            assert client.get("/sync-role-and").status_code == 403


def test_perms_and():
    with patch(
        "bustapi.auth.login.current_user", MockUser(permissions=["read", "write"])
    ):
        with BustTestClient(app) as client:
            assert client.get("/async-perm-and").status_code == 200

    with patch("bustapi.auth.login.current_user", MockUser(permissions=["read"])):
        with BustTestClient(app) as client:
            assert client.get("/async-perm-and").status_code == 403


def test_perms_or():
    with patch("bustapi.auth.login.current_user", MockUser(permissions=["read"])):
        with BustTestClient(app) as client:
            assert client.get("/async-perm-or").status_code == 200

    with patch("bustapi.auth.login.current_user", MockUser(permissions=["delete"])):
        with BustTestClient(app) as client:
            assert client.get("/async-perm-or").status_code == 403
