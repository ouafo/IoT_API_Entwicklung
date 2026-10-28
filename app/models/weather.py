
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class WeatherMeasurement(BaseModel):
    BuildingID: str
    SensorTypeCode: str
    StartDateTime: datetime
    EndDateTime: datetime
    MeasureContent: Optional[float] = None
    MeasureUnitCode: Optional[str] = None


class WeatherMeasurementResponse(BaseModel):
    count: Optional[int] = None
    value: List[WeatherMeasurement]

    class Config:
        schema_extra = {
            "example": {
                "count": 1,
                "value": [
                    {
                        "BuildingID": "A",
                        "SensorTypeCode": "temperature",
                        "StartDateTime": "2024-08-01T23:00:00+00:00",
                        "EndDateTime": "2024-08-01T23:15:00+00:00",
                        "MeasureContent": 27.7,
                        "MeasureUnitCode": "celsius"
                    }
                ]
            }
        }
