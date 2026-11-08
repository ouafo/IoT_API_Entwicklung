
"""Pydantic response models for room climate forecasting."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ForecastRoomItem(BaseModel):
    room_id: str = Field(
        description="Unique room identifier, including building ID."
    )

    forecast_count: int = Field(
        description="Number of records in the latest forecast generation."
    )

    available_horizons: list[int] = Field(
        default_factory=list,
        description="Available forecast horizons in minutes."
    )

    available_sensors: list[str] = Field(
        default_factory=list,
        description=(
            "Available forecast sensor types, e.g. temperature, "
            "humidity, co2 and light."
        )
    )

    latest_forecast: Optional[datetime] = Field(
        default=None,
        description="Latest target timestamp of the forecast."
    )

    latest_created_at: Optional[datetime] = Field(
        default=None,
        description="Latest input timestamp used to generate the forecast."
    )

    data_age_hours: Optional[float] = Field(
        default=None,
        description="Age of the forecast input data in hours."
    )

    is_stale: Optional[bool] = Field(
        default=None,
        description="Whether the forecast input data are older than 24 hours."
    )

    status: str = Field(
        description="Forecast status: available, stale or no_forecast."
    )

    comment: Optional[str] = Field(
        default=None,
        description="Additional information about forecast availability."
    )


class ForecastRoomsResponse(BaseModel):
    count: int = Field(
        description="Number of rooms returned."
    )

    value: list[ForecastRoomItem] = Field(
        description="All known rooms and their forecast status."
    )


class ForecastItem(BaseModel):
    room_id: str = Field(
        description="Unique room identifier."
    )

    sensor_type: str = Field(
        description=(
            "Sensor type: temperature, humidity, co2 or light."
        )
    )

    sensor_label: Optional[str] = Field(
        default=None,
        description="Human-readable sensor name."
    )

    forecast_origin: datetime = Field(
        description="Latest input timestamp used to generate the forecast."
    )

    forecast_timestamp: datetime = Field(
        description="Target timestamp of the predicted sensor value."
    )

    horizon_minutes: int = Field(
        description="Forecast horizon in minutes."
    )

    predicted_value: float = Field(
        description="Predicted value of the selected sensor."
    )

    unit: str = Field(
        description="Unit of the predicted sensor value."
    )

    model_type: str = Field(
        description="Model used to generate the prediction."
    )

    data_age_hours: Optional[float] = Field(
        default=None,
        description="Age of the forecast input data in hours."
    )

    is_stale: Optional[bool] = Field(
        default=None,
        description="Whether the forecast input data are older than 24 hours."
    )

    status: Optional[str] = Field(
        default=None,
        description="Forecast status: available or stale."
    )

    comment: Optional[str] = Field(
        default=None,
        description="Additional information about the forecast."
    )


class TemperatureForecastItem(ForecastItem):
    """Forecast response model for temperature predictions."""

    predicted_temperature_c: Optional[float] = Field(
        default=None,
        description=(
            "Legacy temperature prediction field. "
            "Only available for temperature forecasts."
        )
    )


class RoomForecastsResponse(BaseModel):
    count: int = Field(
        description="Number of forecast records returned."
    )

    RoomID: str = Field(
        description="Requested room identifier."
    )

    value: list[ForecastItem] = Field(
        description="Forecast records for the selected room."
    )


class RoomForecastSummary(BaseModel):
    room_id: str = Field(
        description="Unique room identifier."
    )

    sensor_type: str = Field(
        description="Selected sensor type."
    )

    sensor_label: Optional[str] = Field(
        default=None,
        description="Human-readable sensor name."
    )

    unit: str = Field(
        description="Unit of the selected sensor."
    )

    forecast_count: int = Field(
        description="Number of forecast records in the latest generation."
    )

    average_value: Optional[float] = Field(
        default=None,
        description="Average predicted sensor value."
    )

    minimum_value: Optional[float] = Field(
        default=None,
        description="Minimum predicted sensor value."
    )

    maximum_value: Optional[float] = Field(
        default=None,
        description="Maximum predicted sensor value."
    )

    first_forecast: Optional[datetime] = Field(
        default=None,
        description="Earliest target timestamp in the latest generation."
    )

    latest_forecast: Optional[datetime] = Field(
        default=None,
        description="Latest target timestamp in the latest generation."
    )

    latest_created_at: Optional[datetime] = Field(
        default=None,
        description="Latest input timestamp used to generate the forecast."
    )

    data_age_hours: Optional[float] = Field(
        default=None,
        description="Age of the forecast input data in hours."
    )

    is_stale: Optional[bool] = Field(
        default=None,
        description="Whether the forecast input data are older than 24 hours."
    )

    status: str = Field(
        description="Forecast status: available or stale."
    )
