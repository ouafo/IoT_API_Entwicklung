from typing import Tuple, List, Any, Optional
from datetime import datetime

from app.config import settings
from app.database import connection
from app.logger import logger


def get_room_by_id(room_id: str) -> List[dict]:
    """
    Raum anhand der RoomID auflösen.
    BuildingID wird aus room_climate ermittelt.
    Raumattribute werden aus end_users.room ergänzt.
    """

    room_table = (
        f"{settings.DB_SCHEMA}.room_climate"
        if settings.DB_SCHEMA
        else "room_climate"
    )

    query = f"""
        SELECT DISTINCT
            rc.room_location AS "RoomID",
            rc.building AS "BuildingID",
            rc.application_name AS "ApplicationName",
            r.room_type AS "room_type",
            r.capacity AS "capacity",
            r.area AS "area",
            r.window_count AS "window_count"
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
                "capacity": row[4],
                "area": row[5],
                "window_count": row[6]
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
    """Alle Räume mit zusätzlichen Raumattributen holen."""

    table = (
        f"{settings.DB_SCHEMA}.room_climate"
        if settings.DB_SCHEMA
        else "room_climate"
    )

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
            r.capacity AS "capacity",
            r.area AS "area",
            r.window_count AS "window_count"
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
                "capacity": row[5],
                "area": row[6],
                "window_count": row[7]
            })

        return rooms

    except Exception as e:
        logger.error(f"Get rooms failed: {e}")
        raise

    finally:
        if conn:
            connection.put_conn(conn)
