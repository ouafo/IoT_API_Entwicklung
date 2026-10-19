import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import base64
from app.main import app

def get_auth_header():
    credentials = "admin:98558979c"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}

@pytest.fixture
def client():
    return TestClient(app)

@patch("app.services.measurement_service.get_all_rooms")
def test_rooms_returns_data(mock_get_all, client):
    mock_get_all.return_value = {
        "@odata.context": "...",
        "@odata.count": 2,
        "value": [
            {"RoomID": "A203", "BuildingID": "A", "ApplicationName": "KICAGEM"},
            {"RoomID": "A304", "BuildingID": "A", "ApplicationName": "KICAGEM"}
        ]
    }
    resp = client.get("/api/Rooms", headers=get_auth_header())
    data = resp.json()
    assert isinstance(data["value"], list)
    assert data["value"][0]["RoomID"] == "A203"

@patch("app.database.queries.get_rooms")
def test_get_single_room_ok(mock_get_rooms, client):
    mock_get_rooms.return_value = [
        {"RoomID": "A203", "BuildingID": "A", "ApplicationName": "KICAGEM"}
    ]
    # RoomID format is 'A-A203' (building-room) per route logic
    resp = client.get("/api/Rooms('A-A203')", headers=get_auth_header())
    assert resp.status_code == 200
    data = resp.json()
    assert data["RoomID"] == "A203"

@patch("app.services.measurement_service.get_measurements")
def test_get_measurements_basic(mock_get_measurements, client):
    mock_get_measurements.return_value = {
        "@odata.context": "...",
        "@odata.count": 1,
        "value": [{
            "RoomID": "A203",
            "BuildingID": "A",
            "SensorTypeCode": "temperature",
            "StartDateTime": "2025-01-01T00:00:00Z",
            "EndDateTime": "2025-01-01T00:15:00Z",
            "MeasureContent": 21.1,
            "MeasureUnitCode": "celsius"
        }]
    }
    resp = client.get("/api/Rooms('A-A203')/Measurements?StartDateTime=2025-01-01T00:00:00Z&EndDateTime=2025-01-01T23:59:59Z&SensorTypeCode=temperature&$top=1", headers=get_auth_header())
    data = resp.json()
    assert isinstance(data["value"], list)
    assert len(data["value"]) == 1
    assert data["value"][0]["SensorTypeCode"] == "temperature"

@patch("app.services.measurement_service.get_measurements")
def test_measurements_top_skip(mock_get, client):
    mock_get.return_value = {
        "@odata.context": "...",
        "@odata.count": 2,
        "value": [
            {
                "RoomID": "A203",
                "BuildingID": "A",
                "SensorTypeCode": "temperature",
                "StartDateTime": "2025-01-01T00:00:00Z",
                "EndDateTime": "2025-01-01T00:15:00Z",
                "MeasureContent": 21.1,
                "MeasureUnitCode": "celsius"
            },
            {
                "RoomID": "A203",
                "BuildingID": "A",
                "SensorTypeCode": "humidity",
                "StartDateTime": "2025-01-01T00:15:00Z",
                "EndDateTime": "2025-01-01T00:30:00Z",
                "MeasureContent": 38,
                "MeasureUnitCode": "percent"
            }
        ]
    }
    resp = client.get("/api/Rooms('A-A203')/Measurements?StartDateTime=2025-01-01T00:00:00Z&EndDateTime=2025-01-01T23:59:59Z&$top=2&$skip=0", headers=get_auth_header())
    data = resp.json()
    assert isinstance(data["value"], list)
    assert len(data["value"]) == 2