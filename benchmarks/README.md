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
| **`/`** | 🚀 RPS | 🥇 **211,984** | **28,932** | **27,499** | **15,933** | **5,087** | **10,660** |
|  | ⏱️ Avg Latency | 0.80ms | 3.45ms | 3.90ms | 9.33ms | 19.61ms | 10.11ms |
|  | 📉 Max Latency | 34.52ms | 14.72ms | 39.41ms | 363.47ms | 76.77ms | 108.23ms |
|  | 📦 Transfer | 24.46 MB/s | 3.56 MB/s | 3.41 MB/s | 2.23 MB/s | 0.81 MB/s | 1.49 MB/s |
|  | 🔥 CPU Usage | 396% | 201% | 206% | 96% | 454% | 502% |
|  | 🧠 RAM Usage | 55.9 MB | 56.4 MB | 56.1 MB | 30.5 MB | 160.6 MB | 250.4 MB |
| | | --- | --- | --- | --- | --- | --- |
| **`/json`** | 🚀 RPS | 🥇 **208,543** | **29,638** | **9,688** | **18,888** | **5,319** | **10,964** |
|  | ⏱️ Avg Latency | 0.71ms | 3.54ms | 11.05ms | 6.54ms | 18.62ms | 9.11ms |
|  | 📉 Max Latency | 36.56ms | 34.98ms | 56.33ms | 236.13ms | 31.39ms | 46.63ms |
|  | 📦 Transfer | 25.06 MB/s | 3.53 MB/s | 1.16 MB/s | 2.02 MB/s | 0.83 MB/s | 1.48 MB/s |
|  | 🔥 CPU Usage | 401% | 201% | 140% | 96% | 375% | 400% |
|  | 🧠 RAM Usage | 53.7 MB | 54.3 MB | 54.0 MB | 30.5 MB | 160.7 MB | 252.2 MB |
| | | --- | --- | --- | --- | --- | --- |
| **`/user/10`** | 🚀 RPS | 🥇 **211,768** | **25,056** | **13,381** | **16,720** | **5,177** | **9,354** |
|  | ⏱️ Avg Latency | 1.04ms | 4.42ms | 7.49ms | 6.17ms | 18.54ms | 10.91ms |
|  | 📉 Max Latency | 128.99ms | 41.94ms | 23.89ms | 141.61ms | 38.24ms | 90.41ms |
|  | 📦 Transfer | 24.84 MB/s | 2.92 MB/s | 1.57 MB/s | 2.34 MB/s | 0.79 MB/s | 1.24 MB/s |
|  | 🔥 CPU Usage | 403% | 197% | 135% | 96% | 376% | 396% |
|  | 🧠 RAM Usage | 53.8 MB | 54.3 MB | 54.3 MB | 30.5 MB | 160.7 MB | 252.9 MB |
| | | --- | --- | --- | --- | --- | --- |

## 📊 Performance Comparison
![RPS Comparison](rps_comparison.png)

## ⚙️ How to Reproduce
```bash
uv run --extra benchmarks benchmarks/run_comparison_auto.py
```