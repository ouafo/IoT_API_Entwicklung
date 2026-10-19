"""Database queries für Measurements."""

from typing import Tuple, List, Any, Optional
from datetime import datetime
from app.config import settings
from app.database import connection
from app.logger import logger
def build_measurements_query(
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
) -> Tuple[str, List[Any]]:
    """SQL Query für Measurements bauen."""
    params = []
    queries = []
    # Welche Sensoren holen? 
    sensors_to_query = []
    if sensor_type:
        if sensor_type in settings.SENSOR_MAPPINGS:
            sensors_to_query = [sensor_type]
        else: 
            return "", []
    else:
        sensors_to_query = list(settings.SENSOR_MAPPINGS.keys())
    
    # Für jeden Sensor eine Query bauen
    for sensor in sensors_to_query:
        mapping = settings.SENSOR_MAPPINGS[sensor]
        table = mapping["table"]
        value_col = mapping["value_column"]
        unit_col = mapping["unit_column"]
        default_unit = mapping. get("default_unit", "")
        
        fq_table = f"{settings.DB_SCHEMA}.{table}" if settings.DB_SCHEMA else table
        
        # SELECT mit fester Reihenfolge
        select_parts = f"""
            room_location AS "RoomID",
            building AS "BuildingID",
            '{sensor}' AS "SensorTypeCode",
            start AS "StartDateTime",
            stop AS "EndDateTime",
            "{value_col}" AS "MeasureContent",
            COALESCE(NULLIF("{unit_col}", ''), '{default_unit}') AS "MeasureUnitCode"
        """
        # WHERE Bedingungen
        where_parts = []
        
        if room_id:
            where_parts.append("room_location = %s")
            params.append(room_id)
        
        if building_id:
            where_parts. append("building = %s")
            params.append(building_id)
        
        if start_time:
            where_parts.append("start >= %s")
            params.append(start_time)
        
        if end_time:
            where_parts.append("stop <= %s")
            params.append(end_time)
        
        # OData $filter
        if filter_clause: 
            where_parts.append(f"({filter_clause})")
            if filter_params:
                params.extend(filter_params)
        
        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"
        
        # Query zusammenbauen
        query = f"""
            SELECT {select_parts}
            FROM {fq_table}
            WHERE {where_clause}
        """
        
        queries.append(query)
    # UNION ALL für mehrere Sensoren
    if len(queries) > 1:
        combined_query = " UNION ALL ".join([f"({q})" for q in queries])
    else:
        combined_query = queries[0]
    
    # ORDER BY, LIMIT, OFFSET
    final_query = f"""
        SELECT * FROM ({combined_query}) AS measurements
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    return final_query, params

def count_measurements(
    room_id: Optional[str] = None,
    building_id: Optional[str] = None,
    sensor_type:  Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> int:
    """Anzahl Measurements zählen."""
    params = []
    count_queries = []
    
    sensors_to_query = []
    if sensor_type:
        if sensor_type in settings.SENSOR_MAPPINGS:
            sensors_to_query = [sensor_type]
        else:
            return 0
    else: 
        sensors_to_query = list(settings.SENSOR_MAPPINGS.keys())
    
    for sensor in sensors_to_query:
        mapping = settings. SENSOR_MAPPINGS[sensor]
        table = mapping["table"]
        
        fq_table = f"{settings.DB_SCHEMA}.{table}" if settings.DB_SCHEMA else table
        
        where_parts = []
        
        if room_id:
            where_parts.append("room_location = %s")
            params. append(room_id)
        
        if building_id: 
            where_parts.append("building = %s")
            params. append(building_id)
        
        if start_time: 
            where_parts.append("start >= %s")
            params. append(start_time)
        
        if end_time: 
            where_parts.append("stop <= %s")
            params. append(end_time)
        
        where_clause = " AND ".join(where_parts) if where_parts else "TRUE"
        
        count_queries.append(f"SELECT COUNT(*) FROM {fq_table} WHERE {where_clause}")
    
    if len(count_queries) > 1:
        combined = " + ".join([f"({q})" for q in count_queries])
        final_query = f"SELECT {combined}"
    else:
        final_query = count_queries[0]
    
    conn = None
    try:
        conn = connection.get_conn()
        cur = conn.cursor()
        cur.execute(final_query, params)
        result = cur.fetchone()
        return result[0] if result else 0
    except Exception as e:
        logger. error(f"Count failed: {e}")
        return 0
    finally:
        if conn:
            connection.put_conn(conn)


def get_rooms(
    building_id: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[dict]:
    """Alle Räume holen."""
    
    table = f"{settings.DB_SCHEMA}. room_climate" if settings.DB_SCHEMA else "room_climate"
    
    params = []
    where_clause = ""
    
    if building_id:
        where_clause = "WHERE building = %s"
        params.append(building_id)
    
    query = f"""
        SELECT DISTINCT
            room_location AS "RoomID",
            building AS "BuildingID",
            application_name AS "ApplicationName"
        FROM {table}
        {where_clause}
        ORDER BY building, room_location
        LIMIT %s OFFSET %s
    """
    
    params.extend([limit, offset])
    
    conn = None
    try: 
        conn = connection.get_conn()
        cur = conn. cursor()
        cur.execute(query, params)
        
        rooms = []
        for row in cur.fetchall():
            rooms.append({
                "RoomID": row[0],
                "BuildingID": row[1],
                "ApplicationName": row[2]
            })
        
        return rooms
    except Exception as e: 
        logger.error(f"Get rooms failed: {e}")
        return []
    finally:
        if conn:
            connection.put_conn(conn)