import os
import sys

# Projekt-Root zum Import-Pfad hinzufügen (ermöglicht "import app.*")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv
from app.config import settings
import psycopg

load_dotenv()

def test_connection():
    dsn = {
        "host": settings.DB_HOST,
        "port": int(settings.DB_PORT) if settings.DB_PORT else None,
        "dbname": settings.DB_NAME,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
    }
    try:
        with psycopg.connect(**dsn) as conn:
            with conn.cursor() as cur:
                schema = settings.DB_SCHEMA or "public"
                cur.execute(f"SELECT to_regclass(%s)", (f"{schema}.telemetry",))
                exists = cur.fetchone()[0]
                if not exists:
                    print(f"Tabelle {schema}.telemetry nicht gefunden.")
                    return
                cur.execute(f"SELECT COUNT(*) FROM {schema}.telemetry")
                cnt = cur.fetchone()[0]
                print(f"DB test OK — {schema}.telemetry rows = {cnt}")
    except Exception as e:
        print("DB connection error:", e)

if __name__ == "__main__":
    test_connection()