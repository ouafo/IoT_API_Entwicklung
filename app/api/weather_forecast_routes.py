"""API routes for on-demand 7-day-ahead weather station forecasting."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.auth.basic_auth import verify_basic_auth
from app.config import settings
from app.models.weather_forecast import (
    WeatherForecastSeriesResponse,
    WeatherForecastStationResponse,
)
from app.services.weather_forecast_service import (
    get_weather_forecast_stations,
    get_weather_forecasts,
)


router = APIRouter(
    prefix=f"{settings.API_PREFIX}/Forecasts/Weather",
    tags=["AI Forecasting - Weather"],
    dependencies=[Depends(verify_basic_auth)],
)

WeatherSensorType = Literal[
    "temperature",
    "humidity",
    "barometric_pressure",
    "wind_speed",
    "rainfall",
    "wind_direction",
]


@router.get(
    "/Stations",
    response_model=list[WeatherForecastStationResponse],
    summary="List weather stations available for forecasting",
)
async def get_weather_forecast_stations_route():
    return await get_weather_forecast_stations()


@router.get(
    "/{BuildingID}",
    response_model=WeatherForecastSeriesResponse,
    summary="Get 7-day-ahead weather forecast vs. recent history",
)
async def get_weather_forecasts_route(
    BuildingID: str = Path(..., description="Building identifier, e.g. A."),
    SensorTypeCode: WeatherSensorType = Query(default="temperature"),
    limit: int = Query(default=15, ge=5, le=50, description="Number of recent records (default 15)."),
):
    try:
        result = await get_weather_forecasts(
            building_id=BuildingID,
            sensor_type=SensorTypeCode,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result["Forecast"]:
        raise HTTPException(
            status_code=404,
            detail=f"No recent weather measurements found for building '{BuildingID}'.",
        )
    return result