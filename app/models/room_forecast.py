"""Pydantic response models for room climate forecasting."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SeriesPoint(BaseModel):
    timestamp: datetime = Field(description="Timestamp of measurement or forecast.")
    value: float = Field(description="Measured or predicted sensor value.")


class RoomAttributes(BaseModel):
    capacity: int = Field(default=40, description="Room seating capacity.")
    area: float = Field(default=100.0, description="Room floor area in m².")
    window_count: int = Field(default=4, description="Number of windows in the room.")


class ForecastRoomItem(BaseModel):
    building: str
    room_id: str
    full_room_id: str
    capacity: int
    area: float
    window_count: int
    available_sensors: list[str]
    status: str = "available"


class ForecastRoomsResponse(BaseModel):
    count: int
    value: list[ForecastRoomItem]


class RoomForecastSeriesResponse(BaseModel):
    building: str
    room_id: str
    full_room_id: str
    sensor_type: str
    sensor_label: str
    unit: str
    room_attributes: RoomAttributes
    forecast_origin: Optional[datetime] = None
    target_weekday: Optional[str] = None
    horizon_days: int = 7
    model_type: str = "DampedTrend+RoomPhysics(n=15)"
    history_count: int
    forecast_count: int
    history: list[SeriesPoint]
    forecast: list[SeriesPoint]


class RoomForecastSummary(BaseModel):
    building: str
    room_id: str
    full_room_id: str
    sensor_type: str
    sensor_label: str
    unit: str
    forecast_origin: Optional[datetime] = None
    target_weekday: Optional[str] = None
    history_average: Optional[float] = None
    forecast_average: Optional[float] = None
    forecast_minimum: Optional[float] = None
    forecast_maximum: Optional[float] = None
    status: str