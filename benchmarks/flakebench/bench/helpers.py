"""Shared building blocks for the planted causes."""

import json
import multiprocessing
import os
import time
import urllib.parse
import urllib.request

API = os.environ.get("WEATHER_API_URL", "http://weather-api:8000")


def timed_cpu_work(cpu_budget: float) -> float:
    """Do `cpu_budget` seconds of CPU work; return the wall-clock time it took.

    Measuring CPU time (process_time) makes the amount of work independent of
    how fast the machine is; only CPU *availability* changes the wall time.
    """
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    x = 0
    while time.process_time() - start_cpu < cpu_budget:
        x = (x * 31 + 7) % 1_000_003
    return time.perf_counter() - start_wall


def _allocate(size_mb: int) -> None:
    data = b"x" * (size_mb * 1024 * 1024)
    assert len(data) > 0


def allocate_in_worker(size_mb: int) -> int:
    """Allocate memory in a child process; return its exit code (-9 if OOM-killed)."""
    worker = multiprocessing.get_context("spawn").Process(target=_allocate, args=(size_mb,))
    worker.start()
    worker.join(120)
    return worker.exitcode


def api_get(path: str, timeout: float = 1.0, **params) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())
