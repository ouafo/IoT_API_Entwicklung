"""API routes für OData-Service."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from fastapi.responses import JSONResponse
import re
from app.config import settings
from app.database import connection
from app.models. measurement import MeasurementResponse, RoomResponse
from app.api.odata_helpers import parse_filter, parse_orderby
from app.auth.basic_auth import verify_basic_auth
from app.logger import logger
from app.services.measurement_service import get_measurements, get_all_rooms
from app.exceptions import InvalidDatetimeException, TimeRangeException, FilterException

router = APIRouter(prefix=settings.API_PREFIX)

ALLOWED_FILTER_COLUMNS = [
    "RoomID", "BuildingID", "SensorTypeCode",
    "StartDateTime", "EndDateTime", "MeasureContent", "MeasureUnitCode"
]

ALLOWED_ORDERBY_COLUMNS = [
    "RoomID", "BuildingID", "SensorTypeCode",
    "StartDateTime", "EndDateTime", "MeasureContent"
]

ORDERBY_COLUMN_ALIASES = {
    "RoomID": '"RoomID"',
    "BuildingID": '"BuildingID"',
    "SensorTypeCode": '"SensorTypeCode"',
    "StartDateTime": '"StartDateTime"',
    "EndDateTime": '"EndDateTime"',
    "MeasureContent": '"MeasureContent"'
}


def _parse_iso8601(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        return datetime.fromisoformat(dt_str)
    except ValueError: 
        raise InvalidDatetimeException(dt_str, "datetime")


@router.get("/health")
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
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            db_status = "ok"
        finally:
            connection.put_conn(conn)
    except Exception as e:
        logger. error(f"Health check failed: {e}")
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


@router.get("/Rooms", response_model=RoomResponse)
async def get_rooms(
    filter: Optional[str] = Query(None, alias="$filter"),
    orderby: Optional[str] = Query(None, alias="$orderby"),
    top: Optional[int] = Query(settings.DEFAULT_PAGE_SIZE, alias="$top"),
    skip: Optional[int] = Query(0, alias="$skip"),
    count: Optional[bool] = Query(True, alias="$count"),
    _user: str = Depends(verify_basic_auth),
):
    """Get all rooms with optional OData filtering."""
    building_id = None
    
    # Simple filter parsing for BuildingID
    if filter: 
        if "BuildingID eq" in filter:
            parts = filter.split("'")
            if len(parts) >= 2:
                building_id = parts[1]
    
    return await get_all_rooms(
        building_id=building_id,
        limit=min(top, settings.MAX_PAGE_SIZE),
        offset=skip,
        include_count=count
    )


@router.get("/Rooms('{RoomID}')")
async def get_single_room(
    RoomID: str = Path(..., description="Format: BuildingID-RoomID (e.g., 'A-A203')"),
    _user: str = Depends(verify_basic_auth),
):
    """Get a single room by composite key."""
    parts = RoomID.split("-")
    if len(parts) != 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid RoomID format. Use 'BuildingID-RoomID'"}
        )
    
    building_id, room_id = parts
    
    from app.database. queries import get_rooms
    rooms = get_rooms(building_id=building_id, limit=1000)
    room = next((r for r in rooms if r["RoomID"] == room_id and r["BuildingID"] == building_id), None)
    
    if not room:
        return JSONResponse(
            status_code=404,
            content={"error": "Room not found"}
        )
    
    return {
        "@odata.context": f"{settings.API_PREFIX}/$metadata#Rooms/$entity",
        **room
    }


@router. get("/Rooms('{RoomID}')/Measurements", response_model=MeasurementResponse)
async def get_room_measurements(
    RoomID: str = Path(..., description="Format: BuildingID-RoomID (e.g., 'A-A203')"),
    StartDateTime: str = Query(..., description="ISO 8601 start time (e.g., 2025-01-01T00:00:00Z)"),
    EndDateTime: str = Query(... , description="ISO 8601 end time"),
    SensorTypeCode: Optional[str] = Query(
        None,
        description="Sensor type:  temperature, humidity, co2, light, motion, power, energy_import"
    ),
    filter: Optional[str] = Query(None, alias="$filter", description="OData filter (e.g., MeasureContent gt 22)"),
    orderby: Optional[str] = Query("StartDateTime ASC", alias="$orderby", description="OData ordering"),
    top: Optional[int] = Query(settings.DEFAULT_PAGE_SIZE, alias="$top", description="Limit (max 10000)"),
    skip: Optional[int] = Query(0, alias="$skip", description="Offset for pagination"),
    count: Optional[bool] = Query(True, alias="$count", description="Include total count"),
    _user: str = Depends(verify_basic_auth),
):
    """
    Get measurements for a room with full OData support.
    
    Supports:
    - $filter: OData filter with API field names (e.g., MeasureContent gt 22)
    - $orderby:  Sorting (e.g., StartDateTime desc)
    - $top/$skip: Pagination
    - $count: Total count
    """
    # Validate $top limit
    if top > settings.MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"$top ({top}) ist zu groß. Maximal erlaubt: {settings.MAX_PAGE_SIZE}"
        )
    
    # Parse RoomID (Format: BuildingID-RoomID)
    parts = RoomID.split("-")
    if len(parts) != 2:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid RoomID format. Use 'BuildingID-RoomID'"}
        )
    building_id, room_id = parts
    
    # Parse time range
    start_dt = None
    end_dt = None
    if StartDateTime:
        start_dt = _parse_iso8601(StartDateTime)
    if EndDateTime:
        end_dt = _parse_iso8601(EndDateTime)
    
    # Validate time range
    if start_dt and end_dt and start_dt > end_dt:
        raise TimeRangeException(StartDateTime, EndDateTime)
    
    # Process OData $filter
    filter_clause = None
    filter_params = None
    if filter:
        # Basic validation
        if not re.match(
            r"^[\w_]+ (eq|ne|gt|lt|ge|le) ((-?\d+(\.\d+)?)|('[^']*')|true|false|null)$",
            filter
        ):
            raise HTTPException(status_code=400, detail="Ungültiger OData-Filter")
        
        spaltenname = filter.split()[0]
        if spaltenname not in ALLOWED_FILTER_COLUMNS:
            raise HTTPException(
                status_code=400,
                detail=f"Ungültige Filterspalte: {spaltenname}"
            )
        
        # MAPPING FROM API FIELDS TO DB COLUMNS
        filter_column_map = {
            "RoomID": "room_location",
            "BuildingID": "building",
            "StartDateTime": "start",
            "EndDateTime": "stop"
        }
        
        # Add sensor-specific mapping
        if SensorTypeCode and SensorTypeCode in settings.SENSOR_MAPPINGS:
            mapping = settings.SENSOR_MAPPINGS[SensorTypeCode]
            filter_column_map["MeasureContent"] = f'"{mapping["value_column"]}"'
            filter_column_map["MeasureUnitCode"] = f'"{mapping["unit_column"]}"'
        
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
        parsed_orderby = parse_orderby(orderby, ALLOWED_ORDERBY_COLUMNS, ORDERBY_COLUMN_ALIASES)
        if parsed_orderby:
            orderby_clause = parsed_orderby
    
    # Fetch measurements
    return await get_measurements(
        room_id=room_id,
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
        room_key=RoomID
    )


@router.get("/$metadata")
async def get_metadata(_user: str = Depends(verify_basic_auth)):
    """OData CSDL metadata (Entity Data Model)."""
    xml = f"""<? xml version="1.0" encoding="UTF-8"?>
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="KICAGEM">
      <EntityType Name="Room">
        <Key>
          <PropertyRef Name="RoomKey"/>
        </Key>
        <Property Name="RoomKey" Type="Edm.String" Nullable="false"/>
        <Property Name="RoomID" Type="Edm.String" Nullable="false"/>
        <Property Name="BuildingID" Type="Edm. String" Nullable="false"/>
        <Property Name="ApplicationName" Type="Edm.String"/>
        <NavigationProperty Name="Measurements" Type="Collection(KICAGEM.Measurement)"/>
      </EntityType>
      <EntityType Name="Measurement">
        <Key>
          <PropertyRef Name="MeasurementID"/>
        </Key>
        <Property Name="MeasurementID" Type="Edm. Guid" Nullable="false"/>
        <Property Name="RoomID" Type="Edm.String" Nullable="false"/>
        <Property Name="BuildingID" Type="Edm.String" Nullable="false"/>
        <Property Name="SensorTypeCode" Type="Edm.String" Nullable="false"/>
        <Property Name="StartDateTime" Type="Edm. DateTimeOffset" Nullable="false"/>
        <Property Name="EndDateTime" Type="Edm.DateTimeOffset" Nullable="false"/>
        <Property Name="MeasureContent" Type="Edm.Double" Nullable="false"/>
        <Property Name="MeasureUnitCode" Type="Edm.String" Nullable="false"/>
      </EntityType>
      <EntityContainer Name="Container">
        <EntitySet Name="Rooms" EntityType="KICAGEM.Room">
          <NavigationPropertyBinding Path="Measurements" Target="Measurements"/>
        </EntitySet>
        <EntitySet Name="Measurements" EntityType="KICAGEM.Measurement"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""
    
    return JSONResponse(content=xml, media_type="application/xml")