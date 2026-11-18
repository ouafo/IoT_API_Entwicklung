"""Lightweight, read-only PostgreSQL + in-memory cached forecasting engine.

Uses the latest N=15 valid measurements per room or building to project
a 7-day-ahead (same weekday & time next week) evolution without writing
any CSV files or database tables.
"""

from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

from app.config import settings
from app.database import connection, queries
from app.logger import logger


HISTORY_WINDOW_SIZE = 15
FORECAST_OFFSET_DAYS = 7
CACHE_TTL_SECONDS = 300  # 5 minutes in-memory cache


DEFAULT_ROOM_ATTRIBUTES = {
    "capacity": 40,
    "area": 100.0,
    "window_count": 4,
}


ROOM_CLIMATE_SENSORS = {
    "temperature": {
        "column": "temperature",
        "unit_column": "temperature_unit",
        "default_unit": "°C",
        "label": "Temperatur",
        "min": -10.0,
        "max": 50.0,
    },
    "humidity": {
        "column": "humidity",
        "unit_column": "humidity_unit",
        "default_unit": "%",
        "label": "Luftfeuchtigkeit",
        "min": 0.0,
        "max": 100.0,
    },
    "co2": {
        "column": "co2",
        "unit_column": "co2_unit",
        "default_unit": "ppm",
        "label": "CO₂",
        "min": 250.0,
        "max": 5000.0,
    },
    "light": {
        "column": "light_mean",
        "unit_column": "light_unit",
        "default_unit": "Lux",
        "label": "Licht",
        "min": 0.0,
        "max": 100000.0,
    },
}


WEATHER_SENSORS = {
    "temperature": {
        "column": "temperature",
        "unit_column": "temperature_unit",
        "default_unit": "celsius",
        "min": -40.0,
        "max": 60.0,
    },
    "humidity": {
        "column": "humidity",
        "unit_column": "humidity_unit",
        "default_unit": "percent",
        "min": 0.0,
        "max": 100.0,
    },
    "barometric_pressure": {
        "column": "pressure",
        "unit_column": "pressure_unit",
        "default_unit": "hPa",
        "min": 850.0,
        "max": 1100.0,
    },
    "wind_speed": {
        "column": "wind_speed",
        "unit_column": "wind_speed_unit",
        "default_unit": "m/s",
        "min": 0.0,
        "max": 75.0,
    },
    "rainfall": {
        "column": "rainfall_total",
        "unit_column": "rainfall_total_unit",
        "default_unit": "mm",
        "min": 0.0,
        "max": 100.0,
    },
    "wind_direction": {
        "column": "wind_direction",
        "unit_column": "wind_direction_unit",
        "default_unit": "degree",
        "min": 0.0,
        "max": 360.0,
    },
}


class _TTLCache:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if now >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl, value)


_cache = _TTLCache()


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_unit(raw_unit: Optional[str], default_unit: str) -> str:
    if not raw_unit:
        return default_unit
    cleaned = str(raw_unit).strip()
    mapping = {
        "celsius": "°C",
        "percent": "%",
        "ppm": "ppm",
        "Lux": "Lux",
    }
    return mapping.get(cleaned, cleaned)


def parse_room_identifier(room_id: str) -> tuple[Optional[str], str]:
    """Accept both 'A203' and 'A-A203' / 'C-C2.005' formats."""
    cleaned = room_id.strip()
    if "-" in cleaned:
        building_part, room_part = cleaned.split("-", 1)
        if building_part and room_part:
            return building_part.strip(), room_part.strip()
    return None, cleaned


def list_known_rooms() -> list[dict[str, Any]]:
    """Return all distinct rooms including their physical attributes (cached)."""
    cached = _cache.get("known_rooms")
    if cached is not None:
        return cached

    try:
        raw_rooms = queries.get_rooms(limit=settings.MAX_PAGE_SIZE, offset=0)
    except Exception as exc:
        logger.warning(f"Fallback room discovery due to queries.get_rooms error: {exc}")
        raw_rooms = []

    rooms: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for r in raw_rooms:
        b = str(r.get("BuildingID") or "").strip()
        loc = str(r.get("RoomID") or "").strip()
        if not b or not loc or (b, loc) in seen:
            continue
        seen.add((b, loc))

        capacity = r.get("capacity") if r.get("capacity") is not None else DEFAULT_ROOM_ATTRIBUTES["capacity"]
        area = r.get("area") if r.get("area") is not None else DEFAULT_ROOM_ATTRIBUTES["area"]
        window_count = (
            r.get("window_count")
            if r.get("window_count") is not None
            else DEFAULT_ROOM_ATTRIBUTES["window_count"]
        )

        rooms.append({
            "building": b,
            "room_location": loc,
            "room_id": loc,
            "full_room_id": f"{b}-{loc}",
            "capacity": int(capacity),
            "area": float(area),
            "window_count": int(window_count),
        })

    rooms.sort(key=lambda item: (item["building"], item["room_location"]))
    _cache.set("known_rooms", rooms)
    return rooms


def resolve_room(
    room_id: str,
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any]:
    """Resolve room metadata and physical attributes from either 'A203' or 'A-A203'."""
    building_hint, room_location = parse_room_identifier(room_id)
    rooms = list_known_rooms()

    matches = [
        r for r in rooms
        if r["room_location"].casefold() == room_location.casefold()
        and (
            building_hint is None
            or r["building"].casefold() == building_hint.casefold()
        )
    ]

    if not matches:
        raise ValueError(f"Room '{room_id}' was not found in the database.")

    if len(matches) > 1:
        buildings = ", ".join(sorted({m["building"] for m in matches}))
        raise ValueError(
            f"Room '{room_id}' exists in multiple buildings ({buildings}). "
            "Please specify '<Building>-<Room>', e.g. 'A-A203'."
        )

    room = dict(matches[0])
    if capacity is not None:
        room["capacity"] = capacity
    if area is not None:
        room["area"] = area
    if window_count is not None:
        room["window_count"] = window_count

    return room


def _room_physics_factor(
    domain: str,
    sensor_type: str,
    room: dict[str, Any],
) -> float:
    """Compute a bounded physical scaling multiplier from capacity, area & window_count."""
    capacity = max(1.0, float(room.get("capacity") or DEFAULT_ROOM_ATTRIBUTES["capacity"]))
    area = max(5.0, float(room.get("area") or DEFAULT_ROOM_ATTRIBUTES["area"]))
    windows = max(
        0.0,
        float(
            room.get("window_count")
            if room.get("window_count") is not None
            else DEFAULT_ROOM_ATTRIBUTES["window_count"]
        ),
    )

    occupancy_density_ratio = (capacity / area) / 0.40
    ventilation_ratio = (windows / area) / 0.04

    if domain == "energy":
        factor = 0.60 + 0.25 * (area / 100.0) + 0.15 * (capacity / 40.0)
        return float(np.clip(factor, 0.5, 2.0))

    if domain == "room_climate":
        if sensor_type == "co2":
            factor = (0.75 + 0.25 * occupancy_density_ratio) / (0.85 + 0.15 * ventilation_ratio)
            return float(np.clip(factor, 0.5, 1.8))
        if sensor_type in ("temperature", "humidity"):
            factor = (0.85 + 0.15 * occupancy_density_ratio) / (0.90 + 0.10 * ventilation_ratio)
            return float(np.clip(factor, 0.6, 1.5))

    return 1.0


def _project_series_next_week(
    timestamps: list[datetime],
    values: list[float],
    min_val: float,
    max_val: float,
    physics_factor: float = 1.0,
    is_circular_angle: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build paired 15-point historical series and 15-point +7-day forecast series."""
    n = len(values)
    history_points = [
        {
            "timestamp": _ensure_utc(ts),
            "value": round(float(val), 4),
        }
        for ts, val in zip(timestamps, values)
    ]

    if is_circular_angle:
        radians = np.deg2rad(values)
        sin_vals = np.sin(radians)
        cos_vals = np.cos(radians)

        sin_mean = float(np.mean(sin_vals))
        cos_mean = float(np.mean(cos_vals))

        forecast_points = []
        for idx, (ts, s_val, c_val) in enumerate(zip(timestamps, sin_vals, cos_vals)):
            blend = 0.70 + 0.20 * (idx / max(1, n - 1))
            pred_sin = blend * float(s_val) + (1.0 - blend) * sin_mean
            pred_cos = blend * float(c_val) + (1.0 - blend) * cos_mean
            angle = (math.degrees(math.atan2(pred_sin, pred_cos)) + 360.0) % 360.0
            forecast_points.append({
                "timestamp": _ensure_utc(ts) + timedelta(days=FORECAST_OFFSET_DAYS),
                "value": round(float(angle), 2),
            })
        return history_points, forecast_points

    arr = np.asarray(values, dtype=float)
    weights = np.linspace(0.5, 1.5, n)
    weighted_mean = float(np.average(arr, weights=weights))

    if n >= 2:
        x = np.arange(n, dtype=float)
        x_centered = x - x.mean()
        denom = float(np.sum(x_centered ** 2))
        slope = float(np.sum(x_centered * (arr - arr.mean())) / denom) if denom > 0 else 0.0
    else:
        slope = 0.0

    damped_slope = slope * 0.35 * physics_factor

    forecast_points = []
    for idx, (ts, val) in enumerate(zip(timestamps, arr)):
        deviation_from_mean = (float(val) - weighted_mean) * physics_factor
        projected = weighted_mean + deviation_from_mean + damped_slope * (idx - (n - 1) / 2.0)
        projected = float(np.clip(projected, min_val, max_val))
        forecast_points.append({
            "timestamp": _ensure_utc(ts) + timedelta(days=FORECAST_OFFSET_DAYS),
            "value": round(projected, 4),
        })

    return history_points, forecast_points


def generate_room_climate_forecast(
    room_id: str,
    sensor_type: str = "temperature",
    limit: int = HISTORY_WINDOW_SIZE,
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any]:
    sensor_key = sensor_type.strip().lower()
    if sensor_key not in ROOM_CLIMATE_SENSORS:
        raise ValueError(f"Unsupported room climate sensor: {sensor_type}")

    room = resolve_room(room_id, capacity=capacity, area=area, window_count=window_count)
    n_records = max(5, min(limit, 50))
    cache_key = (
        f"climate:{room['building']}:{room['room_location']}:{sensor_key}:"
        f"{n_records}:{room['capacity']}:{room['area']}:{room['window_count']}"
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    cfg = ROOM_CLIMATE_SENSORS[sensor_key]
    col = cfg["column"]
    unit_col = cfg["unit_column"]
    schema = settings.DB_SCHEMA

    query = f"""
        SELECT
            start,
            {col},
            {unit_col}
        FROM "{schema}"."room_climate"
        WHERE building = %s
          AND room_location = %s
          AND start IS NOT NULL
          AND {col} IS NOT NULL
          AND {col} BETWEEN %s AND %s
        ORDER BY start DESC
        LIMIT %s;
    """

    conn = connection.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            query,
            (
                room["building"],
                room["room_location"],
                cfg["min"],
                cfg["max"],
                n_records,
            ),
        )
        rows = cur.fetchall()
    finally:
        connection.put_conn(conn)

    if not rows:
        return {
            "building": room["building"],
            "room_id": room["room_id"],
            "full_room_id": room["full_room_id"],
            "sensor_type": sensor_key,
            "sensor_label": cfg["label"],
            "unit": cfg["default_unit"],
            "room_attributes": {
                "capacity": room["capacity"],
                "area": room["area"],
                "window_count": room["window_count"],
            },
            "forecast_origin": None,
            "target_weekday": None,
            "history": [],
            "forecast": [],
        }

    rows = list(reversed(rows))
    timestamps = [_ensure_utc(r[0]) for r in rows]
    values = [float(r[1]) for r in rows]
    unit = _normalize_unit(rows[-1][2], cfg["default_unit"])

    physics_factor = _room_physics_factor("room_climate", sensor_key, room)
    history, forecast = _project_series_next_week(
        timestamps=timestamps,
        values=values,
        min_val=cfg["min"],
        max_val=cfg["max"],
        physics_factor=physics_factor,
    )

    origin = timestamps[-1]
    target_first = forecast[0]["timestamp"]

    result = {
        "building": room["building"],
        "room_id": room["room_id"],
        "full_room_id": room["full_room_id"],
        "sensor_type": sensor_key,
        "sensor_label": cfg["label"],
        "unit": unit,
        "room_attributes": {
            "capacity": room["capacity"],
            "area": room["area"],
            "window_count": room["window_count"],
        },
        "forecast_origin": origin,
        "target_weekday": target_first.strftime("%A"),
        "history": history,
        "forecast": forecast,
    }
    _cache.set(cache_key, result)
    return result


def generate_energy_forecast(
    room_id: str,
    limit: int = HISTORY_WINDOW_SIZE,
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any]:
    room = resolve_room(room_id, capacity=capacity, area=area, window_count=window_count)
    n_records = max(5, min(limit, 50))
    cache_key = (
        f"energy:{room['building']}:{room['room_location']}:"
        f"{n_records}:{room['capacity']}:{room['area']}:{room['window_count']}"
    )
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    schema = settings.DB_SCHEMA
    query = f"""
        SELECT
            start,
            MAX("Wirkenergie_Import_L123_T1") AS energy_kwh
        FROM "{schema}"."room_energy"
        WHERE building = %s
          AND room_location = %s
          AND start IS NOT NULL
          AND "Wirkenergie_Import_L123_T1" IS NOT NULL
        GROUP BY start
        ORDER BY start DESC
        LIMIT %s;
    """

    conn = connection.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, (room["building"], room["room_location"], n_records + 1))
        rows = cur.fetchall()
    finally:
        connection.put_conn(conn)

    if len(rows) < 2:
        return {
            "building": room["building"],
            "room_id": room["room_id"],
            "full_room_id": room["full_room_id"],
            "unit": "kWh",
            "room_attributes": {
                "capacity": room["capacity"],
                "area": room["area"],
                "window_count": room["window_count"],
            },
            "forecast_origin": _ensure_utc(rows[0][0]) if rows else None,
            "target_weekday": None,
            "history": [],
            "forecast": [],
        }

    rows = list(reversed(rows))
    timestamps: list[datetime] = []
    consumptions: list[float] = []

    for i in range(1, len(rows)):
        _, e_prev = rows[i - 1]
        ts_curr, e_curr = rows[i]
        delta_kwh = max(0.0, float(e_curr) - float(e_prev))
        timestamps.append(_ensure_utc(ts_curr))
        consumptions.append(delta_kwh)

    physics_factor = _room_physics_factor("energy", "consumption_kwh", room)
    history, forecast = _project_series_next_week(
        timestamps=timestamps,
        values=consumptions,
        min_val=0.0,
        max_val=10000.0,
        physics_factor=physics_factor,
    )

    origin = timestamps[-1]
    target_first = forecast[0]["timestamp"]

    result = {
        "building": room["building"],
        "room_id": room["room_id"],
        "full_room_id": room["full_room_id"],
        "unit": "kWh",
        "room_attributes": {
            "capacity": room["capacity"],
            "area": room["area"],
            "window_count": room["window_count"],
        },
        "forecast_origin": origin,
        "target_weekday": target_first.strftime("%A"),
        "history": history,
        "forecast": forecast,
    }
    _cache.set(cache_key, result)
    return result


def list_weather_buildings() -> list[str]:
    cached = _cache.get("weather_buildings")
    if cached is not None:
        return cached

    schema = settings.DB_SCHEMA
    query = f"""
        SELECT DISTINCT building
        FROM "{schema}"."weather_station"
        WHERE building IS NOT NULL
        ORDER BY building;
    """
    conn = connection.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query)
        buildings = [str(r[0]).strip() for r in cur.fetchall()]
        _cache.set("weather_buildings", buildings)
        return buildings
    finally:
        connection.put_conn(conn)


def generate_weather_forecast(
    building_id: str,
    sensor_type: str = "temperature",
    limit: int = HISTORY_WINDOW_SIZE,
) -> dict[str, Any]:
    sensor_key = sensor_type.strip().lower()
    if sensor_key not in WEATHER_SENSORS:
        raise ValueError(f"Unsupported weather sensor: {sensor_type}")

    b_id = building_id.strip()
    n_records = max(5, min(limit, 50))
    cache_key = f"weather:{b_id}:{sensor_key}:{n_records}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    cfg = WEATHER_SENSORS[sensor_key]
    col = cfg["column"]
    unit_col = cfg["unit_column"]
    schema = settings.DB_SCHEMA

    query = f"""
        SELECT
            stop,
            {col},
            {unit_col}
        FROM "{schema}"."weather_station"
        WHERE building = %s
          AND stop IS NOT NULL
          AND {col} IS NOT NULL
          AND {col} BETWEEN %s AND %s
        ORDER BY stop DESC
        LIMIT %s;
    """

    conn = connection.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, (b_id, cfg["min"], cfg["max"], n_records))
        rows = cur.fetchall()
    finally:
        connection.put_conn(conn)

    if not rows:
        return {
            "building": b_id,
            "sensor_type": sensor_key,
            "unit": cfg["default_unit"],
            "forecast_origin": None,
            "target_weekday": None,
            "history": [],
            "forecast": [],
        }

    rows = list(reversed(rows))
    timestamps = [_ensure_utc(r[0]) for r in rows]
    values = [float(r[1]) for r in rows]
    unit = _normalize_unit(rows[-1][2], cfg["default_unit"])

    history, forecast = _project_series_next_week(
        timestamps=timestamps,
        values=values,
        min_val=cfg["min"],
        max_val=cfg["max"],
        physics_factor=1.0,
        is_circular_angle=(sensor_key == "wind_direction"),
    )

    origin = timestamps[-1]
    target_first = forecast[0]["timestamp"]

    result = {
        "building": b_id,
        "sensor_type": sensor_key,
        "unit": unit,
        "forecast_origin": origin,
        "target_weekday": target_first.strftime("%A"),
        "history": history,
        "forecast": forecast,
    }
    _cache.set(cache_key, result)
    return result