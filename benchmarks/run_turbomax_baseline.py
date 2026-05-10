import subprocess
import time
import requests
import os
import signal
import sys

# Turbomax Benchmark Runner v2.0
print("Starting Turbomax App (Optimized)...")
env = os.environ.copy()
env["PYTHONPATH"] = "."
app_process = subprocess.Popen(
    [sys.executable, "benchmarks/turbomax_app.py"], 
    stdout=subprocess.DEVNULL, 
    stderr=subprocess.DEVNULL,
    env=env
)
time.sleep(2)

try:
    print("Authenticating...")
    session = requests.Session()
    resp = session.post("http://127.0.0.1:8080/login")
    
    if not resp.ok:
        raise Exception(f"Login failed: {resp.status_code}")
        
    cookies = resp.cookies.get_dict()
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    print(f"Authentication successful. Token acquired.")

    def run_wrk(name, url):
        print(f"\n>>> Running Benchmark: {name}")
        print(f"Target: {url}")
        wrk_cmd = [
            "wrk", "-t2", "-c10", "-d15s",
            "-H", f"Cookie: {cookie_header}",
            url
        ]
        res = subprocess.run(wrk_cmd, capture_output=True, text=True)
        print(res.stdout)
        return f"\n=== {name} ===\n{res.stdout}"

    results = []
    # Test Route 1
    results.append(run_wrk("Route 1: jsonify (Deferred Serialization)", "http://127.0.0.1:8080/api/business_logic?sort_by=name"))
    
    # Test Route 2
    results.append(run_wrk("Route 2: raw dict (Zero-Copy Rust Serialization)", "http://127.0.0.1:8080/api/business_logic_raw?sort_by=name"))
    
    with open("benchmarks/turbomax_baseline.txt", "w") as f:
        f.writelines(results)
    print("\n✅ All results saved to benchmarks/turbomax_baseline.txt")

finally:
    print("Shutting down app...")
    app_process.send_signal(signal.SIGINT)
    app_process.wait()
