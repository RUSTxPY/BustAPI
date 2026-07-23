import os
import tempfile

import pytest
from bustapi import BustAPI


def test_https_ssl_context_parameter(capsys):
    app = BustAPI(__name__)

    @app.route("/")
    def index():
        return "HTTPS Hello"

    # Verify that app.run accepts ssl_context without erroring on signature
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = os.path.join(tmpdir, "cert.pem")
        key_path = os.path.join(tmpdir, "key.pem")

        # Write dummy files to verify path passing logic
        with open(cert_path, "w") as f:
            f.write("dummy cert")
        with open(key_path, "w") as f:
            f.write("dummy key")

        # Test parameter unpacking in python layer
        ssl_tuple = (cert_path, key_path)

        app.run(host="127.0.0.1", port=9999, workers=1, ssl_context=ssl_tuple)
        captured = capsys.readouterr()
        assert "No valid certificates found" in captured.out
