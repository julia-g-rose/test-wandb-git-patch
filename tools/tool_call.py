from __future__ import annotations

import ast
from typing import Any


def get_weather(*, location: str, date: str | None = None, units: str = "C") -> dict[str, Any]:
    """
    A safe, deterministic tool suitable for an OpenAI function-calling travel-agent demo.
    - No filesystem access
    - No environment access
    - No network access

    Returns a small, hard-coded forecast-like response so you can test tool calling without
    hitting any external APIs.
    """
    # Minimal “forecast” table (fake, deterministic).
    normalized = location.strip().lower()
    forecast = {
        "san francisco": {"summary": "cool and breezy", "temp_c": 16, "precip_chance": 0.1},
        "new york": {"summary": "variable clouds", "temp_c": 22, "precip_chance": 0.3},
        "london": {"summary": "light rain", "temp_c": 14, "precip_chance": 0.6},
        "tokyo": {"summary": "humid and warm", "temp_c": 27, "precip_chance": 0.4},
    }.get(normalized)

    if not forecast:
        forecast = {"summary": "unknown (demo stub)", "temp_c": 20, "precip_chance": 0.2}

    units_norm = units.strip().upper()
    temp = forecast["temp_c"]
    temp_out: float
    temp_unit: str
    if units_norm == "F":
        temp_out = temp * 9 / 5 + 32
        temp_unit = "F"
    else:
        temp_out = float(temp)
        temp_unit = "C"

    return {
        "tool": "get_weather",
        "location": location,
        "date": date,
        "units": temp_unit,
        "summary": forecast["summary"],
        "temperature": round(temp_out, 1),
        "precipitation_chance": forecast["precip_chance"],
    }


