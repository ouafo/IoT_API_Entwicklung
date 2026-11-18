"""Service for on-demand 7-day-ahead room climate forecasting."""

from typing import Any, Optional
from starlette.concurrency import run_in_threadpool

from app.services.forecast_engine import (
    HISTORY_WINDOW_SIZE,
    ROOM_CLIMATE_SENSORS,
    generate_room_climate_forecast,
    list_known_rooms,
)


async def get_forecast_rooms() -> list[dict[str, Any]]:
    rooms = await run_in_threadpool(list_known_rooms)
    return [
        {
            **room,
            "available_sensors": list(ROOM_CLIMATE_SENSORS.keys()),
            "status": "available",
        }
        for room in rooms
    ]


async def get_room_forecasts(
    room_id: str,
    limit: int = HISTORY_WINDOW_SIZE,
    sensor_type: str = "temperature",
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any]:
    data = await run_in_threadpool(
        generate_room_climate_forecast,
        room_id,
        sensor_type,
        limit,
        capacity,
        area,
        window_count,
    )
    return {
        **data,
        "horizon_days": 7,
        "model_type": "DampedTrend+RoomPhysics(n=15)",
        "history_count": len(data["history"]),
        "forecast_count": len(data["forecast"]),
    }


async def get_room_forecast_summary(
    room_id: str,
    sensor_type: str = "temperature",
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any] | None:
    data = await get_room_forecasts(
        room_id=room_id,
        limit=HISTORY_WINDOW_SIZE,
        sensor_type=sensor_type,
        capacity=capacity,
        area=area,
        window_count=window_count,
    )
    if not data["forecast"]:
        return None

    hist_vals = [p["value"] for p in data["history"]]
    fc_vals = [p["value"] for p in data["forecast"]]

    return {
        "building": data["building"],
        "room_id": data["room_id"],
        "full_room_id": data["full_room_id"],
        "sensor_type": data["sensor_type"],
        "sensor_label": data["sensor_label"],
        "unit": data["unit"],
        "forecast_origin": data["forecast_origin"],
        "target_weekday": data["target_weekday"],
        "history_average": round(sum(hist_vals) / len(hist_vals), 3),
        "forecast_average": round(sum(fc_vals) / len(fc_vals), 3),
        "forecast_minimum": round(min(fc_vals), 3),
        "forecast_maximum": round(max(fc_vals), 3),
        "status": "available",
    }