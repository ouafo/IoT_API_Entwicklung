"""API routes for on-demand 7-day-ahead energy forecasting."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.auth.basic_auth import verify_basic_auth
from app.config import settings
from app.models.energy_forecast import (
    EnergyForecastSeriesResponse,
    EnergyRoomResponse,
)
from app.services.energy_forecast_service import (
    get_energy_rooms,
    get_room_energy_forecasts,
)


router = APIRouter(
    prefix=f"{settings.API_PREFIX}/Forecasts/Energy",
    tags=["AI Forecasting - Energy"],
    dependencies=[Depends(verify_basic_auth)],
)


@router.get(
    "/Rooms",
    response_model=list[EnergyRoomResponse],
    summary="List all rooms available for energy forecasting",
)
async def list_energy_rooms():
    return await get_energy_rooms()


@router.get(
    "/Rooms/{RoomID}",
    response_model=EnergyForecastSeriesResponse,
    summary="Get 7-day-ahead energy forecast vs. recent history",
    description=(
        "Uses the last N=15 energy intervals of the room to project "
        "consumption 7 days ahead (same weekday & time), scaled by "
        "room capacity and area."
    ),
)
async def get_room_energy_forecast(
    RoomID: str = Path(..., description="Room ID (e.g. C2.005 or C-C2.005)."),
    limit: int = Query(default=15, ge=5, le=50, description="Number of recent intervals (default 15)."),
    capacity: Optional[int] = Query(default=None, ge=1, description="Optional room capacity override."),
    area: Optional[float] = Query(default=None, gt=0, description="Optional room area in m² override."),
    window_count: Optional[int] = Query(default=None, ge=0, description="Optional window count override."),
):
    try:
        result = await get_room_energy_forecasts(
            room_id=RoomID,
            limit=limit,
            capacity=capacity,
            area=area,
            window_count=window_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not result["forecast"]:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough recent energy measurements found for room '{RoomID}'.",
        )
    return result