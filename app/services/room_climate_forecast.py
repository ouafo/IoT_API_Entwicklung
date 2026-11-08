
"""Service for room climate forecasts.

Room inventory is read from PostgreSQL.
Forecast values are read from the generated forecast CSV.

Supported forecast variables:
- temperature
- humidity
- co2
- light
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import math

import pandas as pd
from psycopg.rows import dict_row

from app.database import connection


BASE_DIR = Path(__file__).resolve().parents[2]

FORECAST_FILE = (
    BASE_DIR
    / "forecasting"
    / "room_climate"
    / "results"
    / "forecasts.csv"
)

MAX_FORECAST_AGE_HOURS = 24

SENSOR_CONFIG = {
    "temperature": {
        "label": "Temperatur",
        "unit": "°C",
    },
    "humidity": {
        "label": "Luftfeuchtigkeit",
        "unit": "%",
    },
    "co2": {
        "label": "CO₂",
        "unit": "ppm",
    },
    "light": {
        "label": "Licht",
        "unit": "Lux",
    },
}

NO_FORECAST_COMMENT = (
    "Keine Raumklima-Prognose vorhanden. Datenlage für das Training prüfen."
)

STALE_COMMENT = (
    "Prognose basiert auf Eingangsdaten, die älter als 24 Stunden sind."
)


def _safe_float(value: Any) -> float | None:
    """Convert a value to a finite Python float.

    NaN, positive infinity, negative infinity and invalid values
    are converted to None to ensure JSON compatibility.
    """

    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _safe_datetime(value: Any) -> datetime | None:
    """Convert a value to a timezone-aware Python datetime."""

    if value is None or pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()

    if not isinstance(value, datetime):
        value = pd.to_datetime(
            value,
            utc=True,
            errors="coerce",
        )

        if pd.isna(value):
            return None

        value = value.to_pydatetime()

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value


def get_all_rooms() -> list[dict[str, str]]:
    """Return all known building-room combinations."""

    conn = connection.get_conn()

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT DISTINCT
                    building,
                    room_location
                FROM (
                    SELECT building, room_location
                    FROM public.device_battery

                    UNION

                    SELECT building, room_location
                    FROM public.door_window

                    UNION

                    SELECT building, room_location
                    FROM public.energy

                    UNION

                    SELECT building, room_location
                    FROM public."level"

                    UNION

                    SELECT building, room_location
                    FROM public.people_counter

                    UNION

                    SELECT building, room_location
                    FROM public.room_climate

                    UNION

                    SELECT building, room_location
                    FROM public.room_climate_old

                    UNION

                    SELECT building, room_location
                    FROM public.room_energy
                ) AS room_sources
                WHERE building IS NOT NULL
                  AND room_location IS NOT NULL
                ORDER BY building, room_location
            """)

            rows = cur.fetchall()

            return [
                {
                    "room_id": (
                        f'{str(row["building"]).strip()}-'
                        f'{str(row["room_location"]).strip()}'
                    )
                }
                for row in rows
            ]

    finally:
        connection.put_conn(conn)


def load_forecasts() -> pd.DataFrame:
    """Load and validate the multi-sensor forecast CSV."""

    if not FORECAST_FILE.exists():
        raise FileNotFoundError(
            f"Climate forecast CSV not found: {FORECAST_FILE}"
        )

    df = pd.read_csv(FORECAST_FILE)

    required = {
        "room_id",
        "forecast_origin",
        "forecast_timestamp",
        "horizon_minutes",
        "model_type",
    }

    # Support both the new multi-sensor format and the old
    # temperature-only format during migration.
    if "predicted_value" not in df.columns:
        if "predicted_temperature_c" in df.columns:
            df["predicted_value"] = df["predicted_temperature_c"]
        else:
            required.add("predicted_value")

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing climate forecast columns: {sorted(missing)}"
        )

    if df.empty:
        return df

    df = df.copy()

    df["room_id"] = (
        df["room_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "sensor_type" not in df.columns:
        df["sensor_type"] = "temperature"

    df["sensor_type"] = (
        df["sensor_type"]
        .fillna("temperature")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    if "unit" not in df.columns:
        df["unit"] = df["sensor_type"].map(
            lambda sensor: SENSOR_CONFIG.get(
                sensor, {}
            ).get("unit", "")
        )

    df["unit"] = df["unit"].fillna("").astype(str)

    df["forecast_origin"] = pd.to_datetime(
        df["forecast_origin"],
        utc=True,
        errors="coerce",
    )

    df["forecast_timestamp"] = pd.to_datetime(
        df["forecast_timestamp"],
        utc=True,
        errors="coerce",
    )

    df["horizon_minutes"] = pd.to_numeric(
        df["horizon_minutes"],
        errors="coerce",
    )

    df["predicted_value"] = pd.to_numeric(
        df["predicted_value"],
        errors="coerce",
    )

    # Convert all non-finite numeric values to NaN.
    # This includes NaN, +Infinity and -Infinity.
    df["predicted_value"] = df["predicted_value"].where(
        df["predicted_value"].map(
            lambda value: (
                pd.notna(value)
                and math.isfinite(float(value))
            )
        ),
        other=float("nan"),
    )

    # The legacy temperature field is optional.
    # It is only populated for temperature forecasts.
    if "predicted_temperature_c" in df.columns:
        df["predicted_temperature_c"] = pd.to_numeric(
            df["predicted_temperature_c"],
            errors="coerce",
        )

        df["predicted_temperature_c"] = (
            df["predicted_temperature_c"].where(
                df["predicted_temperature_c"].map(
                    lambda value: (
                        pd.notna(value)
                        and math.isfinite(float(value))
                    )
                ),
                other=float("nan"),
            )
        )

    invalid = (
        df["room_id"].eq("")
        | df["forecast_origin"].isna()
        | df["forecast_timestamp"].isna()
        | df["horizon_minutes"].isna()
        | df["predicted_value"].isna()
        | ~df["sensor_type"].isin(SENSOR_CONFIG)
    )

    if invalid.any():
        invalid_count = int(invalid.sum())

        # Invalid forecast records cannot be returned by the API.
        # They are excluded instead of causing JSON serialization errors.
        df = df.loc[~invalid].copy()

    if df.empty:
        return df

    df["horizon_minutes"] = df["horizon_minutes"].astype(int)

    return df


def _get_data_age_hours(forecast_origin: Any) -> float:
    """Calculate the age of forecast input data in hours."""

    origin = _safe_datetime(forecast_origin)

    if origin is None:
        return 0.0

    now = datetime.now(timezone.utc)

    age_hours = (now - origin).total_seconds() / 3600

    return round(max(age_hours, 0.0), 2)


def _add_freshness_information(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add freshness information and sanitize API records."""

    for record in records:

        # Ensure all numeric fields are JSON-compatible.
        for field in (
            "predicted_value",
            "predicted_temperature_c",
            "horizon_minutes",
        ):
            if field in record:
                safe_value = _safe_float(record[field])

                if field == "horizon_minutes" and safe_value is not None:
                    record[field] = int(safe_value)
                else:
                    record[field] = safe_value

        # Normalize timestamps.
        for field in (
            "forecast_origin",
            "forecast_timestamp",
        ):
            if field in record:
                record[field] = _safe_datetime(record[field])

        # Remove the temperature-specific compatibility field
        # for all sensors except temperature.
        if record.get("sensor_type") != "temperature":
            record.pop("predicted_temperature_c", None)

        age_hours = _get_data_age_hours(
            record["forecast_origin"]
        )

        is_stale = age_hours > MAX_FORECAST_AGE_HOURS

        record["data_age_hours"] = age_hours
        record["is_stale"] = is_stale
        record["status"] = "stale" if is_stale else "available"
        record["comment"] = STALE_COMMENT if is_stale else None

        sensor_type = record.get("sensor_type", "temperature")

        record["sensor_label"] = SENSOR_CONFIG.get(
            sensor_type, {}
        ).get("label", sensor_type)

    return records


def _latest_generation(
    group: pd.DataFrame,
) -> pd.DataFrame:
    """Return only records from the latest forecast generation."""

    latest_origin = group["forecast_origin"].max()

    return group[
        group["forecast_origin"] == latest_origin
    ].copy()


def get_forecast_rooms() -> list[dict[str, Any]]:
    """Return all known rooms, including rooms without forecasts."""

    rooms = get_all_rooms()
    df = load_forecasts()

    forecasts_by_room = {}

    if not df.empty:
        for room_id, group in df.groupby("room_id"):
            forecasts_by_room[room_id.upper()] = _latest_generation(group)

    result = []

    for room in rooms:
        room_id = room["room_id"]
        group = forecasts_by_room.get(room_id.upper())

        if group is None or group.empty:
            result.append({
                "room_id": room_id,
                "forecast_count": 0,
                "available_horizons": [],
                "available_sensors": [],
                "latest_forecast": None,
                "latest_created_at": None,
                "data_age_hours": None,
                "is_stale": None,
                "status": "no_forecast",
                "comment": NO_FORECAST_COMMENT,
            })
            continue

        latest_origin = group["forecast_origin"].max()
        latest_timestamp = group["forecast_timestamp"].max()

        age_hours = _get_data_age_hours(latest_origin)
        is_stale = age_hours > MAX_FORECAST_AGE_HOURS

        result.append({
            "room_id": room_id,
            "forecast_count": int(len(group)),
            "available_horizons": sorted(
                int(value)
                for value in group["horizon_minutes"].unique()
            ),
            "available_sensors": sorted(
                group["sensor_type"].unique().tolist()
            ),
            "latest_forecast": _safe_datetime(latest_timestamp),
            "latest_created_at": _safe_datetime(latest_origin),
            "data_age_hours": age_hours,
            "is_stale": is_stale,
            "status": "stale" if is_stale else "available",
            "comment": STALE_COMMENT if is_stale else None,
        })

    return result


def get_room_forecasts(
    room_id: str,
    limit: int = 100,
    sensor_type: str | None = None,
    horizon_minutes: int | None = None,
) -> list[dict[str, Any]]:
    """Return forecasts for one room with optional sensor and horizon filters."""

    df = load_forecasts()

    if df.empty:
        return []

    normalized_room_id = room_id.strip().upper()

    result = df[
        df["room_id"].str.upper() == normalized_room_id
    ].copy()

    if sensor_type:
        normalized_sensor = sensor_type.strip().lower()

        if normalized_sensor not in SENSOR_CONFIG:
            raise ValueError(
                f"Unsupported sensor type: {sensor_type}"
            )

        result = result[
            result["sensor_type"] == normalized_sensor
        ]

    if horizon_minutes is not None:
        result = result[
            result["horizon_minutes"] == horizon_minutes
        ]

    if result.empty:
        return []

    result = result.sort_values(
        ["forecast_timestamp", "sensor_type", "horizon_minutes"],
        ascending=[False, True, True],
    ).head(max(1, limit))

    records = result.to_dict(orient="records")

    return _add_freshness_information(records)


def get_room_forecast_summary(
    room_id: str,
    sensor_type: str = "temperature",
) -> dict[str, Any] | None:
    """Return statistics for the latest forecast generation of one room and sensor."""

    normalized_room_id = room_id.strip().upper()
    normalized_sensor = sensor_type.strip().lower()

    if normalized_sensor not in SENSOR_CONFIG:
        raise ValueError(
            f"Unsupported sensor type: {sensor_type}"
        )

    df = load_forecasts()

    if df.empty:
        return None

    result = df[
        (df["room_id"].str.upper() == normalized_room_id)
        & (df["sensor_type"] == normalized_sensor)
    ].copy()

    if result.empty:
        return None

    latest = _latest_generation(result)

    # Keep only finite forecast values for the statistics.
    values = [
        value
        for value in (
            _safe_float(item)
            for item in latest["predicted_value"].tolist()
        )
        if value is not None
    ]

    if not values:
        return None

    latest_origin = latest["forecast_origin"].max()
    latest_timestamp = latest["forecast_timestamp"].max()

    age_hours = _get_data_age_hours(latest_origin)
    is_stale = age_hours > MAX_FORECAST_AGE_HOURS

    sensor_config = SENSOR_CONFIG[normalized_sensor]

    return {
        "room_id": normalized_room_id,
        "sensor_type": normalized_sensor,
        "sensor_label": sensor_config["label"],
        "unit": str(latest["unit"].iloc[0]),
        "forecast_count": len(values),
        "average_value": _safe_float(
            sum(values) / len(values)
        ),
        "minimum_value": _safe_float(min(values)),
        "maximum_value": _safe_float(max(values)),
        "first_forecast": _safe_datetime(
            latest["forecast_timestamp"].min()
        ),
        "latest_forecast": _safe_datetime(latest_timestamp),
        "latest_created_at": _safe_datetime(latest_origin),
        "data_age_hours": age_hours,
        "is_stale": is_stale,
        "status": "stale" if is_stale else "available",
        "comment": STALE_COMMENT if is_stale else None,
    }
