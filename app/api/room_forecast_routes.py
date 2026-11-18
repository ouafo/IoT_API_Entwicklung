"""API routes for on-demand 7-day-ahead room climate forecasting."""

from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.auth.basic_auth import verify_basic_auth
from app.config import settings
from app.models.room_forecast import (
    ForecastRoomsResponse,
    RoomForecastSeriesResponse,
    RoomForecastSummary,
)
from app.services.room_climate_forecast import (
    get_forecast_rooms,
    get_room_forecast_summary,
    get_room_forecasts,
)


router = APIRouter(
    prefix=settings.API_PREFIX,
    tags=["AI Forecasting - Rooms"],
    dependencies=[Depends(verify_basic_auth)],
)

SensorType = Literal["temperature", "humidity", "co2", "light"]


@router.get(
    "/Forecasts/Rooms",
    response_model=ForecastRoomsResponse,
    summary="List all known rooms for climate forecasting",
)
async def list_rooms_with_forecasts():
    rooms = await get_forecast_rooms()
    return {"count": len(rooms), "value": rooms}


@router.get(
    "/Forecasts/Rooms/{RoomID}",
    response_model=RoomForecastSeriesResponse,
    summary="Get 7-day-ahead room climate forecast vs. recent history",
    description=(
        "Uses the last N=15 valid measurements of the room to project "
        "a 15-point forecast exactly 7 days ahead (same weekday & time), "
        "incorporating room attributes (capacity, area, window_count)."
    ),
)
async def get_forecasts_for_room(
    RoomID: str = Path(..., description="Room ID (e.g. A203 or A-A203)."),
    sensor_type: SensorType = Query(default="temperature"),
    limit: int = Query(default=15, ge=5, le=50, description="Number of recent records (default 15)."),
    capacity: Optional[int] = Query(default=None, ge=1, description="Optional room capacity override."),
    area: Optional[float] = Query(default=None, gt=0, description="Optional room area in m² override."),
    window_count: Optional[int] = Query(default=None, ge=0, description="Optional window count override."),
):
    try:
        result = await get_room_forecasts(
            room_id=RoomID,
            limit=limit,
            sensor_type=sensor_type,
            capacity=capacity,
            area=area,
            window_count=window_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not result["forecast"]:
        raise HTTPException(
            status_code=404,
            detail=f"No recent {sensor_type} measurements found for room '{RoomID}'.",
        )
    return result


@router.get(
    "/Forecasts/Rooms/{RoomID}/Summary",
    response_model=RoomForecastSummary,
    summary="Get statistical comparison of recent history vs. 7-day forecast",
)
async def get_room_forecast_statistics(
    RoomID: str = Path(..., description="Room ID (e.g. A203 or A-A203)."),
    sensor_type: SensorType = Query(default="temperature"),
    capacity: Optional[int] = Query(default=None, ge=1),
    area: Optional[float] = Query(default=None, gt=0),
    window_count: Optional[int] = Query(default=None, ge=0),
):
    try:
        summary = await get_room_forecast_summary(
            room_id=RoomID,
            sensor_type=sensor_type,
            capacity=capacity,
            area=area,
            window_count=window_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"No recent {sensor_type} measurements found for room '{RoomID}'.",
        )
    return summary