"""weather tool.

Uses Open-Meteo: free, no API key, accurate. Two-step lookup:
    1. Geocode the location to lat/lon (open-meteo geocoding API).
    2. Hit the forecast endpoint for current conditions + today.

Autorun: read-only, no PII, no auth.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.tools.base import ExecutionContext, Tool, ToolResult

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 6.0

# Mapping for WMO weather codes -> short descriptions. Trimmed.
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Heavy rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherTool(Tool):
    name = "weather"
    description = (
        "Look up current weather and today's forecast for a location. "
        "Pass a city, address, or 'city, country' string. Temperatures "
        "are returned in both Celsius and Fahrenheit."
    )
    parameters = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Place name, e.g. 'Boston', 'Paris, France'.",
            }
        },
        "required": ["location"],
        "additionalProperties": False,
    }
    default_policy = "autorun"

    async def run(
        self, args: dict[str, Any], ctx: ExecutionContext
    ) -> ToolResult:
        location = (args.get("location") or "").strip()
        if not location:
            return ToolResult(content="No location provided.", error=True)

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            geo_resp = await client.get(
                GEOCODE_URL, params={"name": location, "count": 1}
            )
            geo_resp.raise_for_status()
            geo = geo_resp.json()
            results = geo.get("results") or []
            if not results:
                return ToolResult(
                    content=f"Couldn't find a place called {location!r}.",
                    error=True,
                )
            place = results[0]
            lat = place["latitude"]
            lon = place["longitude"]
            display = ", ".join(
                p for p in [place.get("name"), place.get("country")] if p
            )

            fc_resp = await client.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,apparent_temperature,relative_humidity_2m,"
                        "weather_code,wind_speed_10m"
                    ),
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
            )
            fc_resp.raise_for_status()
            fc = fc_resp.json()

        cur = fc.get("current", {})
        daily = fc.get("daily", {})
        code = cur.get("weather_code")
        desc = WMO_CODES.get(int(code), "Unknown") if code is not None else "Unknown"
        temp_c = cur.get("temperature_2m")
        feels_c = cur.get("apparent_temperature")
        rh = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        hi_c = (daily.get("temperature_2m_max") or [None])[0]
        lo_c = (daily.get("temperature_2m_min") or [None])[0]

        def c_to_f(c: float | None) -> float | None:
            return None if c is None else round(c * 9 / 5 + 32, 1)

        summary_parts: list[str] = [f"{desc} in {display}"]
        if temp_c is not None:
            summary_parts.append(f"{temp_c:g}°C ({c_to_f(temp_c):g}°F)")
        if feels_c is not None and feels_c != temp_c:
            summary_parts.append(f"feels {feels_c:g}°C")
        if hi_c is not None and lo_c is not None:
            summary_parts.append(
                f"today {lo_c:g}–{hi_c:g}°C "
                f"({c_to_f(lo_c):g}–{c_to_f(hi_c):g}°F)"
            )
        if rh is not None:
            summary_parts.append(f"humidity {rh}%")
        if wind is not None:
            summary_parts.append(f"wind {wind:g} km/h")
        summary = ". ".join(summary_parts) + "."

        return ToolResult(
            content=summary,
            data={
                "location": display,
                "lat": lat,
                "lon": lon,
                "conditions": desc,
                "temperature_c": temp_c,
                "temperature_f": c_to_f(temp_c),
                "feels_like_c": feels_c,
                "feels_like_f": c_to_f(feels_c),
                "humidity_pct": rh,
                "wind_kmh": wind,
                "today_high_c": hi_c,
                "today_low_c": lo_c,
                "today_high_f": c_to_f(hi_c),
                "today_low_f": c_to_f(lo_c),
            },
        )
