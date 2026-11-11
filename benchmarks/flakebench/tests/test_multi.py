"""Planted causes: two at once (network AND timezone)."""

import time

from bench.helpers import api_get


def test_multi_network_and_timezone():
    forecast = api_get("/health")
    stamp = time.strftime("%H:%M", time.localtime(1795291200))
    assert forecast["status"] == "ok" and stamp == "20:00"
