"""Delivery planning that calls an external weather service.

Planted problem (external dependency): the tests call the real service instead
of a fake. They fail without network access, and occasionally even with it,
because the service is sometimes slower than the client's timeout.
"""

import json
import os
import urllib.parse
import urllib.request

WEATHER_API_URL = os.environ.get("WEATHER_API_URL", "http://weather-api:8000")
TIMEOUT_SECONDS = 1.0


def _get(path: str, **params) -> dict:
    url = f"{WEATHER_API_URL}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def delivery_forecast(city: str) -> dict:
    data = _get("/forecast", city=city)
    risk = "high" if data["rain_mm"] > 10 else "low"
    return {"city": city, "rain_mm": data["rain_mm"], "delay_risk": risk}


def weather_alerts(city: str) -> list:
    return _get("/alerts", city=city)["alerts"]
