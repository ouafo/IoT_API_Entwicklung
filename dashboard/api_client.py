from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from config import (
    API_BASE_URL,
    API_USERNAME,
    API_PASSWORD,
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
                API_PASSWORD
            )

        self.session.headers.update({
            "Accept": "application/json"
        })

    def get(
        self,
        endpoint: str,
        params: Optional[dict] = None
    ) -> Any:
        """GET-Anfrage an die FastAPI senden."""

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else "unbekannt"
            )

            raise RuntimeError(
                f"API-Fehler ({status_code}) bei {endpoint}: "
                f"{exc}"
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
    # SYSTEM
    # ---------------------------------------------------------

    def health_check(self):
        return self.get("/api/health")

    # ---------------------------------------------------------
    # WEATHER FORECASTS
    # ---------------------------------------------------------

    def get_weather_stations(self):
        return self.get("/api/Forecasts/Weather/Stations")

    def get_latest_weather_forecasts(
        self,
        building_id: str,
        sensor_type: Optional[str] = None,
        horizon_minutes: Optional[int] = None
    ):
        params = {}

        if sensor_type:
            params["SensorTypeCode"] = sensor_type

        if horizon_minutes:
            params["HorizonMinutes"] = horizon_minutes

        return self.get(
            f"/api/Forecasts/Weather/{building_id}/Latest",
            params=params or None
        )

    def get_weather_forecasts(
        self,
        building_id: str,
        sensor_type: Optional[str] = None,
        horizon_minutes: Optional[int] = None
    ):
        params = {}

        if sensor_type:
            params["SensorTypeCode"] = sensor_type

        if horizon_minutes:
            params["HorizonMinutes"] = horizon_minutes

        return self.get(
            f"/api/Forecasts/Weather/{building_id}",
            params=params or None
        )

    def get_weather_measurements(
        self,
        building_id: str,
        start_datetime: str,
        end_datetime: str,
        sensor_type: Optional[str] = None,
        limit: int = 10000
    ):
        params = {
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
            params=params
        )

    # ---------------------------------------------------------
    # ROOM CLIMATE FORECASTS
    # ---------------------------------------------------------

    def get_rooms_with_forecasts(self):
        return self.get("/api/Forecasts/Rooms")

    def get_room_forecasts(
        self,
        room_id: str,
        limit: int = 1000
    ):
        return self.get(
            f"/api/Forecasts/Rooms/{room_id}",
            params={"limit": limit}
        )

    def get_latest_room_forecast(self, room_id: str):
        return self.get(
            f"/api/Forecasts/Rooms/{room_id}/Latest"
        )

    def get_room_forecast_summary(self, room_id: str):
        return self.get(
            f"/api/Forecasts/Rooms/{room_id}/Summary"
        )

    # ---------------------------------------------------------
    # ENERGY FORECASTS
    # ---------------------------------------------------------

    def get_energy_rooms(self):
        return self.get("/api/Forecasts/Energy/Rooms")

    def get_latest_energy_forecasts(self, room_id: str):
        return self.get(
            f"/api/Forecasts/Energy/Rooms/{room_id}/Latest"
        )

    def get_energy_forecasts(self, room_id: str):
        return self.get(
            f"/api/Forecasts/Energy/Rooms/{room_id}"
        )

    # ---------------------------------------------------------
    # HISTORICAL ROOM MEASUREMENTS
    # ---------------------------------------------------------

    def get_room_measurements(
        self,
        room_id: str,
        start_datetime: str,
        end_datetime: str,
        sensor_type: Optional[str] = None,
        limit: int = 10000
    ):
        params = {
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
            params=params
        )


api = APIClient()