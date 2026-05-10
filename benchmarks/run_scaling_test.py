import subprocess
import time
import requests
import os
import signal
import sys

# Multiprocess Scaling Test
workers = 4
print(f"Starting Turbomax App with {workers} workers (SO_REUSEPORT)...")
env = os.environ.copy()
env["PYTHONPATH"] = "."
app_process = subprocess.Popen(
    [sys.executable, "benchmarks/turbomax_app_multi.py"], 
    stdout=subprocess.PIPE, 
    stderr=subprocess.PIPE,
    env=env,
    text=True
)

# Wait for banner to appear to ensure all processes started
time.sleep(5)

try:
    print("Authenticating...")
    session = requests.Session()
    resp = session.post("http://127.0.0.1:8080/login")
    
    if not resp.ok:
        raise Exception(f"Login failed: {resp.status_code}")
        
    cookies = resp.cookies.get_dict()
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    print(f"Authentication successful.")

    print(f"\n>>> Running Benchmark: 4 Workers (SO_REUSEPORT)")
    wrk_cmd = [
        "wrk", "-t4", "-c100", "-d10s",
        "-H", f"Cookie: {cookie_header}",
        "http://127.0.0.1:8080/api/business_logic_raw?sort_by=name"
    ]
    res = subprocess.run(wrk_cmd, capture_output=True, text=True)
    print(res.stdout)

finally:
    print("Shutting down...")
    app_process.terminate()
    app_process.wait()
