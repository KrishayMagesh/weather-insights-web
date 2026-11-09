"""Small client for the free Open-Meteo APIs (no key needed).

- Geocoding: https://open-meteo.com/en/docs/geocoding-api
- Historical weather: https://open-meteo.com/en/docs/historical-weather-api
"""
from datetime import date, timedelta

import pandas as pd
import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "wind_speed_10m_max"]
COLUMNS = {"time": "date", "temperature_2m_max": "temp_high_f",
           "temperature_2m_min": "temp_low_f", "precipitation_sum": "precip_in",
           "wind_speed_10m_max": "wind_max_mph"}


class WeatherAPIError(RuntimeError):
    """The city could not be found or the weather service failed."""


def _get_json(url, params):
    try:
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherAPIError("The weather service could not be reached. "
                              "Please try again in a minute.") from exc
    if response.status_code != 200:
        reason = data.get("reason", response.status_code) if isinstance(data, dict) else ""
        raise WeatherAPIError(f"The weather service returned an error: {reason}")
    return data


def geocode(name):
    """Return {'name', 'label', 'latitude', 'longitude'} for the best match of a city name."""
    name = (name or "").strip()
    if not name:
        raise WeatherAPIError("Please enter a city name.")
    if len(name) > 80:
        raise WeatherAPIError("City names must be 80 characters or fewer.")
    data = _get_json(GEOCODE_URL, {"name": name, "count": 1, "language": "en", "format": "json"})
    results = data.get("results") or []
    if not results:
        raise WeatherAPIError(f"Could not find a city called '{name}'.")
    r = results[0]
    label = ", ".join(p for p in [r.get("name"), r.get("admin1"), r.get("country")] if p)
    return {"name": r.get("name", name), "label": label,
            "latitude": float(r["latitude"]), "longitude": float(r["longitude"])}


def date_range(years):
    """The archive runs about a week behind, so end a week before today."""
    end = date.today() - timedelta(days=7)
    start = end - timedelta(days=round(365.25 * years))
    return start, end


def fetch_daily(latitude, longitude, start, end):
    """Daily weather between two dates as a DataFrame (F, inches, mph)."""
    data = _get_json(ARCHIVE_URL, {
        "latitude": latitude, "longitude": longitude,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": ",".join(DAILY), "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph", "precipitation_unit": "inch", "timezone": "auto",
    })
    if "daily" not in data:
        raise WeatherAPIError("The weather service returned no daily data.")
    df = pd.DataFrame(data["daily"]).rename(columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["temp_high_f", "temp_low_f"]).reset_index(drop=True)
    df["precip_in"] = df["precip_in"].fillna(0)
    df["wind_max_mph"] = df["wind_max_mph"].fillna(df["wind_max_mph"].mean())
    if len(df) < 60:
        raise WeatherAPIError("Not enough weather data was returned for that location.")
    return df
