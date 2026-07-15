# -*- coding: utf-8 -*-
"""Small Linux/Jetson metrics collector."""
from __future__ import print_function

import os


def _read_text(path):
    try:
        with open(path, "r") as handle:
            return handle.read().strip()
    except IOError:
        return ""


def memory_info():
    values = {}
    try:
        with open("/proc/meminfo", "r") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                parts = value.strip().split()
                values[key] = int(parts[0]) * 1024
    except Exception:
        return {}
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": max(0, total - available),
        "used_percent": round((total - available) * 100.0 / total, 1) if total else 0,
    }


def temperature_info():
    candidates = [
        "/sys/devices/virtual/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone0/temp",
    ]
    for path in candidates:
        raw = _read_text(path)
        if raw:
            try:
                value = float(raw)
                if value > 1000:
                    value /= 1000.0
                return round(value, 1)
            except ValueError:
                pass
    return None


def gpu_info():
    """Read Jetson GPU utilization and temperature."""
    result = {}
    gpu_load = _read_text("/sys/devices/57000000.gpu/load")
    if gpu_load:
        try:
            result["gpu_usage_percent"] = round(int(gpu_load) / 10.0, 1)
        except ValueError:
            pass
    gpu_freq = _read_text("/sys/devices/57000000.gpu/devfreq/57000000.gpu/cur_freq")
    if gpu_freq:
        try:
            result["gpu_freq_mhz"] = int(gpu_freq) // 1000000
        except ValueError:
            pass
    # RAM from /proc/meminfo (shared with GPU on Jetson)
    mem = memory_info()
    if mem:
        result["ram_used_mb"] = mem.get("used_bytes", 0) // (1024 * 1024)
        result["ram_total_mb"] = mem.get("total_bytes", 0) // (1024 * 1024)
    # SWAP from /proc/swaps + /proc/meminfo
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("SwapTotal:"):
                    result["swap_total_mb"] = int(line.split()[1]) // 1024
                elif line.startswith("SwapFree:"):
                    swap_free = int(line.split()[1]) // 1024
        if "swap_total_mb" in result:
            result["swap_used_mb"] = result["swap_total_mb"] - swap_free
    except Exception:
        pass
    return result


def collect_metrics():
    try:
        load = os.getloadavg()
    except OSError:
        load = (0.0, 0.0, 0.0)
    disk = os.statvfs("/")
    total_disk = disk.f_frsize * disk.f_blocks
    free_disk = disk.f_frsize * disk.f_bavail
    return {
        "load_1m": round(load[0], 2),
        "load_5m": round(load[1], 2),
        "memory": memory_info(),
        "gpu": gpu_info(),
        "temperature_c": temperature_info(),
        "disk": {
            "total_bytes": total_disk,
            "free_bytes": free_disk,
            "used_percent": round((total_disk - free_disk) * 100.0 / total_disk, 1) if total_disk else 0,
        },
    }
