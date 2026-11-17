"""Database queries for Rooms and Measurements."""

import re
from datetime import datetime
from typing import Tuple, List, Any, Optional

from app.config import settings
from app.database import connection
from app.logger import logger


# ============================================================
# SQL Helper Functions
# ============================================================

def _quote_identifier(identifier: str) -> str:
    """Safely quote a SQL identifier."""
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _get_sensor_mapping(sensor_type: str) -> dict:
    """Return configured mapping for a sensor type."""
    mapping = settings.SENSOR_MAPPINGS.get(sensor_type)
    if mapping is None:
        raise ValueError(f"Unknown sensor type: {sensor_type}")
    return mapping


def _get_schema() -> str:
    """Return safely quoted database schema."""
    return _quote_identifier(settings.DB_SCHEMA)


# ============================================================
# Rooms
# ============================================================

def get_room_by_id(room_id: str) -> List[dict]:
    """
    Resolve room by RoomID.
    BuildingID is retrieved from room_climate.
    Room attributes are joined from end_users.room with defaults applied.
    """
    room_table = f"{_get_schema()}.room_climate"

    query = f"""
    SELECT DISTINCT
        rc.room_location AS "RoomID",
        rc.building AS "BuildingID",
        rc.application_name AS "ApplicationName",
        r.room_type AS "room_type",
        COALESCE(r.capacity, 40) AS "capacity",
        COALESCE(r.area, 100) AS "area",
        COALESCE(r.window_count, 4) AS "window_count"
    FROM {room_table} rc
    LEFT JOIN end_users.room r
        ON r.room_id = rc.room_location
    WHERE rc.room_location = %s
    ORDER BY rc.building
    """

    conn = None
    try:
        conn = connection.get_conn()
        cur = conn.cursor()
        cur.execute(query, [room_id])

        rooms = []
        for row in cur.fetchall():
            rooms.append({
                "RoomID": row[0],
                "BuildingID": row[1],
                "RoomLocation": row[0],
                "ApplicationName": row[2],
                "room_type": row[3],
                "capacity": row[4] if row[4] is not None else 40,
                "area": row[5] if row[5] is not None else 100,
                "window_count": row[6] if row[6] is not None else 4
            })
        return rooms

    except Exception as e:
        logger.error(f"Get room by ID failed: {e}")
        raise

    finally:
        if conn:
            connection.put_conn(conn)


def get_rooms(
    building_id: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[dict]:
    """Fetch all rooms with additional room attributes and fallback defaults."""
    table = f"{_get_schema()}.room_climate"

    params = []
    where_clause = ""

    if building_id:
        where_clause = "WHERE rc.building = %s"
        params.append(building_id)

    query = f"""
    SELECT DISTINCT
        rc.room_location AS "RoomID",
        rc.building AS "BuildingID",
        rc.room_location AS "RoomLocation",
        rc.application_name AS "ApplicationName",
        r.room_type AS "room_type",
        COALESCE(r.capacity, 40) AS "capacity",
        COALESCE(r.area, 100) AS "area",
        COALESCE(r.window_count, 4) AS "window_count"
    FROM {table} rc
    LEFT JOIN end_users.room r
        ON r.room_id = rc.room_location
    {where_clause}
    ORDER BY rc.building, rc.room_location
    LIMIT %s OFFSET %s
    """

    params.extend([limit, offset])

    conn = None
    try:
        conn = connection.get_conn()
        cur = conn.cursor()
        cur.execute(query, params)

        rooms = []
        for row in cur.fetchall():
            rooms.append({
                "RoomID": row[0],
                "BuildingID": row[1],
                "RoomLocation": row[2],
                "ApplicationName": row[3],
                "room_type": row[4],
                "capacity": row[5] if row[5] is not None else 40,
                "area": row[6] if row[6] is not None else 100,
                "window_count": row[7] if row[7] is not None else 4
            })
        return rooms

    except Exception as e:
        logger.error(f"Get rooms failed: {e}")
        raise

    finally:
        if conn:
            connection.put_conn(conn)


# ============================================================
# Room Measurement Time Boundaries
# ============================================================

def get_room_measurement_bounds(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Retrieve the earliest (MIN start) and latest (MAX stop)
    available measurement timestamps for a room.
    """
    if sensor_type:
        sensor_types = [sensor_type]
        _get_sensor_mapping(sensor_type)
    else:
        sensor_types = list(settings.SENSOR_MAPPINGS.keys())

    schema = _get_schema()
    timestamp_queries = []
    params: List[Any] = []

    for current_sensor_type in sensor_types:
        mapping = _get_sensor_mapping(current_sensor_type)
        table = _quote_identifier(mapping["table"])

        conditions = []
        branch_params: List[Any] = []

        if room_id is not None:
            conditions.append('"room_location" = %s')
            branch_params.append(room_id)

        if building_id is not None:
            conditions.append('"building" = %s')
            branch_params.append(building_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        timestamp_queries.append(
            f"""
            SELECT MIN("start") AS earliest_time, MAX("stop") AS latest_time
            FROM {schema}.{table}
            {where_clause}
            """
        )
        params.extend(branch_params)

    if not timestamp_queries:
        return None, None

    sql = """
    SELECT MIN(earliest_time), MAX(latest_time)
    FROM (
    """ + " UNION ALL ".join(timestamp_queries) + """
    ) AS measurement_bounds
    """

    conn = None
    try:
        conn = connection.get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        result = cur.fetchone()
        if result:
            return result[0], result[1]
        return None, None

    except Exception as e:
        logger.error(f"Get room measurement bounds failed: {e}")
        raise

    finally:
        if conn:
            connection.put_conn(conn)


def get_latest_measurement_time(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
) -> Optional[datetime]:
    """Retrieve the latest available measurement timestamp."""
    _, latest_time = get_room_measurement_bounds(
        room_id=room_id,
        building_id=building_id,
        sensor_type=sensor_type,
    )
    return latest_time


# ============================================================
# Build Measurements Query
# ============================================================

def build_measurements_query(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    filter_clause: Optional[str] = None,
    filter_params: Optional[List[Any]] = None,
    order_by: str = '"StartDateTime" ASC',
    limit: int = 1000,
    offset: int = 0,
) -> Tuple[str, List[Any]]:
    """
    Build SQL query for measurements returning 7 standard columns:
    RoomID, BuildingID, SensorTypeCode, StartDateTime,
    EndDateTime, MeasureContent, MeasureUnitCode.
    """
    if sensor_type:
        sensor_types = [sensor_type]
        _get_sensor_mapping(sensor_type)
    else:
        sensor_types = list(settings.SENSOR_MAPPINGS.keys())

    queries = []
    params: List[Any] = []
    schema = _get_schema()

    for current_sensor_type in sensor_types:
        mapping = _get_sensor_mapping(current_sensor_type)
        table = _quote_identifier(mapping["table"])
        value_column = _quote_identifier(mapping["value_column"])
        unit_column = _quote_identifier(mapping["unit_column"])

        conditions = []
        branch_params: List[Any] = []

        if room_id is not None:
            conditions.append('"room_location" = %s')
            branch_params.append(room_id)

        if building_id is not None:
            conditions.append('"building" = %s')
            branch_params.append(building_id)

        if start_time is not None:
            conditions.append('"start" >= %s')
            branch_params.append(start_time)

        if end_time is not None:
            conditions.append('"stop" <= %s')
            branch_params.append(end_time)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        if filter_clause:
            if where_clause:
                where_clause += f" AND ({filter_clause})"
            else:
                where_clause = f"WHERE ({filter_clause})"

        branch_params.extend(filter_params or [])

        query = f"""
        SELECT
            "room_location" AS "RoomID",
            "building" AS "BuildingID",
            %s AS "SensorTypeCode",
            "start" AS "StartDateTime",
            "stop" AS "EndDateTime",
            {value_column} AS "MeasureContent",
            {unit_column} AS "MeasureUnitCode"
        FROM {schema}.{table}
        {where_clause}
        """

        queries.append(query)
        # SensorTypeCode placeholder appears in SELECT before WHERE parameters
        params.append(current_sensor_type)
        params.extend(branch_params)

    combined_query = " UNION ALL ".join(queries)

    sql = f"""
    SELECT *
    FROM (
        {combined_query}
    ) AS measurements
    ORDER BY {order_by}
    LIMIT %s
    OFFSET %s
    """

    params.extend([limit, offset])
    return sql, params


# ============================================================
# Count Measurements
# ============================================================

def count_measurements(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> int:
    """Count total measurements matching filter conditions."""
    if sensor_type:
        sensor_types = [sensor_type]
        _get_sensor_mapping(sensor_type)
    else:
        sensor_types = list(settings.SENSOR_MAPPINGS.keys())

    schema = _get_schema()
    count_queries = []
    params: List[Any] = []

    for current_sensor_type in sensor_types:
        mapping = _get_sensor_mapping(current_sensor_type)
        table = _quote_identifier(mapping["table"])

        conditions = []
        branch_params: List[Any] = []

        if room_id is not None:
            conditions.append('"room_location" = %s')
            branch_params.append(room_id)

        if building_id is not None:
            conditions.append('"building" = %s')
            branch_params.append(building_id)

        if start_time is not None:
            conditions.append('"start" >= %s')
            branch_params.append(start_time)

        if end_time is not None:
            conditions.append('"stop" <= %s')
            branch_params.append(end_time)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        count_queries.append(
            f"""
            SELECT COUNT(*) AS total
            FROM {schema}.{table}
            {where_clause}
            """
        )
        params.extend(branch_params)

    sql = """
    SELECT COALESCE(SUM(total), 0)
    FROM (
    """ + " UNION ALL ".join(count_queries) + """
    ) AS counts
    """

    conn = None
    try:
        conn = connection.get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        result = cur.fetchone()
        return int(result[0] or 0)

    except Exception as e:
        logger.error(f"Count measurements failed: {e}")
        raise

    finally:
        if conn:
            connection.put_conn(conn)