"""Service for on-demand 7-day-ahead room energy forecasting."""

from typing import Any, Optional
from starlette.concurrency import run_in_threadpool

from app.services.forecast_engine import (
    HISTORY_WINDOW_SIZE,
    generate_energy_forecast,
    list_known_rooms,
)


async def get_energy_rooms() -> list[dict[str, Any]]:
    rooms = await run_in_threadpool(list_known_rooms)
    return [
        {
            **room,
            "status": "available",
        }
        for room in rooms
    ]


async def get_room_energy_forecasts(
    room_id: str,
    limit: int = HISTORY_WINDOW_SIZE,
    capacity: Optional[int] = None,
    area: Optional[float] = None,
    window_count: Optional[int] = None,
) -> dict[str, Any]:
    data = await run_in_threadpool(
        generate_energy_forecast,
        room_id,
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