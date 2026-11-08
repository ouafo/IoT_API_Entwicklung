
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

    # Accept a space instead of T as separator.
    if " " in normalized:
        normalized = normalized.replace(" ", "T", 1)

    # Normalize UTC offsets such as +00.
    if re.search(r"[+-]\d{2}$", normalized):
        normalized += ":00"

    # Normalize Z to UTC offset.
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} has an invalid datetime format. "
                "Use ISO-8601, e.g. 2025-01-01T00:00:00Z."
            ),
        ) from exc


router = APIRouter(
    prefix=settings.API_PREFIX,
    tags=["Weather stations"],
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
        "and time range. Supported measurements include temperature, "
        "humidity, wind direction, wind speed, barometric pressure "
        "and rainfall. Results support OData filtering, sorting "
        "and pagination."
    ),
)
async def read_weather_measurements(
    BuildingID: str = Path(
        ...,
        description="Building identifier, e.g. A.",
    ),

    StartDateTime: str = Query(
        ...,
        description="Start of the time range (ISO-8601, UTC).",
    ),

    EndDateTime: str = Query(
        ...,
        description="End of the time range (ISO-8601, UTC).",
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
    """
    Retrieve weather station measurements.

    Supports OData filtering, sorting, pagination and record counts.
    """

    start_dt = parse_datetime_input(
        StartDateTime,
        "StartDateTime",
    )

    end_dt = parse_datetime_input(
        EndDateTime,
        "EndDateTime",
    )

    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail="Both timestamps must include a timezone.",
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
