import subprocess
import time
import requests
import os
import signal

# 1. Start the app
print("Starting Turbomax App...")
app_process = subprocess.Popen([".venv/bin/python", "benchmarks/turbomax_app.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2) # wait for app to start

try:
    # 2. Get JWT token
    print("Logging in to get JWT token...")
    session = requests.Session()
    
    # Retry mechanism
    max_retries = 10
    resp = None
    for i in range(max_retries):
        try:
            resp = session.post("http://127.0.0.1:8080/login")
            break
        except requests.exceptions.ConnectionError:
            print(f"Waiting for app to start... (Attempt {i+1}/{max_retries})")
            time.sleep(1)
            
    if not resp:
        raise Exception("Failed to connect to app")
        
    cookies = resp.cookies.get_dict()
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    print(f"Cookie: {cookie_header}")

    results = []

    # 3a. Run wrk on /api/business_logic (jsonify route)
    print("\n=== Route 1: /api/business_logic (jsonify) ===")
    wrk_cmd = [
        "wrk",
        "-t2",
        "-c10",
        "-d20s",
        "-H", f"Cookie: {cookie_header}",
        "http://127.0.0.1:8080/api/business_logic?sort_by=name"
    ]
    result = subprocess.run(wrk_cmd, capture_output=True, text=True)
    print(result.stdout)
    results.append("=== Route 1: /api/business_logic (jsonify) ===\n")
    results.append(result.stdout)

    # 3b. Run wrk on /api/business_logic_raw (raw dict)
    print("\n=== Route 2: /api/business_logic_raw (raw dict → Rust serialization) ===")
    wrk_cmd = [
        "wrk",
        "-t2",
        "-c10",
        "-d20s",
        "-H", f"Cookie: {cookie_header}",
        "http://127.0.0.1:8080/api/business_logic_raw?sort_by=name"
    ]
    result = subprocess.run(wrk_cmd, capture_output=True, text=True)
    print(result.stdout)
    results.append("\n=== Route 2: /api/business_logic_raw (raw dict → Rust serialization) ===\n")
    results.append(result.stdout)
    
    # 4. Save results
    os.makedirs("benchmarks", exist_ok=True)
    with open("benchmarks/turbomax_baseline.txt", "w") as f:
        f.writelines(results)
    print("Saved results to benchmarks/turbomax_baseline.txt")

finally:
    # 5. Kill app
    print("Cleaning up app...")
    app_process.send_signal(signal.SIGINT)
    app_process.wait()
