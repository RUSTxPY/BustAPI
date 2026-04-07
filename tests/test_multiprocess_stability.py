import multiprocessing
import os
import signal
import socket
import subprocess
import sys
import time

import psutil
import pytest
import requests
from bustapi import BustAPI

# Ensure PYTHONPATH is in sub-processes
BUSTAPI_PATH = os.path.join(os.getcwd(), "python")


def test_spawn_environment_stability():
    """Test that BustAPI works even if the global start method is 'spawn'."""
    server_file = "tmp_spawn_test.py"
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    content = f"""
import os
import sys
import multiprocessing
import time

# Force spawn globally as early as possible
try:
    multiprocessing.set_start_method('spawn', force=True)
except RuntimeError:
    pass

sys.path.insert(0, '{BUSTAPI_PATH}')
from bustapi import BustAPI
app = BustAPI()

@app.route('/test')
def test_route():
    return "OK"

if __name__ == '__main__':
    # Start with 2 workers
    app.run(workers=2, port={port}, debug=False)
"""
    with open(server_file, "w") as f:
        f.write(content)

    # We use env to pass PYTHONPATH too
    env = os.environ.copy()
    env["PYTHONPATH"] = BUSTAPI_PATH

    proc = subprocess.Popen(
        [sys.executable, server_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    time.sleep(5)  # Give it time to spawn

    try:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            pytest.fail("Server process died early in spawn mode")

        resp = requests.get(f"http://127.0.0.1:{port}/test", timeout=5)
        assert resp.status_code == 200
        assert resp.text == "OK"
        print("Successfully verified responsiveness in spawn mode.")
    finally:
        # Proper cleanup of process tree
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        if os.path.exists(server_file):
            os.remove(server_file)


def test_signal_propagation_to_workers():
    """Test that killing the parent also cleans up the workers."""
    server_file = "tmp_signal_test_3.py"
    port = 5097
    content = f"""
import os
import sys
sys.path.insert(0, '{BUSTAPI_PATH}')
from bustapi import BustAPI
app = BustAPI()
@app.route('/')
def home(): return 'ok'
if __name__ == '__main__':
    app.run(workers=2, port={port})
"""
    with open(server_file, "w") as f:
        f.write(content)

    proc = subprocess.Popen(
        [sys.executable, server_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(5)

    try:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            pytest.fail("Server process died early")

        parent = psutil.Process(proc.pid)
        worker_pids = [c.pid for c in parent.children()]
        assert len(worker_pids) >= 2

        # Send SIGINT to parent
        proc.send_signal(signal.SIGINT)

        # Polling loop to wait for workers to exit (up to 15 seconds)
        for _ in range(15):
            alive_workers = [pid for pid in worker_pids if psutil.pid_exists(pid)]
            if not alive_workers:
                break
            time.sleep(1)

        # Check if workers are gone
        for pid in worker_pids:
            assert not psutil.pid_exists(pid), f"Worker process {pid} still alive!"
    finally:
        if proc.poll() is None:
            proc.kill()
        if os.path.exists(server_file):
            os.remove(server_file)


def test_route_inheritance_across_workers():
    """Verify that routes registered before app.run() are inherited by workers."""
    server_file = "tmp_inheritance_test_3.py"
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    content = f"""
import os
import sys
sys.path.insert(0, '{BUSTAPI_PATH}')
from bustapi import BustAPI
app = BustAPI()
@app.route('/alpha')
def alpha(): return 'ALPHA'
@app.route('/beta')
def beta(): return 'BETA'
if __name__ == '__main__':
    app.run(workers=2, port={port})
"""
    with open(server_file, "w") as f:
        f.write(content)

    proc = subprocess.Popen(
        [sys.executable, server_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(5)

    try:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            pytest.fail("Server process died early")

        r1 = requests.get(f"http://127.0.0.1:{port}/alpha", timeout=5)
        assert r1.status_code == 200
        assert r1.text == "ALPHA"

        r2 = requests.get(f"http://127.0.0.1:{port}/beta", timeout=5)
        assert r2.status_code == 200
        assert r2.text == "BETA"
    finally:
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        if os.path.exists(server_file):
            os.remove(server_file)


def test_so_reuseport_validation():
    """Verify that multiple workers use SO_REUSEPORT correctly on Linux."""
    if os.uname().sysname != "Linux":
        pytest.skip("SO_REUSEPORT is primarily tested on Linux")

    server_file = "tmp_reuseport_test_3.py"
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    content = f"""
import os
import sys
sys.path.insert(0, '{BUSTAPI_PATH}')
from bustapi import BustAPI
app = BustAPI()
@app.route('/ping')
def ping(): return 'pong'
if __name__ == '__main__':
    app.run(workers=2, port={port})
"""
    with open(server_file, "w") as f:
        f.write(content)

    proc = subprocess.Popen(
        [sys.executable, server_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(5)

    try:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            pytest.fail("Server process died early")

        resp = requests.get(f"http://127.0.0.1:{port}/ping", timeout=2)
        assert resp.status_code == 200
        assert resp.text == "pong"

        parent = psutil.Process(proc.pid)
        assert len(parent.children()) >= 2
    finally:
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        if os.path.exists(server_file):
            os.remove(server_file)
