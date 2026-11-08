
"""Service for reading energy forecasts and the complete room catalogue."""

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
    / "energy"
    / "results"
    / "forecasts.csv"
)

MAX_FORECAST_AGE_HOURS = 24

NO_FORECAST_COMMENT = (
    "Keine Prognose vorhanden. Datenlage für das Training prüfen."
)

STALE_COMMENT = (
    "Prognose basiert auf Eingangsdaten, die älter als 24 Stunden sind."
)


def get_all_rooms() -> list[dict[str, str]]:
    """Read all known building-room combinations from the database."""

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
                    "building": str(row["building"]).strip(),
                    "room_id": (
                        f'{str(row["building"]).strip()}-'
                        f'{str(row["room_location"]).strip()}'
                    ),
                }
                for row in rows
            ]

    finally:
        connection.put_conn(conn)


def load_forecasts() -> pd.DataFrame:
    """Load and validate energy forecasts from the CSV file."""

    if not FORECAST_FILE.exists():
        raise FileNotFoundError(
            f"Forecast-Datei nicht gefunden: {FORECAST_FILE}"
        )

    df = pd.read_csv(FORECAST_FILE)

    if df.empty:
        return df

    if "forecast_origin" not in df.columns:
        if "forecast_created_at" in df.columns:
            df = df.rename(
                columns={"forecast_created_at": "forecast_origin"}
            )
        else:
            raise ValueError("Spalte 'forecast_origin' fehlt.")

    required = {
        "building",
        "room",
        "forecast_origin",
        "forecast_timestamp",
        "horizon_minutes",
        "predicted_consumption_kwh",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Fehlende Forecast-Spalten: {sorted(missing)}"
        )

    df = df.copy()

    df["building"] = df["building"].astype(str).str.strip()
    df["room"] = df["room"].astype(str).str.strip()

    if "model_type" not in df.columns:
        df["model_type"] = "unknown"

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

    df["predicted_consumption_kwh"] = pd.to_numeric(
        df["predicted_consumption_kwh"],
        errors="coerce",
    )

    invalid = (
        df["building"].eq("")
        | df["room"].eq("")
        | df["forecast_origin"].isna()
        | df["forecast_timestamp"].isna()
        | df["horizon_minutes"].isna()
        | df["predicted_consumption_kwh"].isna()
    )

    if invalid.any():
        raise ValueError(
            f"Die Forecast-Datei enthält {int(invalid.sum())} "
            "ungültige Datensätze."
        )

    df["horizon_minutes"] = df["horizon_minutes"].astype(int)

    df["room_id"] = df["building"] + "-" + df["room"]

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
    """Add freshness status and comments to forecast records."""

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


def get_energy_rooms() -> list[dict[str, Any]]:
    """Return all known rooms, including rooms without forecasts."""

    rooms = get_all_rooms()
    df = load_forecasts()

    forecasts_by_room = {}

    if not df.empty:
        for room_id, group in df.groupby("room_id"):
            forecasts_by_room[room_id.upper()] = group

    result = []

    for room in rooms:
        room_id = room["room_id"]
        group = forecasts_by_room.get(room_id.upper())

        if group is None or group.empty:
            result.append({
                "building": room["building"],
                "room_id": room_id,
                "available_horizons": [],
                "forecast_count": 0,
                "latest_forecast_timestamp": None,
                "latest_forecast_origin": None,
                "data_age_hours": None,
                "is_stale": None,
                "status": "no_forecast",
                "comment": NO_FORECAST_COMMENT,
            })
            continue

        latest_origin = group["forecast_origin"].max()

        # Only describe the latest forecast generation.
        latest_generation = group[
            group["forecast_origin"] == latest_origin
        ]

        latest_timestamp = latest_generation[
            "forecast_timestamp"
        ].max()

        age_hours = _get_data_age_hours(latest_origin)
        is_stale = age_hours > MAX_FORECAST_AGE_HOURS

        result.append({
            "building": room["building"],
            "room_id": room_id,
            "available_horizons": sorted(
                latest_generation["horizon_minutes"].unique().tolist()
            ),
            "forecast_count": int(len(latest_generation)),
            "latest_forecast_timestamp": latest_timestamp,
            "latest_forecast_origin": latest_origin,
            "data_age_hours": age_hours,
            "is_stale": is_stale,
            "status": "stale" if is_stale else "available",
            "comment": STALE_COMMENT if is_stale else None,
        })

    return result


def get_room_energy_forecasts(
    room_id: str,
) -> list[dict[str, Any]]:
    """Return all energy forecasts for one room."""

    df = load_forecasts()

    if df.empty:
        return []

    normalized_room_id = room_id.strip().upper()

    result = df[
        df["room_id"].str.upper() == normalized_room_id
    ]

    # Also allow lookup by room number only.
    if result.empty:
        result = df[
            df["room"].str.upper() == normalized_room_id
        ]

    if result.empty:
        return []

    result = result.sort_values(
        ["forecast_origin", "horizon_minutes"],
        ascending=[False, True],
    )

    records = result.to_dict(orient="records")

    return _add_freshness_information(records)


def get_latest_energy_forecasts(
    room_id: str,
) -> list[dict[str, Any]]:
    """Return forecasts belonging to the latest forecast generation."""

    forecasts = get_room_energy_forecasts(room_id)

    if not forecasts:
        return []

    latest_origin = max(
        item["forecast_origin"] for item in forecasts
    )

    return [
        item
        for item in forecasts
        if item["forecast_origin"] == latest_origin
    ]
