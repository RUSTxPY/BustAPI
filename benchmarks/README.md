# ⚡ Ultimate Web Framework Benchmark

> **Date:** 2026-05-10 | **Tool:** `wrk`

## 🖥️ System Spec
- **OS:** `Linux 7.0.0-14-generic`
- **CPU:** `Intel(R) Core(TM) i5-8365U CPU @ 1.60GHz` (8 Cores)
- **RAM:** `15.4 GB`
- **Python:** `3.13.11`

## 🏆 Throughput (Requests/sec)

| Endpoint | Metrics | BustAPI Fast (v0.15.0) (1w) | BustAPI Turbo (v0.15.0) (1w) | BustAPI Normal (v0.15.0) (1w) | Catzilla (v0.2.2) (1w) | Flask (v3.1.3) (4w) | FastAPI (v0.136.1) (4w) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`/`** | 🚀 RPS | 🥇 **252,196** | **38,846** | **41,167** | **20,498** | **7,323** | **11,953** |
|  | ⏱️ Avg Latency | 0.64ms | 2.58ms | 2.45ms | 5.23ms | 13.53ms | 8.48ms |
|  | 📉 Max Latency | 21.45ms | 18.34ms | 23.90ms | 151.21ms | 29.21ms | 55.31ms |
|  | 📦 Transfer | 29.10 MB/s | 4.78 MB/s | 5.10 MB/s | 2.87 MB/s | 1.16 MB/s | 1.68 MB/s |
|  | 🔥 CPU Usage | 436% | 201% | 208% | 96% | 381% | 398% |
|  | 🧠 RAM Usage | 55.9 MB | 56.1 MB | 55.9 MB | 30.6 MB | 161.6 MB | 250.6 MB |
| | | --- | --- | --- | --- | --- | --- |
| **`/json`** | 🚀 RPS | 🥇 **235,900** | **30,393** | **31,881** | **23,524** | **5,920** | **12,269** |
|  | ⏱️ Avg Latency | 0.66ms | 3.32ms | 3.12ms | 4.39ms | 16.78ms | 8.17ms |
|  | 📉 Max Latency | 19.86ms | 11.69ms | 11.46ms | 110.25ms | 39.99ms | 34.98ms |
|  | 📦 Transfer | 28.35 MB/s | 3.62 MB/s | 3.80 MB/s | 2.51 MB/s | 0.92 MB/s | 1.66 MB/s |
|  | 🔥 CPU Usage | 428% | 196% | 173% | 96% | 367% | 395% |
|  | 🧠 RAM Usage | 53.8 MB | 53.7 MB | 54.1 MB | 30.6 MB | 161.7 MB | 252.2 MB |
| | | --- | --- | --- | --- | --- | --- |
| **`/user/10`** | 🚀 RPS | 🥇 **238,697** | **36,839** | **24,700** | **21,431** | **6,438** | **10,890** |
|  | ⏱️ Avg Latency | 0.63ms | 2.71ms | 4.07ms | 5.12ms | 15.38ms | 9.28ms |
|  | 📉 Max Latency | 26.68ms | 8.53ms | 15.00ms | 157.83ms | 28.53ms | 63.63ms |
|  | 📦 Transfer | 28.00 MB/s | 4.29 MB/s | 2.87 MB/s | 3.00 MB/s | 0.98 MB/s | 1.44 MB/s |
|  | 🔥 CPU Usage | 439% | 198% | 158% | 97% | 741% | 401% |
|  | 🧠 RAM Usage | 54.0 MB | 53.7 MB | 54.4 MB | 30.6 MB | 161.7 MB | 253.3 MB |
| | | --- | --- | --- | --- | --- | --- |

## 📊 Performance Comparison
![RPS Comparison](rps_comparison.png)

## ⚙️ How to Reproduce
```bash
uv run --extra benchmarks benchmarks/run_comparison_auto.py
```