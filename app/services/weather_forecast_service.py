"""Service for reading and preparing weather forecasts."""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FORECAST_FILE = (
    PROJECT_ROOT
    / "forecasting"
    / "weather"
    / "results"
    / "forecasts.csv"
)

MAX_DATA_AGE_HOURS = 24


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO datetime and ensure that it is timezone-aware."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def _load_forecasts() -> list[dict[str, Any]]:
    """Load forecasts from the generated CSV file."""

    if not FORECAST_FILE.exists():
        raise FileNotFoundError(
            f"Weather forecast file not found: {FORECAST_FILE}"
        )

    forecasts = []

    with FORECAST_FILE.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "building",
            "sensor_type",
            "forecast_origin",
            "forecast_timestamp",
            "horizon_minutes",
            "predicted_value",
        }

        available_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - available_columns

        if missing_columns:
            raise ValueError(
                "Weather forecast CSV is missing columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            try:
                forecast_origin = _parse_datetime(
                    row["forecast_origin"]
                )

                forecast_timestamp = _parse_datetime(
                    row["forecast_timestamp"]
                )

                now = datetime.now(timezone.utc)

                data_age_hours = (
                    now - forecast_origin.astimezone(timezone.utc)
                ).total_seconds() / 3600

                is_stale = data_age_hours > MAX_DATA_AGE_HOURS

                forecasts.append(
                    {
                        "BuildingID": row["building"],
                        "SensorTypeCode": row["sensor_type"],
                        "ForecastOrigin": forecast_origin,
                        "ForecastDateTime": forecast_timestamp,
                        "HorizonMinutes": int(row["horizon_minutes"]),
                        "PredictedValue": float(row["predicted_value"]),
                        "MeasureUnitCode": row.get("unit") or None,
                        
                        "DataAgeHours": round(data_age_hours, 2),
                        "IsStale": is_stale,
                        "Status": "stale" if is_stale else "current",
                    }
                )

            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(
                    f"Invalid row in weather forecast CSV: {row}"
                ) from exc

    return forecasts


def get_weather_forecast_stations() -> list[dict[str, Any]]:
    """Return all buildings with available weather forecasts."""

    forecasts = _load_forecasts()

    grouped: dict[str, list[dict[str, Any]]] = {}

    for forecast in forecasts:
        building = forecast["BuildingID"]
        grouped.setdefault(building, []).append(forecast)

    stations = []

    for building, building_forecasts in grouped.items():
        latest_origin = max(
            forecast["ForecastOrigin"]
            for forecast in building_forecasts
        )

        latest_forecasts = [
            forecast
            for forecast in building_forecasts
            if forecast["ForecastOrigin"] == latest_origin
        ]

        latest_age = latest_forecasts[0]["DataAgeHours"]
        is_stale = latest_age > MAX_DATA_AGE_HOURS

        stations.append(
            {
                "BuildingID": building,
                "ForecastCount": len(building_forecasts),
                "LatestForecastOrigin": latest_origin,
                "DataAgeHours": latest_age,
                "IsStale": is_stale,
                "Status": "stale" if is_stale else "current",
            }
        )

    return sorted(stations, key=lambda item: item["BuildingID"])


def get_weather_forecasts(
    building_id: str,
    sensor_type: Optional[str] = None,
    horizon_minutes: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Return forecasts for one building."""

    forecasts = _load_forecasts()

    result = [
        forecast
        for forecast in forecasts
        if forecast["BuildingID"].casefold() == building_id.casefold()
    ]

    if sensor_type:
        result = [
            forecast
            for forecast in result
            if forecast["SensorTypeCode"].casefold()
            == sensor_type.casefold()
        ]

    if horizon_minutes is not None:
        result = [
            forecast
            for forecast in result
            if forecast["HorizonMinutes"] == horizon_minutes
        ]

    return sorted(
        result,
        key=lambda item: (
            item["ForecastDateTime"],
            item["SensorTypeCode"],
            item["HorizonMinutes"],
        ),
    )


def get_latest_weather_forecasts(
    building_id: str,
    sensor_type: Optional[str] = None,
    horizon_minutes: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Return forecasts from the most recent forecast run for a building."""

    forecasts = get_weather_forecasts(
        building_id=building_id,
        sensor_type=sensor_type,
        horizon_minutes=horizon_minutes,
    )

    if not forecasts:
        return []

    latest_origin = max(
        forecast["ForecastOrigin"]
        for forecast in forecasts
    )

    return [
        forecast
        for forecast in forecasts
        if forecast["ForecastOrigin"] == latest_origin
    ]