"""Planted cause: hidden external dependency (the fake weather service)."""

from bench.helpers import api_get


def test_network_forecast():
    assert "rain_mm" in api_get("/forecast", city="Mysuru")


def test_network_alerts():
    assert isinstance(api_get("/alerts", city="Mysuru")["alerts"], list)


def test_network_health():
    # /health is never slow, so this only fails without network: a hidden sensitivity.
    assert api_get("/health")["status"] == "ok"
