"""Application configuration."""

from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    """App Settings aus Environment Variables."""
    
    # Database
    DB_HOST: str = os.getenv("DB_HOST", "iwilsv-1.campus.fh-ludwigshafen.de")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os. getenv("DB_NAME", "kicagem_db")
    DB_USER: str = os.getenv("DB_USER", "ba_thesis")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "pw_ba_thesis")
    DB_SCHEMA: str = os.getenv("DB_SCHEMA", "public") 
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "1"))
    DB_POOL_MAX: int = int(os. getenv("DB_POOL_MAX", "10"))

    # API
    API_TITLE: str = os.getenv("API_TITLE", "KICAGEM IoT Analytics Service")
    API_VERSION: str = os.getenv("API_VERSION", "1.0.0")
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")
    
    # Auth
    BASIC_AUTH_USERNAME: str = os.getenv("BASIC_AUTH_USERNAME", "admin")
    BASIC_AUTH_PASSWORD: str = os.getenv("BASIC_AUTH_PASSWORD", "98558979c")
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", "1000"))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", "10000"))
    
    # Sensor Mapping - nicht hart-codiert!
    SENSOR_MAPPINGS = {
    "temperature": {
        "table": "room_climate",
        "value_column": "temperature",
        "unit_column": "temperature_unit",
        "default_unit": "°C",
    },
    "humidity": {
        "table":  "room_climate",
        "value_column": "humidity",
        "unit_column": "humidity_unit",
        "default_unit": "%%",  # ← GEÄNDERT: %% statt %
    },
    "co2": {
        "table":  "room_climate",
        "value_column": "co2",
        "unit_column": "co2_unit",
        "default_unit": "ppm",
    },
    "light": {
        "table": "room_climate",
        "value_column": "light_mean",
        "unit_column":  "light_unit",
        "default_unit": "lux",
    },
    "motion": {
        "table": "room_climate",
        "value_column": "motion",
        "unit_column": "motion_unit",
        "default_unit": "movements",
    },
    "power": {
        "table": "energy",
        "value_column": "Wirkleistung_L123_sum",
        "unit_column":  "Wirkleistung_unit",
        "default_unit":  "W",
    },
    "energy_import": {
        "table": "energy",
        "value_column": "Wirkenergie_Import_L123_T1",
        "unit_column":  "Wirkenergie_unit",
        "default_unit":  "kWh",
    },
}

settings = Settings()