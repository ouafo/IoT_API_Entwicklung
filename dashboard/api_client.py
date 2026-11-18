"""Central HTTP client for the KICaGEM FastAPI backend."""

from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from config import (
    API_BASE_URL,
    API_PASSWORD,
    API_USERNAME,
    REQUEST_TIMEOUT,
)


class APIClient:
    """Zentraler Client für die KICaGEM FastAPI."""

    def __init__(self):
        self.base_url = API_BASE_URL
        self.session = requests.Session()

        if API_USERNAME and API_PASSWORD:
            self.session.auth = HTTPBasicAuth(
                API_USERNAME,
                API_PASSWORD,
            )

        self.session.headers.update({
            "Accept": "application/json",
        })

    def get(
        self,
        endpoint: str,
        params: Optional[dict] = None,
    ) -> Any:
        """GET-Anfrage an die FastAPI senden."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else "unbekannt"
            )
            detail = ""
            if exc.response is not None:
                try:
                    detail = f" – {exc.response.json().get('detail', '')}"
                except Exception:
                    pass
            raise RuntimeError(
                f"API-Fehler ({status_code}) bei {endpoint}{detail}"
            ) from exc

        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Keine Verbindung zur API unter {self.base_url}. "
                "Ist der FastAPI-Server gestartet?"
            ) from exc

        except requests.exceptions.Timeout as exc:
            raise RuntimeError(
                f"Zeitüberschreitung bei der Anfrage an {endpoint}."
            ) from exc

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Fehler bei der API-Anfrage: {exc}"
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                f"Die API lieferte keine gültige JSON-Antwort: {endpoint}"
            ) from exc

    # ---------------------------------------------------------
    # SYSTEM & ROOM METADATA
    # ---------------------------------------------------------

    def health_check(self):
        return self.get("/api/health")

    def get_rooms(self):
        return self.get("/api/Rooms")

    def get_room(self, room_id: str):
        return self.get(f"/api/Rooms('{room_id}')")

    def get_room_time_range(
        self,
        room_id: str,
        sensor_type: Optional[str] = None,
    ):
        params = {"SensorTypeCode": sensor_type} if sensor_type else None
        return self.get(f"/api/Rooms('{room_id}')/TimeRange", params=params)

    # ---------------------------------------------------------
    # HISTORICAL ROOM & WEATHER MEASUREMENTS
    # ---------------------------------------------------------

    def get_room_measurements(
        self,
        room_id: str,
        start_datetime: str,
        end_datetime: str,
        sensor_type: Optional[str] = None,
        limit: int = 10000,
    ):
        params: dict[str, Any] = {
            "StartDateTime": start_datetime,
            "EndDateTime": end_datetime,
            "$top": limit,
            "$orderby": "StartDateTime ASC",
            "$count": True,
        }
        if sensor_type:
            params["SensorTypeCode"] = sensor_type

        return self.get(
            f"/api/Rooms('{room_id}')/Measurements",
            params=params,
        )

    def get_weather_measurements(
        self,
        building_id: str,
        start_datetime: str,
        end_datetime: str,
        sensor_type: Optional[str] = None,
        limit: int = 10000,
    ):
        params: dict[str, Any] = {
            "StartDateTime": start_datetime,
            "EndDateTime": end_datetime,
            "$top": limit,
            "$orderby": "StartDateTime ASC",
            "$count": True,
        }
        if sensor_type:
            params["SensorTypeCode"] = sensor_type

        return self.get(
            f"/api/WeatherMeasurements/{building_id}",
            params=params,
        )

    # ---------------------------------------------------------
    # 7-DAY-AHEAD FORECASTS (HISTORY VS. FORECAST SERIES)
    # ---------------------------------------------------------

    def get_rooms_with_forecasts(self):
        return self.get("/api/Forecasts/Rooms")

    def get_room_forecasts(
        self,
        room_id: str,
        sensor_type: str = "temperature",
        limit: int = 15,
        capacity: Optional[int] = None,
        area: Optional[float] = None,
        window_count: Optional[int] = None,
    ):
        params: dict[str, Any] = {
            "sensor_type": sensor_type,
            "limit": limit,
        }
        if capacity is not None:
            params["capacity"] = capacity
        if area is not None:
            params["area"] = area
        if window_count is not None:
            params["window_count"] = window_count

        return self.get(f"/api/Forecasts/Rooms/{room_id}", params=params)

    def get_room_forecast_summary(
        self,
        room_id: str,
        sensor_type: str = "temperature",
        capacity: Optional[int] = None,
        area: Optional[float] = None,
        window_count: Optional[int] = None,
    ):
        params: dict[str, Any] = {"sensor_type": sensor_type}
        if capacity is not None:
            params["capacity"] = capacity
        if area is not None:
            params["area"] = area
        if window_count is not None:
            params["window_count"] = window_count

        return self.get(f"/api/Forecasts/Rooms/{room_id}/Summary", params=params)

    def get_energy_rooms(self):
        return self.get("/api/Forecasts/Energy/Rooms")

    def get_energy_forecasts(
        self,
        room_id: str,
        limit: int = 15,
        capacity: Optional[int] = None,
        area: Optional[float] = None,
        window_count: Optional[int] = None,
    ):
        params: dict[str, Any] = {"limit": limit}
        if capacity is not None:
            params["capacity"] = capacity
        if area is not None:
            params["area"] = area
        if window_count is not None:
            params["window_count"] = window_count

        return self.get(f"/api/Forecasts/Energy/Rooms/{room_id}", params=params)

    def get_weather_stations(self):
        return self.get("/api/Forecasts/Weather/Stations")

    def get_weather_forecasts(
        self,
        building_id: str,
        sensor_type: str = "temperature",
        limit: int = 15,
    ):
        params: dict[str, Any] = {
            "SensorTypeCode": sensor_type,
            "limit": limit,
        }
        return self.get(
            f"/api/Forecasts/Weather/{building_id}",
            params=params,
        )


api = APIClient()