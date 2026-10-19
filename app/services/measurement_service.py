"""Measurement Service Layer."""

from typing import List, Optional, Any
from datetime import datetime
from starlette.concurrency import run_in_threadpool

from app.database import connection, queries
from app.models.measurement import Measurement, MeasurementResponse, Room, RoomResponse
from app.config import settings
from app.logger import logger
from app.exceptions import DatabaseException


async def get_measurements(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type:  Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    filter_clause: Optional[str] = None,
    filter_params: Optional[List[Any]] = None,
    order_by: str = "start ASC",
    limit: int = 1000,
    offset: int = 0,
    include_count: bool = True,
    room_key: Optional[str] = None,
) -> MeasurementResponse:
    """Measurements aus DB holen."""
    
    def _execute():
        sql, params = queries.build_measurements_query(
            room_id=room_id,
            building_id=building_id,
            sensor_type=sensor_type,
            start_time=start_time,
            end_time=end_time,
            filter_clause=filter_clause,
            filter_params=filter_params,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )
        conn = None
        try:
            conn = connection.get_conn()
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            measurements = []
            for row in rows:
                measurements.append(Measurement(
                    RoomID=row[0],
                    BuildingID=row[1],
                    SensorTypeCode=row[2],
                    StartDateTime=row[3]. isoformat() if row[3] else None,
                    EndDateTime=row[4].isoformat() if row[4] else None,
                    MeasureContent=float(row[5]) if row[5] is not None else 0.0,
                    MeasureUnitCode=row[6] if row[6] else ""
                ))
            
            return measurements
        except Exception as e: 
            logger.error(f"Query failed: {e}")
            raise DatabaseException("Measurements query failed", e)
        finally:
            if conn:
                connection.put_conn(conn)
    
    try:
        measurements = await run_in_threadpool(_execute)
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise DatabaseException("Service execution failed", e)
    
    total_count = 0
    if include_count:
        total_count = await run_in_threadpool(
            queries.count_measurements,
            room_id, building_id, sensor_type, start_time, end_time
        )
    
    context = f"{settings.API_PREFIX}/$metadata#Measurements"
    if room_key:
        context = f"{settings.API_PREFIX}/$metadata#Rooms('{room_key}')/Measurements"
    
    next_link = None
    if len(measurements) == limit and offset + limit < total_count:
        next_link = f"{settings.API_PREFIX}/Rooms('{room_key}')/Measurements? $skip={offset + limit}&$top={limit}"
    
    return MeasurementResponse(
        odata_context=context,
        odata_count=total_count if include_count else None,
        odata_nextLink=next_link,
        value=measurements
    )

async def get_all_rooms(
    building_id: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
    include_count: bool = True,
) -> RoomResponse:
    """Alle Räume holen."""

    def _execute():
        return queries.get_rooms(
            building_id=building_id,
            limit=limit,
            offset=offset
        )
    try:
        room_dicts = await run_in_threadpool(_execute)
        rooms = [Room(**r) for r in room_dicts]
    except Exception as e:
        logger.error(f"Get rooms failed: {e}")
        raise DatabaseException("Get rooms failed", e)
    total_count = len(rooms) if not include_count else len(rooms)
    next_link = None
    if len(rooms) == limit:
        next_link = f"{settings.API_PREFIX}/Rooms? $skip={offset + limit}&$top={limit}"
    
    return RoomResponse(
        odata_context=f"{settings. API_PREFIX}/$metadata#Rooms",
        odata_count=total_count if include_count else None,
        odata_nextLink=next_link,
        value=rooms
    )