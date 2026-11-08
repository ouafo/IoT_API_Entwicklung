"""Pydantic models for weather forecasts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WeatherForecastResponse(BaseModel):
    """A single weather forecast."""

    model_config = ConfigDict(populate_by_name=True)

    BuildingID: str
    SensorTypeCode: str
    ForecastOrigin: datetime
    ForecastDateTime: datetime
    HorizonMinutes: int
    PredictedValue: float
    MeasureUnitCode: Optional[str] = None
    #ModelType: Optional[str] = None
    DataAgeHours: float
    IsStale: bool
    Status: str


class WeatherForecastStationResponse(BaseModel):
    """Forecast availability for one weather station."""

    BuildingID: str
    ForecastCount: int
    LatestForecastOrigin: datetime
    DataAgeHours: float
    IsStale: bool
    Status: str