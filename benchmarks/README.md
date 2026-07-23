# ⚡ Ultimate Web Framework Benchmark

> **Date:** 2026-07-23 | **Tool:** `wrk`

## 🖥️ System Spec
- **OS:** `Linux 7.0.0-28-generic`
- **CPU:** `Intel(R) Core(TM) i5-8365U CPU @ 1.60GHz` (8 Cores)
- **RAM:** `15.4 GB`
- **Python:** `3.13.11`

## 🏆 Throughput (Requests/sec)

| Endpoint | Metrics | BustAPI (1w) | Flask (1w) | FastAPI (1w) | Sanic (1w) | Falcon (1w) | Bottle (1w) | Django (1w) | BlackSheep (1w) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`/`** | 🚀 RPS | 🥇 **33,241** | **1,563** | **2,803** | **13,524** | **4,140** | **3,526** | **1,165** | **12,271** |
|  | ⏱️ Avg Latency | 15.05ms | 63.10ms | 44.30ms | 11.51ms | 23.91ms | 28.05ms | 84.38ms | 9.73ms |
|  | 📉 Max Latency | 285.38ms | 94.81ms | 486.31ms | 351.19ms | 35.00ms | 41.98ms | 152.84ms | 273.31ms |
|  | 📦 Transfer | 4.09 MB/s | 0.25 MB/s | 0.39 MB/s | 1.51 MB/s | 0.62 MB/s | 0.56 MB/s | 0.20 MB/s | 1.72 MB/s |
|  | 🔥 CPU Usage | 209% | 97% | 92% | 95% | 96% | 96% | 94% | 95% |
|  | 🧠 RAM Usage | 35.7 MB | 57.5 MB | 55.7 MB | 127.6 MB | 61.6 MB | 53.4 MB | 77.2 MB | 45.5 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |
| **`/json`** | 🚀 RPS | 🥇 **32,392** | **1,486** | **2,689** | **13,131** | **3,833** | **3,174** | **1,151** | **10,243** |
|  | ⏱️ Avg Latency | 16.84ms | 66.26ms | 37.44ms | 11.33ms | 25.80ms | 31.19ms | 85.61ms | 14.01ms |
|  | 📉 Max Latency | 325.09ms | 93.35ms | 231.47ms | 363.74ms | 44.58ms | 48.43ms | 132.16ms | 413.84ms |
|  | 📦 Transfer | 3.86 MB/s | 0.23 MB/s | 0.36 MB/s | 1.40 MB/s | 0.60 MB/s | 0.49 MB/s | 0.20 MB/s | 1.39 MB/s |
|  | 🔥 CPU Usage | 215% | 96% | 95% | 96% | 96% | 96% | 96% | 96% |
|  | 🧠 RAM Usage | 37.5 MB | 57.5 MB | 56.9 MB | 127.6 MB | 61.7 MB | 53.5 MB | 77.3 MB | 45.6 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |
| **`/user/10`** | 🚀 RPS | 🥇 **21,824** | **1,385** | **2,368** | **12,727** | **3,648** | **3,071** | **1,163** | **11,317** |
|  | ⏱️ Avg Latency | 24.58ms | 71.01ms | 43.13ms | 8.97ms | 27.14ms | 32.17ms | 84.50ms | 10.32ms |
|  | 📉 Max Latency | 539.94ms | 105.21ms | 300.74ms | 251.70ms | 42.89ms | 48.49ms | 155.54ms | 312.62ms |
|  | 📦 Transfer | 2.54 MB/s | 0.21 MB/s | 0.31 MB/s | 1.32 MB/s | 0.56 MB/s | 0.47 MB/s | 0.20 MB/s | 1.50 MB/s |
|  | 🔥 CPU Usage | 197% | 96% | 94% | 96% | 96% | 96% | 94% | 96% |
|  | 🧠 RAM Usage | 37.8 MB | 57.5 MB | 57.0 MB | 127.7 MB | 61.7 MB | 53.5 MB | 77.3 MB | 46.2 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |

## 📊 Performance Comparison
![RPS Comparison](rps_comparison.png)

## ⚙️ How to Reproduce
```bash
uv run --extra benchmarks benchmarks/run_comparison_auto.py
```