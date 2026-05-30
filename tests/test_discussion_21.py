"""Tests for roles_required and permission_required (Discussion #21)."""

import pytest
from bustapi import BustAPI, current_user
from bustapi.auth import (
    BaseUser,
    LoginManager,
    login_user,
    permission_required,
    roles_required,
)
from bustapi.testing import BustTestClient


class AdminUser(BaseUser):
    def __init__(self, id):
        self.id = id
        self.role = "admin"
        self.permissions = ["posts:delete", "users:read"]


class ModUser(BaseUser):
    def __init__(self, id):
        self.id = id
        self.role = "moderator"
        self.permissions = ["users:read"]


class RoleListUser(BaseUser):
    """User with .roles as a list (plural form)."""

    def __init__(self, id):
        self.id = id
        self.roles = ["admin", "editor"]


class CallablePermUser(BaseUser):
    """User with callable .permissions."""

    def __init__(self, id):
        self.id = id
        self._perms = ["special:access"]

    @property
    def permissions(self):
        return self._perms


USERS = {
    "1": AdminUser(1),
    "2": ModUser(2),
    "3": RoleListUser(3),
    "4": CallablePermUser(4),
}


def _make_app():
    app = BustAPI()
    app.secret_key = "test-secret"
    lm = LoginManager(app)

    @lm.user_loader
    def load_user(user_id):
        return USERS.get(user_id)

    return app


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = user_id


def test_roles_required_single_role():
    """@roles_required passes when user has matching role (singular .role)."""
    app = _make_app()

    @app.route("/admin")
    @roles_required("admin")
    def admin_panel():
        return {"ok": True}

    client = BustTestClient(app)
    _login(client, "1")

    resp = client.get("/admin")
    assert resp.status_code == 200
    assert resp.json == {"ok": True}


def test_roles_required_fails_when_role_mismatch():
    """@roles_required returns 403 when user lacks required role."""
    app = _make_app()

    @app.route("/admin")
    @roles_required("admin")
    def admin_panel():
        return {"ok": True}

    client = BustTestClient(app)
    _login(client, "2")

    resp = client.get("/admin")
    assert resp.status_code == 403


def test_roles_required_plural_roles():
    """@roles_required works with .roles (plural list attribute)."""
    app = _make_app()

    @app.route("/admin")
    @roles_required("admin")
    def admin_panel():
        return {"ok": True}

    client = BustTestClient(app)
    _login(client, "3")

    resp = client.get("/admin")
    assert resp.status_code == 200
    assert resp.json == {"ok": True}


def test_permission_required_passes():
    """@permission_required passes when user has the required permission."""
    app = _make_app()

    @app.route("/delete-post")
    @permission_required("posts:delete")
    def delete_post():
        return {"deleted": True}

    client = BustTestClient(app)
    _login(client, "1")

    resp = client.get("/delete-post")
    assert resp.status_code == 200
    assert resp.json == {"deleted": True}


def test_permission_required_fails():
    """@permission_required returns 403 when user lacks permission."""
    app = _make_app()

    @app.route("/delete-post")
    @permission_required("posts:delete")
    def delete_post():
        return {"deleted": True}

    client = BustTestClient(app)
    _login(client, "2")

    resp = client.get("/delete-post")
    assert resp.status_code == 403


def test_permission_required_multiple():
    """@permission_required requires ALL permissions."""
    app = _make_app()

    @app.route("/full-access")
    @permission_required("posts:delete", "users:read")
    def full_access():
        return {"ok": True}

    client = BustTestClient(app)
    _login(client, "1")

    resp = client.get("/full-access")
    assert resp.status_code == 200
    assert resp.json == {"ok": True}


def test_permission_required_callable():
    """@permission_required works with callable .permissions."""
    app = _make_app()

    @app.route("/special")
    @permission_required("special:access")
    def special():
        return {"ok": True}

    client = BustTestClient(app)
    _login(client, "4")

    resp = client.get("/special")
    assert resp.status_code == 200
    assert resp.json == {"ok": True}


def test_auth_required_before_role_check():
    """Unauthenticated users get 401, not 403."""
    app = _make_app()

    @app.route("/admin")
    @roles_required("admin")
    def admin_panel():
        return {"ok": True}

    client = BustTestClient(app)

    resp = client.get("/admin")
    assert resp.status_code == 401


def test_exact_discussion_21_example():
    """Reproduce the exact code pattern from discussion #21 answer."""
    app = BustAPI()
    app.secret_key = "test-secret"
    lm = LoginManager(app)

    class User(BaseUser):
        def __init__(self, id):
            self.id = id
            self.role = "admin"
            self.permissions = ["posts:delete", "users:read"]

    @lm.user_loader
    def load_user(user_id):
        return User(1)

    @app.route("/admin")
    @roles_required("admin")
    def admin():
        return {"ok": True}

    @app.route("/posts/delete")
    @permission_required("posts:delete")
    def delete_post():
        return {"deleted": True}

    client = BustTestClient(app)

    _login(client, "1")

    resp_admin = client.get("/admin")
    assert resp_admin.status_code == 200
    assert resp_admin.json == {"ok": True}

    resp_delete = client.get("/posts/delete")
    assert resp_delete.status_code == 200
    assert resp_delete.json == {"deleted": True}
