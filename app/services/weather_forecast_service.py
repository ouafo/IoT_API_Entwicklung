"""Service for on-demand 7-day-ahead weather station forecasting."""

from typing import Any
from starlette.concurrency import run_in_threadpool

from app.services.forecast_engine import (
    HISTORY_WINDOW_SIZE,
    WEATHER_SENSORS,
    generate_weather_forecast,
    list_weather_buildings,
)


async def get_weather_forecast_stations() -> list[dict[str, Any]]:
    buildings = await run_in_threadpool(list_weather_buildings)
    return [
        {
            "BuildingID": b,
            "AvailableSensors": list(WEATHER_SENSORS.keys()),
            "Status": "available",
        }
        for b in buildings
    ]


async def get_weather_forecasts(
    building_id: str,
    sensor_type: str = "temperature",
    limit: int = HISTORY_WINDOW_SIZE,
) -> dict[str, Any]:
    data = await run_in_threadpool(
        generate_weather_forecast,
        building_id,
        sensor_type,
        limit,
    )
    return {
        "BuildingID": data["building"],
        "SensorTypeCode": data["sensor_type"],
        "MeasureUnitCode": data["unit"],
        "ForecastOrigin": data["forecast_origin"],
        "TargetWeekday": data["target_weekday"],
        "HorizonDays": 7,
        "ModelType": "DampedTrend(n=15)",
        "HistoryCount": len(data["history"]),
        "ForecastCount": len(data["forecast"]),
        "History": data["history"],
        "Forecast": data["forecast"],
    }