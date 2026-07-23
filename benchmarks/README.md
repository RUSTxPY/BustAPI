# ⚡ Ultimate Web Framework Benchmark

> **Date:** 2026-06-17 | **Tool:** `wrk`

## 🖥️ System Spec
- **OS:** `Linux 7.0.0-22-generic`
- **CPU:** `Intel(R) Core(TM) i5-8365U CPU @ 1.60GHz` (8 Cores)
- **RAM:** `15.4 GB`
- **Python:** `3.13.11`

## 🏆 Throughput (Requests/sec)

| Endpoint | Metrics | BustAPI (1w) | Flask (1w) | FastAPI (1w) | Sanic (1w) | Falcon (1w) | Bottle (1w) | Django (1w) | BlackSheep (1w) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`/`** | 🚀 RPS | **19,085** | **2,405** | **3,837** | 🥇 **31,132** | **5,736** | **4,813** | **2,610** | **27,173** |
|  | ⏱️ Avg Latency | 5.23ms | 42.09ms | 27.20ms | 3.99ms | 16.78ms | 20.74ms | 38.01ms | 4.94ms |
|  | 📉 Max Latency | 15.35ms | 151.52ms | 212.60ms | 160.90ms | 30.54ms | 63.38ms | 56.43ms | 195.54ms |
|  | 📦 Transfer | 2.35 MB/s | 0.38 MB/s | 0.54 MB/s | 3.47 MB/s | 0.86 MB/s | 0.76 MB/s | 0.46 MB/s | 3.81 MB/s |
|  | 🔥 CPU Usage | 96% | 95% | 96% | 97% | 87% | 87% | 96% | 97% |
|  | 🧠 RAM Usage | 40.0 MB | 59.8 MB | 55.0 MB | 127.5 MB | 62.5 MB | 56.1 MB | 78.7 MB | 45.6 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |
| **`/json`** | 🚀 RPS | **16,959** | **2,795** | **4,470** | 🥇 **23,909** | **4,991** | **3,835** | **2,432** | **21,985** |
|  | ⏱️ Avg Latency | 5.75ms | 35.60ms | 23.36ms | 6.11ms | 19.93ms | 25.88ms | 40.71ms | 6.78ms |
|  | 📉 Max Latency | 11.71ms | 112.45ms | 206.58ms | 247.57ms | 49.05ms | 44.79ms | 64.51ms | 260.28ms |
|  | 📦 Transfer | 2.02 MB/s | 0.43 MB/s | 0.61 MB/s | 2.55 MB/s | 0.78 MB/s | 0.60 MB/s | 0.42 MB/s | 2.98 MB/s |
|  | 🔥 CPU Usage | 97% | 96% | 94% | 97% | 87% | 90% | 97% | 97% |
|  | 🧠 RAM Usage | 40.0 MB | 59.8 MB | 55.3 MB | 127.6 MB | 62.5 MB | 56.1 MB | 78.7 MB | 45.9 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |
| **`/user/10`** | 🚀 RPS | **12,770** | **2,740** | **3,619** | 🥇 **24,272** | **4,893** | **4,103** | **2,270** | **18,864** |
|  | ⏱️ Avg Latency | 7.81ms | 36.21ms | 29.76ms | 5.78ms | 20.31ms | 23.44ms | 43.62ms | 7.35ms |
|  | 📉 Max Latency | 14.32ms | 59.80ms | 335.66ms | 232.36ms | 30.74ms | 43.44ms | 64.30ms | 264.62ms |
|  | 📦 Transfer | 1.49 MB/s | 0.42 MB/s | 0.48 MB/s | 2.52 MB/s | 0.75 MB/s | 0.63 MB/s | 0.39 MB/s | 2.50 MB/s |
|  | 🔥 CPU Usage | 96% | 96% | 96% | 97% | 89% | 91% | 96% | 97% |
|  | 🧠 RAM Usage | 40.1 MB | 59.8 MB | 55.8 MB | 127.6 MB | 62.5 MB | 56.1 MB | 78.7 MB | 46.6 MB |
| | | --- | --- | --- | --- | --- | --- | --- | --- |

## 📊 Performance Comparison
![RPS Comparison](rps_comparison.png)

## ⚙️ How to Reproduce
```bash
uv run --extra benchmarks benchmarks/run_comparison_auto.py
```