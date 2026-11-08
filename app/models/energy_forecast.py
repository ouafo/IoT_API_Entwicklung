
"""Pydantic response models for energy forecasting."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EnergyForecastResponse(BaseModel):
    building: str = Field(
        description="Building identifier."
    )

    room_id: str = Field(
        description="Combined building and room identifier."
    )

    forecast_origin: datetime = Field(
        description="Latest input timestamp used to generate the forecast."
    )

    forecast_timestamp: datetime = Field(
        description="Target timestamp of the predicted energy consumption."
    )

    horizon_minutes: int = Field(
        description="Forecast horizon in minutes."
    )

    predicted_consumption_kwh: float = Field(
        description="Predicted energy consumption in kilowatt-hours."
    )

    model_type: str = Field(
        description="Machine learning model used for the prediction."
    )

    data_age_hours: Optional[float] = Field(
        default=None,
        description="Age of the input data in hours."
    )

    is_stale: Optional[bool] = Field(
        default=None,
        description="Whether the input data are older than the freshness threshold."
    )

    status: Optional[str] = Field(
        default=None,
        description="Forecast status: available or stale."
    )

    comment: Optional[str] = Field(
        default=None,
        description="Additional information about the forecast."
    )


class EnergyRoomResponse(BaseModel):
    building: str = Field(
        description="Building identifier."
    )

    room_id: str = Field(
        description="Combined building and room identifier."
    )

    available_horizons: list[int] = Field(
        default_factory=list,
        description="Available forecast horizons in minutes."
    )

    forecast_count: int = Field(
        description="Number of forecasts in the latest forecast generation."
    )

    latest_forecast_timestamp: Optional[datetime] = Field(
        default=None,
        description="Target timestamp of the latest forecast."
    )

    latest_forecast_origin: Optional[datetime] = Field(
        default=None,
        description="Latest input timestamp used to generate a forecast."
    )

    data_age_hours: Optional[float] = Field(
        default=None,
        description="Age of the latest forecast input data in hours."
    )

    is_stale: Optional[bool] = Field(
        default=None,
        description="Whether the latest forecast input data are stale."
    )

    status: str = Field(
        description="Forecast status: available, stale or no_forecast."
    )

    comment: Optional[str] = Field(
        default=None,
        description="Additional information, particularly when no forecast exists."
    )
