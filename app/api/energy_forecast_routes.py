
"""API routes for AI-based energy forecasting."""

from fastapi import APIRouter, Depends, HTTPException, Path

from app.auth.basic_auth import verify_basic_auth
from app.config import settings
from app.logger import logger
from app.models.energy_forecast import (
    EnergyForecastResponse,
    EnergyRoomResponse,
)
from app.services.energy_forecast_service import (
    get_energy_rooms,
    get_latest_energy_forecasts,
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
    summary="List all rooms with energy forecast status",
    description=(
        "Lists all known rooms from the available database tables, "
        "including rooms without generated forecasts. "
        "Rooms without forecasts are marked with status 'no_forecast'. "
        "Forecasts based on input data older than 24 hours are marked as stale."
    ),
)
def list_energy_rooms():
    """Return all known rooms and their energy forecast status."""

    try:
        return get_energy_rooms()

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Energy forecast file is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid energy forecast data: %s",
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Energy forecast data could not be validated.",
        )

    except Exception as exc:
        logger.error(
            "Error retrieving energy rooms: %s",
            exc,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Energy rooms could not be retrieved.",
        )


@router.get(
    "/Rooms/{RoomID}/Latest",
    response_model=list[EnergyForecastResponse],
    summary="Get latest energy forecasts for a room",
    description=(
        "Returns all forecast horizons belonging to the latest "
        "forecast generation for the selected room. "
        "The room identifier must include the building ID, "
        "for example C-C2.005."
    ),
)
def get_latest_room_energy_forecasts(
    RoomID: str = Path(
        ...,
        description="Building and room identifier, e.g. C-C2.005.",
    ),
):
    """Return the latest forecast generation for one room."""

    try:
        result = get_latest_energy_forecasts(RoomID)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No energy forecasts found for room {RoomID}.",
            )

        return result

    except HTTPException:
        raise

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Energy forecast file is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid energy forecast data for %s",
            RoomID,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Energy forecast data could not be validated.",
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
            detail="Energy forecasts could not be retrieved.",
        )


@router.get(
    "/Rooms/{RoomID}",
    response_model=list[EnergyForecastResponse],
    summary="Get all energy forecasts for a room",
    description=(
        "Returns all generated energy forecasts for the selected room. "
        "Results are sorted by forecast origin and horizon. "
        "The room identifier should include the building ID, "
        "for example C-C2.005."
    ),
)
def get_room_energy_forecast(
    RoomID: str = Path(
        ...,
        description="Building and room identifier, e.g. C-C2.005.",
    ),
):
    """Return all forecasts for one room."""

    try:
        result = get_room_energy_forecasts(RoomID)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No energy forecasts found for room {RoomID}.",
            )

        return result

    except HTTPException:
        raise

    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Energy forecast file is currently unavailable.",
        )

    except ValueError as exc:
        logger.error(
            "Invalid energy forecast data for %s",
            RoomID,
            exc_info=exc,
        )

        raise HTTPException(
            status_code=503,
            detail="Energy forecast data could not be validated.",
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
            detail="Energy forecasts could not be retrieved.",
        )
