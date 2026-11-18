"""API routes for weather station measurements."""

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
)

from app.config import settings
from app.auth.basic_auth import verify_basic_auth
from app.models.weather import WeatherMeasurementResponse
from app.services.weather_service import get_weather_measurements


def parse_datetime_input(value: str, field_name: str) -> datetime:
    """Parse ISO-8601 datetime input."""
    normalized = value.strip()

    # Accept space instead of T as separator
    if " " in normalized:
        normalized = normalized.replace(" ", "T", 1)

    # Normalize UTC offsets such as +00
    if re.search(r"[+-]\d{2}$", normalized):
        normalized += ":00"

    # Normalize Z to UTC offset
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} has an invalid datetime format. "
                "Use ISO-8601, e.g. 2026-11-18T00:00:00+01:00."
            ),
        ) from exc


router = APIRouter(
    prefix=settings.API_PREFIX,
    tags=["Weather Stations"],
)


WeatherSensorType = Literal[
    "temperature",
    "humidity",
    "wind_direction",
    "wind_speed",
    "barometric_pressure",
    "rainfall",
]


@router.get(
    "/WeatherMeasurements/{BuildingID}",
    response_model=WeatherMeasurementResponse,
    response_model_exclude_none=False,
    summary="Retrieve weather station measurements",
    description=(
        "Returns weather station measurements for a selected building "
        "and time range. StartDateTime and EndDateTime are pre-filled with "
        "current time minus 1 hour and current datetime so the user can adjust them."
    ),
)
async def read_weather_measurements(
    BuildingID: str = Path(
        ...,
        description="Building identifier, e.g. A.",
    ),

    StartDateTime: str = Query(
        ...,
        description="Required start datetime (pre-filled with current time minus 1 hour, editable by user).",
    ),

    EndDateTime: str = Query(
        ...,
        description="Required end datetime (pre-filled with current date and time, editable by user).",
    ),

    SensorTypeCode: Optional[WeatherSensorType] = Query(
        default=None,
        description=(
            "Optional sensor type: temperature, humidity, rainfall, "
            "wind_speed, wind_direction or barometric_pressure."
        ),
    ),

    filter_expr: Optional[str] = Query(
        default=None,
        alias="$filter",
        description="Optional OData filter, e.g. MeasureContent gt 22.",
    ),

    orderby: Optional[str] = Query(
        default=None,
        alias="$orderby",
        description="Optional sorting, e.g. StartDateTime desc.",
    ),

    top: int = Query(
        default=1000,
        alias="$top",
        ge=1,
        le=10000,
        description="Maximum number of records (1–10000).",
    ),

    skip: int = Query(
        default=0,
        alias="$skip",
        ge=0,
        description="Number of records to skip.",
    ),

    count: bool = Query(
        default=True,
        alias="$count",
        description="Include the total record count.",
    ),

    _user: str = Depends(verify_basic_auth),
):
    """Retrieve weather station measurements with OData support."""
    start_dt = parse_datetime_input(
        StartDateTime,
        "StartDateTime",
    )

    end_dt = parse_datetime_input(
        EndDateTime,
        "EndDateTime",
    )

    if start_dt > end_dt:
        raise HTTPException(
            status_code=400,
            detail="StartDateTime must not be later than EndDateTime.",
        )

    try:
        return await get_weather_measurements(
            building_id=BuildingID,
            start_time=start_dt,
            end_time=end_dt,
            sensor_type=SensorTypeCode,
            filter_expr=filter_expr,
            orderby=orderby,
            limit=top,
            offset=skip,
            include_count=count,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc