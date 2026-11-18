"""Pydantic response models for weather station forecasting."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class WeatherSeriesPoint(BaseModel):
    timestamp: datetime
    value: float


class WeatherForecastStationResponse(BaseModel):
    BuildingID: str
    AvailableSensors: list[str]
    Status: str = "available"


class WeatherForecastSeriesResponse(BaseModel):
    BuildingID: str
    SensorTypeCode: str
    MeasureUnitCode: str
    ForecastOrigin: Optional[datetime] = None
    TargetWeekday: Optional[str] = None
    HorizonDays: int = 7
    ModelType: str = "DampedTrend(n=15)"
    HistoryCount: int
    ForecastCount: int
    History: list[WeatherSeriesPoint]
    Forecast: list[WeatherSeriesPoint]