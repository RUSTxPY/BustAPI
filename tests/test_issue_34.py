"""Discussion #34 — Blueprint() should not require import_name explicitly."""

import pytest
from bustapi import Blueprint, BustAPI


def test_blueprint_import_name_defaults_to_calling_module():
    bp = Blueprint("api", url_prefix="/api")
    assert bp.import_name == __name__


def test_blueprint_import_name_explicit_still_works():
    bp = Blueprint("api", __name__, url_prefix="/api")
    assert bp.import_name == __name__


def test_blueprint_name_is_required():
    with pytest.raises(TypeError):
        Blueprint()


def test_blueprint_name_must_be_non_empty():
    with pytest.raises(ValueError):
        Blueprint("")
    with pytest.raises(ValueError):
        Blueprint(None)


def test_blueprint_without_import_name_registers_routes():
    app = BustAPI()
    bp = Blueprint("api", url_prefix="/api")

    @bp.get("/health")
    def health():
        return {"ok": True}

    app.register_blueprint(bp)

    assert "/api/health" in app.url_map
    assert app.url_map["/api/health"]["endpoint"] == "api.health"
    assert app.blueprints["api"] is bp


def test_app_import_name_autodetect_unchanged():
    app = BustAPI()
    assert app.import_name != ""
    assert isinstance(app.import_name, str)
