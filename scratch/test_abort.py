import pytest
from bustapi import BustAPI, abort, make_response


def test_abort_404():
    app = BustAPI(__name__)

    @app.route("/error")
    def error():
        abort(404, "Custom 404 Message")

    client = app.test_client()
    resp = client.get("/error")

    assert resp.status_code == 404
    assert resp.get_data(as_text=True) == "Custom 404 Message"


if __name__ == "__main__":
    pytest.main([__file__])
