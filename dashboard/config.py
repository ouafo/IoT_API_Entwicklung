import os
from pathlib import Path

from dotenv import load_dotenv


DASHBOARD_DIR = Path(__file__).resolve().parent

load_dotenv(DASHBOARD_DIR / ".env")

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

API_USERNAME = os.getenv("API_USERNAME", "admin")
API_PASSWORD = os.getenv("API_PASSWORD", "98558979c")

REQUEST_TIMEOUT = 40

DASHBOARD_TITLE = "KICaGEM Analytics"
DASHBOARD_ICON = "🏢"