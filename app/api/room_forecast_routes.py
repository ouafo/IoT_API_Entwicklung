
"""API routes for AI-based room climate forecasting."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.config import settings
from app.auth.basic_auth import verify_basic_auth
from app.logger import logger

from app.models.room_forecast import (
    ForecastRoomsResponse,
    RoomForecastsResponse,
    RoomForecastSummary,
)

from app.services.room_climate_forecast import (
    get_forecast_rooms,
    get_room_forecasts,
    get_room_forecast_summary,
)


router = APIRouter(
    prefix=settings.API_PREFIX,
    tags=["AI Forecasting - Rooms"],
)


SensorType = Literal["temperature", "humidity", "co2", "light"]
ForecastHorizon = Literal[15, 30, 45, 60]


@router.get(
    "/Forecasts/Rooms",
    response_model=ForecastRoomsResponse,
    summary="List all known rooms and their forecast status",
    description=(
        "Lists all known building rooms, including rooms without forecasts. "
        "For each room, the available forecast sensors and horizons are returned. "
        "Forecast values are read from the current room climate forecast CSV. "
        "Rooms without forecasts are marked with status 'no_forecast'. "
        "Forecasts based on input data older than 24 hours are marked as stale."
    ),
)
async def get_rooms_with_forecasts(
    _user: str = Depends(verify_basic_auth),
):
    try:
        rooms = get_forecast_rooms()

        return {
            "count": len(rooms),
            "value": rooms,
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Room climate forecast CSV is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid room climate forecast data: %s",
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Room climate forecast data could not be validated.",
        )

    except Exception as exc:
        logger.error(
            "Error retrieving forecast rooms: %s",
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Forecast rooms could not be retrieved.",
        )


@router.get(
    "/Forecasts/Rooms/{RoomID}",
    response_model=RoomForecastsResponse,
    response_model_exclude_none=True,
    summary="Get room climate forecasts",
    description=(
        "Returns forecasts for the selected room and sensor type. "
        "Optionally, results can be restricted to a specific forecast horizon. "
        "Supported sensors: temperature, humidity, co2 and light. "
        "Supported horizons: 15, 30, 45 and 60 minutes. "
        "Results are sorted by target timestamp in descending order. "
        "The room identifier includes the building ID, e.g. A-A304."
    ),
)
async def get_forecasts_for_room(
    RoomID: str = Path(
        description="Building and room identifier, e.g. A-A304."
    ),
    sensor_type: SensorType = Query(
        default="temperature",
        description=(
            "Sensor type: temperature, humidity, co2 or light."
        ),
    ),
    horizon_minutes: ForecastHorizon | None = Query(
        default=None,
        description=(
            "Optional forecast horizon in minutes: 15, 30, 45 or 60."
        ),
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of forecast records (1–1000).",
    ),
    _user: str = Depends(verify_basic_auth),
):
    try:
        forecasts = get_room_forecasts(
            room_id=RoomID,
            limit=limit,
            sensor_type=sensor_type,
            horizon_minutes=horizon_minutes,
        )

        return {
            "count": len(forecasts),
            "RoomID": RoomID,
            "value": forecasts,
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Room climate forecast CSV is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid forecasts for room %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Room climate forecast data could not be validated.",
        )

    except Exception as exc:
        logger.error(
            "Error retrieving forecasts for %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Room forecasts could not be retrieved.",
        )


@router.get(
    "/Forecasts/Rooms/{RoomID}/Latest",
    response_model=RoomForecastsResponse,
    summary="Get latest room climate forecast",
    description=(
        "Returns the latest forecast record for the selected room and sensor. "
        "Optionally, the result can be restricted to a specific forecast horizon. "
        "The latest forecast is not necessarily current; check data_age_hours "
        "and is_stale."
    ),
)
async def get_latest_room_forecast(
    RoomID: str = Path(
        description="Building and room identifier, e.g. A-A304."
    ),
    sensor_type: SensorType = Query(
        default="temperature",
        description=(
            "Sensor type: temperature, humidity, co2 or light."
        ),
    ),
    horizon_minutes: ForecastHorizon | None = Query(
        default=None,
        description=(
            "Optional forecast horizon in minutes: 15, 30, 45 or 60."
        ),
    ),
    _user: str = Depends(verify_basic_auth),
):
    try:
        forecasts = get_room_forecasts(
            room_id=RoomID,
            limit=1,
            sensor_type=sensor_type,
            horizon_minutes=horizon_minutes,
        )

        if not forecasts:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No {sensor_type} forecasts found for room {RoomID}."
                ),
            )

        return {
            "count": len(forecasts),
            "RoomID": RoomID,
            "value": forecasts,
        }

    except HTTPException:
        raise

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Room climate forecast CSV is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid latest forecast for room %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Room climate forecast data could not be validated.",
        )

    except Exception as exc:
        logger.error(
            "Error retrieving latest forecast for %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Latest room forecast could not be retrieved.",
        )


@router.get(
    "/Forecasts/Rooms/{RoomID}/Summary",
    response_model=RoomForecastSummary,
    summary="Get room climate forecast statistics",
    description=(
        "Returns statistical information about the latest forecast generation "
        "for the selected room and sensor type. "
        "Statistics include average, minimum and maximum predicted values."
    ),
)
async def get_room_forecast_statistics(
    RoomID: str = Path(
        description="Building and room identifier, e.g. A-A304."
    ),
    sensor_type: SensorType = Query(
        default="temperature",
        description=(
            "Sensor type: temperature, humidity, co2 or light."
        ),
    ),
    _user: str = Depends(verify_basic_auth),
):
    try:
        summary = get_room_forecast_summary(
            room_id=RoomID,
            sensor_type=sensor_type,
        )

        if summary is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No {sensor_type} forecasts found for room {RoomID}."
                ),
            )

        return summary

    except HTTPException:
        raise

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Room climate forecast CSV is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid forecast summary for room %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Room climate forecast data could not be validated.",
        )

    except Exception as exc:
        logger.error(
            "Error retrieving forecast summary for %s: %s",
            RoomID,
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Room forecast summary could not be retrieved.",
        )
