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

class MeasurementResponse(BaseModel):
    odata_context: str = Field(..., alias="@odata.context")
    odata_count: Optional[int] = Field(None, alias="@odata.count")
    odata_nextLink: Optional[str] = Field(None, alias="@odata.nextLink")
    value: List[Measurement]
    class Config:
        populate_by_name = True

class Room(BaseModel):
    RoomID: str
    BuildingID: str
    RoomLocation: Optional[str] = None
    ApplicationName: Optional[str] = None

class RoomResponse(BaseModel):
    odata_context: str = Field(..., alias="@odata.context")
    odata_count: Optional[int] = Field(None, alias="@odata.count")
    odata_nextLink: Optional[str] = Field(None, alias="@odata.nextLink")
    value: List[Room]
    class Config:
        populate_by_name = True