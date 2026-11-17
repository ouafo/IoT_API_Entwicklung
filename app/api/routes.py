"""API routes for OData service."""

from datetime import datetime
from typing import Optional
import re

from fastapi import APIRouter, Depends, Query, Path, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import connection
from app.models.measurement import (
    MeasurementResponse,
    RoomResponse,
    RoomTimeRange,
    Room
)
from app.api.odata_helpers import parse_filter, parse_orderby
from app.auth.basic_auth import verify_basic_auth
from app.logger import logger
from app.services.measurement_service import (
    get_measurements,
    get_all_rooms,
    get_room_measurement_bounds
)
from app.exceptions import (
    InvalidDatetimeException,
    FilterException
)


router = APIRouter(
    prefix=settings.API_PREFIX,
    tags=["Building & Room Management"]
)


# ============================================================
# OData Configuration
# ============================================================

ALLOWED_FILTER_COLUMNS = [
    "RoomID",
    "BuildingID",
    "SensorTypeCode",
    "StartDateTime",
    "EndDateTime",
    "MeasureContent",
    "MeasureUnitCode"
]

ALLOWED_ORDERBY_COLUMNS = [
    "RoomID",
    "BuildingID",
    "SensorTypeCode",
    "StartDateTime",
    "EndDateTime",
    "MeasureContent"
]

ORDERBY_COLUMN_ALIASES = {
    "RoomID": '"RoomID"',
    "BuildingID": '"BuildingID"',
    "SensorTypeCode": '"SensorTypeCode"',
    "StartDateTime": '"StartDateTime"',
    "EndDateTime": '"EndDateTime"',
    "MeasureContent": '"MeasureContent"'
}


# ============================================================
# Helper Functions
# ============================================================

def _parse_iso8601(dt_str: str) -> datetime:
    """Parse ISO-8601 datetime string."""
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"

        parsed = datetime.fromisoformat(dt_str)

        if parsed.tzinfo is None:
            parsed = parsed.astimezone()

        return parsed

    except ValueError:
        raise InvalidDatetimeException(dt_str, "datetime")


async def _get_room_by_room_id(room_id: str):
    """
    Resolve a room by its RoomID.
    BuildingID is retrieved internally from the room list.
    """
    rooms_response = await get_all_rooms(
        limit=settings.MAX_PAGE_SIZE,
        offset=0,
        include_count=False
    )

    rooms = (
        rooms_response.value
        if hasattr(rooms_response, "value")
        else rooms_response
    )

    matching_rooms = []

    for room in rooms:
        if isinstance(room, dict):
            room_data = room
        elif hasattr(room, "model_dump"):
            room_data = room.model_dump()
        else:
            room_data = room.dict()

        if room_data.get("RoomID") == room_id:
            matching_rooms.append(room_data)

    if not matching_rooms:
        raise HTTPException(
            status_code=404,
            detail=f"Room '{room_id}' not found. Please redefine room."
        )

    building_ids = {
        room.get("BuildingID")
        for room in matching_rooms
        if room.get("BuildingID") is not None
    }

    if len(building_ids) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"RoomID '{room_id}' is assigned to multiple buildings. "
                "Unique resolution is not possible."
            )
        )

    if not building_ids:
        raise HTTPException(
            status_code=404,
            detail=f"No BuildingID found for RoomID '{room_id}'."
        )

    building_id = next(iter(building_ids))

    room_data = next(
        room for room in matching_rooms
        if room.get("BuildingID") == building_id
    )

    # Apply default room properties if missing
    if room_data.get("capacity") is None:
        room_data["capacity"] = 40
    if room_data.get("area") is None:
        room_data["area"] = 100.0
    if room_data.get("window_count") is None:
        room_data["window_count"] = 4

    return room_data, building_id


# ============================================================
# Health Check
# ============================================================

@router.get(
    "/health",
    tags=["System & Monitoring"]
)
async def health_check():
    """Health check endpoint with database connectivity test."""
    db_status = "unknown"
    latency_ms = None

    try:
        import time

        start = time.perf_counter()
        conn = connection.get_conn()

        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()

            latency_ms = round(
                (time.perf_counter() - start) * 1000,
                2
            )
            db_status = "ok"

        finally:
            connection.put_conn(conn)

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "service": "KICAGEM IoT Analytics",
        "version": settings.API_VERSION,
        "database": {
            "status": db_status,
            "latency_ms": latency_ms
        }
    }


# ============================================================
# GET /Rooms
# ============================================================

@router.get(
    "/Rooms",
    response_model=RoomResponse
)
async def get_rooms(
    filter: Optional[str] = Query(None, alias="$filter"),
    orderby: Optional[str] = Query(None, alias="$orderby"),
    top: Optional[int] = Query(
        settings.DEFAULT_PAGE_SIZE,
        alias="$top"
    ),
    skip: Optional[int] = Query(0, alias="$skip"),
    count: Optional[bool] = Query(True, alias="$count"),
    _user: str = Depends(verify_basic_auth),
):
    """Get all rooms with optional OData filtering."""
    building_id = None

    if filter and "BuildingID eq" in filter:
        parts = filter.split("'")
        if len(parts) >= 2:
            building_id = parts[1]

    return await get_all_rooms(
        building_id=building_id,
        limit=min(top, settings.MAX_PAGE_SIZE),
        offset=skip,
        include_count=count
    )


# ============================================================
# GET /Rooms('{RoomID}')
# ============================================================

@router.get("/Rooms('{RoomID}')")
async def get_single_room(
    RoomID: str = Path(
        ...,
        description="Room identifier, e.g. A203"
    ),
    _user: str = Depends(verify_basic_auth),
):
    """Get a single room by RoomID. BuildingID is resolved internally."""
    room, building_id = await _get_room_by_room_id(RoomID)

    return {
        "@odata.context": (
            f"{settings.API_PREFIX}/$metadata#Rooms/$entity"
        ),
        **room
    }


# ============================================================
# GET /Rooms('{RoomID}')/TimeRange
# ============================================================

@router.get(
    "/Rooms('{RoomID}')/TimeRange",
    response_model=RoomTimeRange
)
async def get_room_time_range(
    RoomID: str = Path(
        ...,
        description="Room identifier, e.g. A203"
    ),
    SensorTypeCode: Optional[str] = Query(
        None,
        description=(
            "Optional sensor type filter: temperature, humidity, co2, "
            "light, motion, power, energy_import"
        )
    ),
    _user: str = Depends(verify_basic_auth),
):
    """Resolve available StartDateTime and EndDateTime bounds for a specific room."""
    _, building_id = await _get_room_by_room_id(RoomID)

    try:
        earliest_dt, latest_dt = await get_room_measurement_bounds(
            room_id=RoomID,
            building_id=building_id,
            sensor_type=SensorTypeCode
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    if earliest_dt is None or latest_dt is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No measurement data available for room '{RoomID}'. "
                "Please redefine room."
            )
        )

    return RoomTimeRange(
        RoomID=RoomID,
        BuildingID=building_id,
        StartDateTime=earliest_dt.isoformat(),
        EndDateTime=latest_dt.isoformat()
    )


# ============================================================
# GET /Rooms('{RoomID}')/Measurements
# ============================================================

@router.get(
    "/Rooms('{RoomID}')/Measurements",
    response_model=MeasurementResponse
)
async def get_room_measurements(
    RoomID: str = Path(
        ...,
        description="Room identifier, e.g. A203"
    ),
    StartDateTime: str = Query(
        ...,
        description="Required start datetime (pre-filled with today 00:00:00, editable by user)"
    ),
    EndDateTime: str = Query(
        ...,
        description="Required end datetime (pre-filled with current date and time, editable by user)"
    ),
    SensorTypeCode: Optional[str] = Query(
        None,
        description=(
            "Sensor type: temperature, humidity, co2, light, "
            "motion, power, energy_import"
        )
    ),
    filter: Optional[str] = Query(
        None,
        alias="$filter",
        description="OData filter, e.g. MeasureContent gt 22"
    ),
    orderby: Optional[str] = Query(
        "StartDateTime ASC",
        alias="$orderby",
        description="OData ordering"
    ),
    top: Optional[int] = Query(
        settings.DEFAULT_PAGE_SIZE,
        alias="$top",
        description="Limit (max 10000)"
    ),
    skip: Optional[int] = Query(
        0,
        alias="$skip",
        description="Offset for pagination"
    ),
    count: Optional[bool] = Query(
        True,
        alias="$count",
        description="Include total count"
    ),
    _user: str = Depends(verify_basic_auth),
):
    """
    Get measurements for a room with OData support.
    StartDateTime and EndDateTime are mandatory fields pre-filled with
    today 00:00 and current date/time so the user can adjust them.
    """

    # Validate pagination
    if top > settings.MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"$top ({top}) is too large. "
                f"Maximum allowed: {settings.MAX_PAGE_SIZE}"
            )
        )

    # Resolve RoomID and BuildingID
    room_dict, building_id = await _get_room_by_room_id(RoomID)
    room_obj = Room(**room_dict)

    # Ensure mandatory StartDateTime and EndDateTime are provided
    if not StartDateTime.strip() or not EndDateTime.strip():
        raise HTTPException(
            status_code=400,
            detail="StartDateTime and EndDateTime are required fields."
        )

    start_dt = _parse_iso8601(StartDateTime)
    end_dt = _parse_iso8601(EndDateTime)

    # Validate chronological order
    if start_dt >= end_dt:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid time range ({start_dt.isoformat()} to {end_dt.isoformat()}): "
                "StartDateTime must be before EndDateTime. "
                "Please redefine room or adjust the time range."
            )
        )

    # Check if requested time range matches available room data bounds
    earliest_dt, latest_dt = await get_room_measurement_bounds(
        room_id=RoomID,
        building_id=building_id,
        sensor_type=SensorTypeCode
    )

    if earliest_dt is None or latest_dt is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No measurement data available for room '{RoomID}'. "
                "Please redefine room."
            )
        )

    # Ensure timezone awareness matches for safe comparison
    if earliest_dt.tzinfo is None:
        earliest_dt = earliest_dt.astimezone()
    if latest_dt.tzinfo is None:
        latest_dt = latest_dt.astimezone()

    if end_dt < earliest_dt or start_dt > latest_dt:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid time range for room '{RoomID}'. "
                f"Available data spans from {earliest_dt.isoformat()} to {latest_dt.isoformat()}. "
                "Please redefine room or select a valid time range."
            )
        )

    # Process OData $filter
    filter_clause = None
    filter_params = None

    if filter:
        if not re.match(
            r"^[\w_]+ (eq|ne|gt|lt|ge|le) "
            r"((-?\d+(\.\d+)?)|('[^']*')|true|false|null)$",
            filter
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid OData filter"
            )

        column_name = filter.split()[0]

        if column_name not in ALLOWED_FILTER_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid filter column: {column_name}"
            )

        filter_column_map = {
            "RoomID": "room_location",
            "BuildingID": "building",
            "StartDateTime": "start",
            "EndDateTime": "stop"
        }

        if (
            SensorTypeCode
            and SensorTypeCode in settings.SENSOR_MAPPINGS
        ):
            mapping = settings.SENSOR_MAPPINGS[SensorTypeCode]
            filter_column_map["MeasureContent"] = (
                f'"{mapping["value_column"]}"'
            )
            filter_column_map["MeasureUnitCode"] = (
                f'"{mapping["unit_column"]}"'
            )

        try:
            filter_clause, filter_params = parse_filter(
                filter,
                ALLOWED_FILTER_COLUMNS,
                filter_column_map
            )

        except Exception as e:
            raise FilterException(filter, str(e))

    # Process OData $orderby
    orderby_clause = '"StartDateTime" ASC'

    if orderby:
        parsed_orderby = parse_orderby(
            orderby,
            ALLOWED_ORDERBY_COLUMNS,
            ORDERBY_COLUMN_ALIASES
        )
        if parsed_orderby:
            orderby_clause = parsed_orderby

    # Fetch measurements
    response = await get_measurements(
        room_id=RoomID,
        building_id=building_id,
        sensor_type=SensorTypeCode,
        start_time=start_dt,
        end_time=end_dt,
        filter_clause=filter_clause,
        filter_params=filter_params,
        order_by=orderby_clause,
        limit=min(top, settings.MAX_PAGE_SIZE),
        offset=skip,
        include_count=count,
        room_key=RoomID,
        room=room_obj
    )

    if not response.value:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No measurements found for room '{RoomID}' in the given time range. "
                "Please redefine room or adjust the time range."
            )
        )

    return response


# ============================================================
# GET /$metadata
# ============================================================

@router.get(
    "/$metadata",
    tags=["API Metadata"]
)
async def get_metadata(
    _user: str = Depends(verify_basic_auth)
):
    """OData CSDL metadata (Entity Data Model)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<edmx:Edmx
 xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"
 Version="4.0">
 <edmx:DataServices>
 <Schema
 xmlns="http://docs.oasis-open.org/odata/ns/edm"
 Namespace="KICAGEM">

 <EntityType Name="Room">
 <Key>
 <PropertyRef Name="RoomKey"/>
 </Key>
 <Property Name="RoomKey" Type="Edm.String" Nullable="false"/>
 <Property Name="RoomID" Type="Edm.String" Nullable="false"/>
 <Property Name="BuildingID" Type="Edm.String" Nullable="false"/>
 <Property Name="ApplicationName" Type="Edm.String"/>
 <NavigationProperty
 Name="Measurements"
 Type="Collection(KICAGEM.Measurement)"/>
 </EntityType>

 <EntityType Name="Measurement">
 <Key>
 <PropertyRef Name="MeasurementID"/>
 </Key>
 <Property Name="MeasurementID" Type="Edm.Guid" Nullable="false"/>
 <Property Name="RoomID" Type="Edm.String" Nullable="false"/>
 <Property Name="BuildingID" Type="Edm.String" Nullable="false"/>
 <Property Name="SensorTypeCode" Type="Edm.String" Nullable="false"/>
 <Property Name="StartDateTime" Type="Edm.DateTimeOffset" Nullable="false"/>
 <Property Name="EndDateTime" Type="Edm.DateTimeOffset" Nullable="false"/>
 <Property Name="MeasureContent" Type="Edm.Double" Nullable="false"/>
 <Property Name="MeasureUnitCode" Type="Edm.String" Nullable="false"/>
 </EntityType>

 <EntityContainer Name="Container">
 <EntitySet Name="Rooms" EntityType="KICAGEM.Room">
 <NavigationPropertyBinding
 Path="Measurements"
 Target="Measurements"/>
 </EntitySet>
 <EntitySet Name="Measurements" EntityType="KICAGEM.Measurement"/>
 </EntityContainer>

 </Schema>
 </edmx:DataServices>
</edmx:Edmx>"""

    return JSONResponse(
        content=xml,
        media_type="application/xml"
    )