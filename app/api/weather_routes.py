
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.config import settings
from app.auth.basic_auth import verify_basic_auth
from app.models.weather import WeatherMeasurementResponse
from app.services.weather_service import get_weather_measurements

#Konvertierung der Zeitstempel in UTC-Format
import re


def parse_datetime_input(value: str, field_name: str) -> datetime:
    """Accept ISO-8601 datetimes with T or a space separator."""

    normalized = value.strip()

    # Replace the first space between date and time with T
    if " " in normalized:
        normalized = normalized.replace(" ", "T", 1)

    # Normalize UTC offsets such as +00 to +00:00
    if re.search(r"[+-]\d{2}$", normalized):
        normalized += ":00"

    # Normalize Z (UTC) to +00:00
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} has an invalid datetime format. "
                "Use ISO-8601, e.g. 2024-08-01T23:00:00Z."
            ),
        )


router = APIRouter(prefix=settings.API_PREFIX)

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
    response_model_exclude_none=True,
    tags=["Weather"],
    summary="Retrieve weather station measurements",
)
async def read_weather_measurements(
    BuildingID: str = Path(
        ...,
        description="Building ID (e.g., 'A')",
    ),
    StartDateTime: str = Query(
        ...,
        description="e.g., 2025-01-01T00:00:00Z",
    ),
    EndDateTime: str = Query(
        ...,
        description="e.g., 2025-01-01T00:00:00Z",
    ),
    SensorTypeCode: Optional[WeatherSensorType] = Query(
        None,
        description="Weather measurement type (temperature, humidity, rainfall, wind_speed, wind_direction, barometric_pressure)",
    ),
    filter_expr: Optional[str] = Query(
        None,
        alias="$filter",
        description="Example: MeasureContent gt 22",
    ),
    orderby: Optional[str] = Query(
        None,
        alias="$orderby",
        description="Example: StartDateTime desc",
    ),
    top: int = Query(
        1000, alias="$top", ge=1, le=10000
    ),
    skip: int = Query(
        0, alias="$skip", ge=0
    ),
    count: bool = Query(
        True, alias="$count"
    ),
    _user: str = Depends(verify_basic_auth),
):
    """Retrieve weather station measurements for a specific building and time range with full OData support.

Supports:

        $filter: OData filter with API field names (e.g., MeasureContent gt 22)
        $orderby: Sorting (e.g., StartDateTime desc)
        $top/$skip: Pagination
        $count: Total count
            """
    start_dt = parse_datetime_input(
        StartDateTime, "StartDateTime"
    )
    end_dt = parse_datetime_input(
        EndDateTime, "EndDateTime"
    )

    if start_dt > end_dt:
        raise HTTPException(
            status_code=400,
            detail="StartDateTime must not be later than EndDateTime",
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
