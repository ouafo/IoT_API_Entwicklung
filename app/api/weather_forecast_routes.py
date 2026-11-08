"""API routes for weather forecasts."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.basic_auth import verify_basic_auth
from app.config import settings
from app.models.weather_forecast import (
    WeatherForecastResponse,
    WeatherForecastStationResponse,
)
from app.services import weather_forecast_service


router = APIRouter(
    prefix=f"{settings.API_PREFIX}/Forecasts/Weather",
    tags=["AI Forecasting – Weather"],
    dependencies=[Depends(verify_basic_auth)],
)


def _handle_service_error(exc: Exception) -> HTTPException:
    """Convert service errors into HTTP responses."""

    if isinstance(exc, FileNotFoundError):
        return HTTPException(
            status_code=503,
            detail=(
                "Weather forecasts are not available yet. "
                "The forecast CSV file has not been generated."
            ),
        )

    return HTTPException(
        status_code=500,
        detail=f"Could not load weather forecasts: {str(exc)}",
    )


@router.get(
    "/Stations",
    response_model=list[WeatherForecastStationResponse],
    summary="List weather stations with available forecasts",
)
def get_weather_forecast_stations():
    """List all buildings for which weather forecasts exist."""

    try:
        return weather_forecast_service.get_weather_forecast_stations()
    except (FileNotFoundError, ValueError) as exc:
        raise _handle_service_error(exc) from exc


@router.get(
    "/{BuildingID}/Latest",
    response_model=list[WeatherForecastResponse],
    summary="Get the latest weather forecasts for a building",
)
def get_latest_weather_forecasts(
    BuildingID: str,
    SensorTypeCode: Optional[str] = Query(
        default=None,
        description="Filter by sensor type, e.g. temperature, humidity, wind_speed, barometric_pressure, rain_fall.",
    ),
    HorizonMinutes: Optional[int] = Query(
        default=None,
        ge=1,
        description="Filter by forecast horizon in minutes, e.g. 15, 30 or 60.",
    ),
):
    """Return forecasts from the latest forecast run for a building."""

    try:
        forecasts = weather_forecast_service.get_latest_weather_forecasts(
            building_id=BuildingID,
            sensor_type=SensorTypeCode,
            horizon_minutes=HorizonMinutes,
        )

        if not forecasts:
            raise HTTPException(
                status_code=404,
                detail=f"No weather forecasts found for building '{BuildingID}'.",
            )

        return forecasts

    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise _handle_service_error(exc) from exc


@router.get(
    "/{BuildingID}",
    response_model=list[WeatherForecastResponse],
    summary="Get weather forecasts for a building",
)
def get_weather_forecasts(
    BuildingID: str,
    SensorTypeCode: Optional[str] = Query(
        default=None,
        description="Filter by sensor type, e.g. temperature, humidity, wind_speed, barometric_pressure, rain_fall.",
    ),
    HorizonMinutes: Optional[int] = Query(
        default=None,
        ge=1,
        description="Filter by forecast horizon in minutes, e.g. 15, 30 or 60.",
    ),
):
    """Return all available weather forecasts for a building."""

    try:
        forecasts = weather_forecast_service.get_weather_forecasts(
            building_id=BuildingID,
            sensor_type=SensorTypeCode,
            horizon_minutes=HorizonMinutes,
        )

        if not forecasts:
            raise HTTPException(
                status_code=404,
                detail=f"No weather forecasts found for building '{BuildingID}'.",
            )

        return forecasts

    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise _handle_service_error(exc) from exc