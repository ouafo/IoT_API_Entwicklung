
"""Service for retrieving weather station measurements."""

import re
from datetime import datetime
from typing import Optional

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import connection
from app.logger import logger
from app.models.weather import (
    WeatherMeasurement,
    WeatherMeasurementResponse,
)


SENSOR_COLUMNS = {
    "temperature": ("temperature", "temperature_unit"),
    "humidity": ("humidity", "humidity_unit"),
    "wind_direction": ("wind_direction", "wind_direction_unit"),
    "wind_speed": ("wind_speed", "wind_speed_unit"),
    "barometric_pressure": (
        "barometric_pressure",
        "barometric_pressure_unit",
    ),
    "rainfall": ("rainfall", "rainfall_unit"),
}

FILTER_COLUMNS = {
    "BuildingID": '"BuildingID"',
    "SensorTypeCode": '"SensorTypeCode"',
    "StartDateTime": '"StartDateTime"',
    "EndDateTime": '"EndDateTime"',
    "MeasureContent": '"MeasureContent"',
    "MeasureUnitCode": '"MeasureUnitCode"',
}

ORDER_COLUMNS = FILTER_COLUMNS.copy()

FILTER_OPERATORS = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "ge": ">=",
    "lt": "<",
    "le": "<=",
}


def build_filter(filter_expr):
    """Build a parameterized filter for one OData comparison."""
    if not filter_expr:
        return "", []

    match = re.fullmatch(
        r"\s*(BuildingID|SensorTypeCode|StartDateTime|EndDateTime|"
        r"MeasureContent|MeasureUnitCode)\s+"
        r"(eq|ne|gt|ge|lt|le)\s+(.+?)\s*",
        filter_expr,
        flags=re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            "Unsupported $filter. Example: MeasureContent gt 22"
        )

    field, operator, raw_value = match.groups()

    # Normalize the field name to its canonical spelling.
    field = next(
        name for name in FILTER_COLUMNS
        if name.lower() == field.lower()
    )
    operator = operator.lower()
    column = FILTER_COLUMNS[field]
    sql_operator = FILTER_OPERATORS[operator]

    raw_value = raw_value.strip()

    if field == "MeasureContent":
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(
                "MeasureContent filters require a numeric value"
            ) from exc

    elif field in ("StartDateTime", "EndDateTime"):
        if raw_value.startswith("'") and raw_value.endswith("'"):
            raw_value = raw_value[1:-1]
        try:
            value = datetime.fromisoformat(
                raw_value.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                f"{field} requires an ISO 8601 timestamp"
            ) from exc

    else:
        if not (
            len(raw_value) >= 2
            and raw_value[0] == "'"
            and raw_value[-1] == "'"
        ):
            raise ValueError(
                f"{field} requires a single-quoted string"
            )
        value = raw_value[1:-1].replace("''", "'")

    return f"{column} {sql_operator} %s", [value]


async def get_weather_measurements(
    building_id: str,
    start_time: datetime,
    end_time: datetime,
    sensor_type: Optional[str] = None,
    filter_expr: Optional[str] = None,
    orderby: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
    include_count: bool = True,
) -> WeatherMeasurementResponse:

    def _execute():
        table = f'"{settings.DB_SCHEMA}"."weather_station"'

        if sensor_type and sensor_type not in SENSOR_COLUMNS:
            raise ValueError(
                f"Unsupported SensorTypeCode: {sensor_type}"
            )

        sensor_types = (
            [sensor_type] if sensor_type else list(SENSOR_COLUMNS)
        )

        branches = []
        params = []

        for code in sensor_types:
            value_column, unit_column = SENSOR_COLUMNS[code]

            branches.append(
                f"""
                SELECT
                    building AS "BuildingID",
                    %s AS "SensorTypeCode",
                    "start" AS "StartDateTime",
                    "stop" AS "EndDateTime",
                    {value_column} AS "MeasureContent",
                    {unit_column} AS "MeasureUnitCode"
                FROM {table}
                WHERE building = %s
                  AND "start" >= %s
                  AND "stop" <= %s
                  AND {value_column} IS NOT NULL
                """
            )

            params.extend([
                code,
                building_id,
                start_time,
                end_time,
            ])

        cte = (
            "WITH measurements AS ("
            + " UNION ALL ".join(branches)
            + ")"
        )

        filter_sql, filter_params = build_filter(filter_expr)
        where_sql = f" WHERE {filter_sql}" if filter_sql else ""

        order_sql = 'ORDER BY "StartDateTime" ASC'

        if orderby:
            match = re.fullmatch(
                r"\s*([A-Za-z]+)(?:\s+(asc|desc))?\s*",
                orderby,
                flags=re.IGNORECASE,
            )

            if not match:
                raise ValueError(
                    "Unsupported $orderby. Example: StartDateTime desc"
                )

            field, direction = match.groups()

            canonical_field = next(
                (
                    name for name in ORDER_COLUMNS
                    if name.lower() == field.lower()
                ),
                None,
            )

            if canonical_field is None:
                raise ValueError(
                    f"Unsupported $orderby field: {field}"
                )

            direction = (direction or "asc").upper()
            order_sql = (
                f"ORDER BY {ORDER_COLUMNS[canonical_field]} {direction}"
            )

        conn = None

        try:
            conn = connection.get_conn()
            cur = conn.cursor()

            count_sql = (
                f"{cte} SELECT COUNT(*) FROM measurements{where_sql}"
            )
            cur.execute(count_sql, params + filter_params)
            total_count = cur.fetchone()[0]

            data_sql = f"""
                {cte}
                SELECT
                    "BuildingID",
                    "SensorTypeCode",
                    "StartDateTime",
                    "EndDateTime",
                    "MeasureContent",
                    "MeasureUnitCode"
                FROM measurements
                {where_sql}
                {order_sql}
                LIMIT %s OFFSET %s
            """

            cur.execute(
                data_sql,
                params + filter_params + [limit, offset],
            )
            rows = cur.fetchall()

            measurements = [
                WeatherMeasurement(
                    BuildingID=row[0],
                    SensorTypeCode=row[1],
                    StartDateTime=row[2],
                    EndDateTime=row[3],
                    MeasureContent=row[4],
                    MeasureUnitCode=row[5],
                )
                for row in rows
            ]

            return WeatherMeasurementResponse(
                count=total_count if include_count else None,
                value=measurements,
            )

        except Exception:
            logger.exception("Weather measurements query failed")
            raise

        finally:
            if conn is not None:
                connection.put_conn(conn)

    return await run_in_threadpool(_execute)
