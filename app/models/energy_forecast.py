"""Pydantic response models for energy forecasting."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EnergySeriesPoint(BaseModel):
    timestamp: datetime = Field(description="Interval timestamp.")
    value: float = Field(description="Energy consumption in kWh.")


class EnergyRoomAttributes(BaseModel):
    capacity: int = 40
    area: float = 100.0
    window_count: int = 4


class EnergyRoomResponse(BaseModel):
    building: str
    room_id: str
    full_room_id: str
    capacity: int
    area: float
    window_count: int
    status: str = "available"


class EnergyForecastSeriesResponse(BaseModel):
    building: str
    room_id: str
    full_room_id: str
    unit: str = "kWh"
    room_attributes: EnergyRoomAttributes
    forecast_origin: Optional[datetime] = None
    target_weekday: Optional[str] = None
    horizon_days: int = 7
    model_type: str = "DampedTrend+RoomPhysics(n=15)"
    history_count: int
    forecast_count: int
    history: list[EnergySeriesPoint]
    forecast: list[EnergySeriesPoint]