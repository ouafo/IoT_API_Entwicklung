"""Measurement data models using Pydantic."""

from pydantic import BaseModel, Field
from typing import List, Optional


class Measurement(BaseModel):
    RoomID: str
    BuildingID: str
    SensorTypeCode: str
    StartDateTime: str
    EndDateTime: str
    MeasureContent: float
    MeasureUnitCode: str


class Room(BaseModel):
    RoomID: str
    BuildingID: str
    RoomLocation: Optional[str] = None
    ApplicationName: Optional[str] = None

    room_type: Optional[str] = None
    capacity: Optional[int] = Field(default=40)
    area: Optional[float] = Field(default=100.0)
    window_count: Optional[int] = Field(default=4)


class RoomTimeRange(BaseModel):
    RoomID: str
    BuildingID: str
    StartDateTime: str
    EndDateTime: str


class MeasurementResponse(BaseModel):
    odata_context: str = Field(..., alias="@odata.context")
    odata_count: Optional[int] = Field(None, alias="@odata.count")
    odata_nextLink: Optional[str] = Field(None, alias="@odata.nextLink")

    Room: Optional[Room] = None
    value: List[Measurement]

    class Config:
        populate_by_name = True


class RoomResponse(BaseModel):
    odata_context: str = Field(..., alias="@odata.context")
    odata_count: Optional[int] = Field(None, alias="@odata.count")
    odata_nextLink: Optional[str] = Field(None, alias="@odata.nextLink")

    value: List[Room]

    class Config:
        populate_by_name = True