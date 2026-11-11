from shop.weather import delivery_forecast, weather_alerts


def test_delivery_forecast():
    forecast = delivery_forecast("Mysuru")
    assert forecast["delay_risk"] in {"low", "high"}


def test_weather_alerts():
    assert isinstance(weather_alerts("Mysuru"), list)
