
"""Service for room climate forecasts.

Room inventory is read from the database.
Forecast values are read exclusively from the current CSV output.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

NO_FORECAST_COMMENT = (
    "Keine Raumklima-Prognose vorhanden. Datenlage für das Training prüfen."
)

STALE_COMMENT = (
    "Prognose basiert auf Eingangsdaten, die älter als 24 Stunden sind."
)


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
    """Load and validate the current room climate forecast CSV."""

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
        "predicted_temperature_c",
        "model_type",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing climate forecast columns: {sorted(missing)}"
        )

    if df.empty:
        return df

    df = df.copy()

    df["room_id"] = df["room_id"].astype(str).str.strip()

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

    df["predicted_temperature_c"] = pd.to_numeric(
        df["predicted_temperature_c"],
        errors="coerce",
    )

    invalid = (
        df["room_id"].eq("")
        | df["forecast_origin"].isna()
        | df["forecast_timestamp"].isna()
        | df["horizon_minutes"].isna()
        | df["predicted_temperature_c"].isna()
    )

    if invalid.any():
        raise ValueError(
            f"Climate forecast CSV contains {int(invalid.sum())} "
            "invalid records."
        )

    df["horizon_minutes"] = df["horizon_minutes"].astype(int)

    return df


def _get_data_age_hours(forecast_origin: Any) -> float:
    """Calculate the age of forecast input data in hours."""

    now = datetime.now(timezone.utc)

    if isinstance(forecast_origin, pd.Timestamp):
        origin = forecast_origin.to_pydatetime()
    else:
        origin = forecast_origin

    if origin.tzinfo is None:
        origin = origin.replace(tzinfo=timezone.utc)

    age_hours = (now - origin).total_seconds() / 3600

    return round(max(age_hours, 0.0), 2)


def _add_freshness_information(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add freshness information to forecast records."""

    for record in records:
        age_hours = _get_data_age_hours(
            record["forecast_origin"]
        )

        is_stale = age_hours > MAX_FORECAST_AGE_HOURS

        record["data_age_hours"] = age_hours
        record["is_stale"] = is_stale
        record["status"] = "stale" if is_stale else "available"
        record["comment"] = STALE_COMMENT if is_stale else None

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
                group["horizon_minutes"].unique().tolist()
            ),
            "latest_forecast": latest_timestamp,
            "latest_created_at": latest_origin,
            "data_age_hours": age_hours,
            "is_stale": is_stale,
            "status": "stale" if is_stale else "available",
            "comment": STALE_COMMENT if is_stale else None,
        })

    return result


def get_room_forecasts(
    room_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return forecasts for one room from the current CSV."""

    df = load_forecasts()

    if df.empty:
        return []

    normalized_room_id = room_id.strip().upper()

    result = df[
        df["room_id"].str.upper() == normalized_room_id
    ].copy()

    if result.empty:
        return []

    result = result.sort_values(
        ["forecast_timestamp", "horizon_minutes"],
        ascending=[False, True],
    ).head(limit)

    records = result.to_dict(orient="records")

    return _add_freshness_information(records)


def get_room_forecast_summary(
    room_id: str,
) -> dict[str, Any] | None:
    """Return statistics for the latest forecast generation of one room."""

    df = load_forecasts()

    if df.empty:
        return None

    normalized_room_id = room_id.strip().upper()

    result = df[
        df["room_id"].str.upper() == normalized_room_id
    ].copy()

    if result.empty:
        return None

    latest = _latest_generation(result)

    latest_origin = latest["forecast_origin"].max()
    age_hours = _get_data_age_hours(latest_origin)
    is_stale = age_hours > MAX_FORECAST_AGE_HOURS

    return {
        "room_id": normalized_room_id,
        "forecast_count": int(len(latest)),
        "average_temperature_c": float(
            latest["predicted_temperature_c"].mean()
        ),
        "minimum_temperature_c": float(
            latest["predicted_temperature_c"].min()
        ),
        "maximum_temperature_c": float(
            latest["predicted_temperature_c"].max()
        ),
        "first_forecast": latest["forecast_timestamp"].min(),
        "latest_forecast": latest["forecast_timestamp"].max(),
        "latest_created_at": latest_origin,
        "data_age_hours": age_hours,
        "is_stale": is_stale,
        "status": "stale" if is_stale else "available",
    }
