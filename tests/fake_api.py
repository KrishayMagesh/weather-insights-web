"""A stand-in for the Open-Meteo API so tests never touch the network."""
import types

import numpy as np
import pandas as pd

CITIES = {
    "san jose": ("San Jose", "California", "United States", 37.34, -121.89, 72, 12, 0.15),
    "seattle": ("Seattle", "Washington", "United States", 47.61, -122.33, 60, 15, 0.40),
}


def response(body, status=200):
    return types.SimpleNamespace(status_code=status, json=lambda: body)


def fake_get(url, params=None, timeout=None):
    if "geocoding" in url:
        city = CITIES.get(params["name"].lower())
        if not city:
            return response({"generationtime_ms": 0.1})
        name, admin1, country, lat, lon, *_ = city
        return response({"results": [{"name": name, "admin1": admin1, "country": country,
                                      "latitude": lat, "longitude": lon}]})
    city = next(c for c in CITIES.values() if abs(c[3] - params["latitude"]) < 0.01)
    base, amp, rain_chance = city[5], city[6], city[7]
    days = pd.date_range(params["start_date"], params["end_date"])
    n = len(days)
    t = np.arange(n)
    rng = np.random.default_rng(int(abs(params["latitude"]) * 100))
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.6 * noise[i - 1] + rng.normal(0, 3)
    high = base + amp * np.sin(2 * np.pi * (t - 100) / 365.25) + noise
    rain = np.where(rng.random(n) < rain_chance, 0.3, 0.0)
    return response({"daily": {
        "time": [d.strftime("%Y-%m-%d") for d in days],
        "temperature_2m_max": list(high), "temperature_2m_min": list(high - 18),
        "precipitation_sum": list(rain), "wind_speed_10m_max": list(9 + rng.random(n) * 4)}})


def failing_get(url, params=None, timeout=None):
    import requests
    raise requests.ConnectionError("network down")
