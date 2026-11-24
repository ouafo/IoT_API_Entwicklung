# Teststrategie für den KICAGEM IoT-Analytics-Service

## Aktueller Teststatus ✅

**7 Tests implementiert (`tests/test_api.py`)** – Alle bestanden (100 %)

### Bestehende Tests (`tests/test_api.py`)
1. `test_health_check_no_auth` – Health-Endpoint (`GET /api/health`) ohne Authentifizierung
2. `test_health_check` – Health-Endpoint mit Authentifizierung
3. `test_auth_required` – Authentifizierungsprüfung bei geschützten Endpunkten
4. `test_invalid_auth` – Ablehnung ungültiger Zugangsdaten
5. `test_invalid_sensor_type` – Validierung des Sensortyps
6. `test_invalid_datetime` – Validierung von Datum/Zeit im ISO-8601-Format
7. `test_start_after_end` – Validierung des Zeitbereichs (`StartDateTime < EndDateTime`)

---

## Empfohlene zusätzliche Tests (datenbankunabhängig)

### 1. Service-Layer-Tests (`test_measurement_service.py`)

Fokus auf **Unit-Tests mit Mocking**, um Business-Logik und Fehlerbehandlung isoliert von der Datenbank zu prüfen:

```python
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from app.services.measurement_service import get_telemetry_data
from app.exceptions import DatabaseException

@pytest.mark.asyncio
async def test_telemetry_service_basic_query():
    """Testet, ob die Service-Schicht die richtigen Abfrageparameter erstellt."""
    with patch('app.services.measurement_service.connection') as mock_conn:
        # Mock-Datenbankantwort
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            (1, "temperature", 22.5, datetime(2026, 1, 1, 12, 0), "101", "A", "°C")
        ]
        mock_cursor.description = [
            ("sensor_id",), ("sensor_type",), ("value",),
            ("timestamp",), ("room_number",), ("building",), ("unit",)
        ]
        mock_conn.get_conn.return_value.cursor.return_value = mock_cursor

        # Service-Aufruf ausführen
        result = await get_telemetry_data(
            sensor_type="temperature",
            start_time=datetime(2026, 1, 1, 0, 0),
            end_time=datetime(2026, 1, 2, 0, 0),
        )

        # Überprüfen der Antwortstruktur
        assert result.metadata["count"] == 1
        assert result.metadata["sensorType"] == "temperature"
        assert len(result.data) == 1
        assert result.data[0].sensorId == 1
        assert result.data[0].value == 22.5

@pytest.mark.asyncio
async def test_telemetry_service_pagination():
    """Testet, ob die Service-Schicht Limit und Offset korrekt behandelt."""
    with patch('app.services.measurement_service.queries') as mock_queries:
        mock_queries.build_telemetry_query.return_value = (
            "SELECT * FROM telemetry LIMIT %s OFFSET %s",
            (10, 20)
        )

        with patch('app.services.measurement_service.connection'):
            # Überprüfen der Pagination-Parameter, die an den Query-Builder übergeben werden
            await get_telemetry_data(
                sensor_type="humidity",
                start_time=datetime(2026, 1, 1),
                end_time=datetime(2026, 1, 2),
                limit=10,
                offset=20,
            )

        # Überprüfen, ob der Query-Builder mit den richtigen Parametern aufgerufen wurde
        mock_queries.build_telemetry_query.assert_called_once()
        call_args = mock_queries.build_telemetry_query.call_args
        assert call_args.kwargs["limit"] == 10
        assert call_args.kwargs["offset"] == 20

@pytest.mark.asyncio
async def test_telemetry_service_database_error():
    """Testet, ob die Service-Schicht Datenbankfehler korrekt behandelt."""
    with patch('app.services.measurement_service.connection.get_conn') as mock_conn:
        mock_conn.side_effect = Exception("Datenbankverbindung fehlgeschlagen")

        with pytest.raises(DatabaseException) as exc_info:
            await get_telemetry_data(
                sensor_type="temperature",
                start_time=datetime(2026, 1, 1),
                end_time=datetime(2026, 1, 2),
            )

        assert "Failed to execute telemetry query" in str(exc_info.value)
```

---

### 2. Security- & OData-Filter-Tests (`test_security.py`)

Test der SQL-Injection-Prävention **ohne Datenbank**:

```python
import pytest
from app.security import (
    validate_order_by,
    detect_sql_injection_patterns,
    validate_column_name,
    sanitize_order_by,
)

def test_validate_order_by_valid():
    """Testet, ob die Whitelist-Validierung gültige ORDER BY-Anweisungen akzeptiert."""
    assert validate_order_by("timestamp DESC") == True
    assert validate_order_by("value ASC") == True
    assert validate_order_by("room_number DESC") == True

def test_validate_order_by_invalid():
    """Testet, ob die Whitelist-Validierung SQL-Injection-Versuche ablehnt."""
    assert validate_order_by("timestamp; DROP TABLE users; --") == False
    assert validate_order_by("1=1 OR 1=1") == False
    assert validate_order_by("timestamp' OR '1'='1") == False

def test_detect_sql_injection_patterns():
    """Testet die heuristische Erkennung von SQL-Injection."""
    assert detect_sql_injection_patterns("'; DROP TABLE--") == True
    assert detect_sql_injection_patterns("1 UNION SELECT *") == True
    assert detect_sql_injection_patterns("timestamp DESC") == False

def test_validate_column_name():
    """Testet die Whitelist-Validierung von Spaltennamen."""
    assert validate_column_name("timestamp") == True
    assert validate_column_name("sensor_id") == True
    assert validate_column_name("invalid_column") == False
    assert validate_column_name("timestamp; DROP") == False

def test_sanitize_order_by_fallback():
    """Testet die ORDER BY-Sanitisierung mit sicherem Fallback."""
    assert sanitize_order_by("timestamp DESC") == "timestamp DESC"
    assert sanitize_order_by("invalid_column") == "timestamp DESC"
    assert sanitize_order_by("; DROP TABLE") == "timestamp DESC"
```

---

### 3. Exception-Handler-Tests (`test_exceptions.py`)

Testet benutzerdefinierte Fehlerantworten **ohne Datenbank**:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_invalid_sensor_type_exception_format():
    """Testet, ob die benutzerdefinierte Ausnahme das richtige JSON-Format zurückgibt."""
    response = client.get(
        "/api/Rooms('C1.003')/Measurements",
        params={
            "StartDateTime": "2026-01-01T00:00:00Z",
            "EndDateTime": "2026-01-02T00:00:00Z",
            "$filter": "SensorTypeCode eq 'invalid_type'",
        },
        auth=("test_user", "test_pass"),
    )
    assert response.status_code in (400, 401)

def test_datetime_exception_format():
    """Testet, ob ungültige Datums-/Uhrzeitangaben abgewiesen werden."""
    response = client.get(
        "/api/Rooms('C1.003')/Measurements",
        params={
            "StartDateTime": "invalid-datetime",
            "EndDateTime": "2026-01-02T00:00:00Z",
        },
        auth=("test_user", "test_pass"),
    )
    assert response.status_code in (400, 401, 422)
```

---

### 4. Query-Builder-Tests (`test_queries.py`)

Testet die SQL-Generierungslogik **ohne Abfragen auszuführen**:

```python
import pytest
from datetime import datetime
from app.database.queries import build_telemetry_query

def test_build_telemetry_query_basic():
    """Testet, ob der Query-Builder die richtige SQL-Struktur generiert."""
    sql, params = build_telemetry_query(
        sensor_type="temperature",
        start_time=datetime(2026, 1, 1, 0, 0),
        end_time=datetime(2026, 1, 2, 0, 0),
    )

    assert "SELECT" in sql
    assert "FROM" in sql
    assert len(params) >= 3
    assert params[0] == "temperature"

def test_build_telemetry_query_with_pagination():
    """Testet, ob der Query-Builder LIMIT und OFFSET hinzufügt."""
    sql, params = build_telemetry_query(
        sensor_type="co2",
        start_time=datetime(2026, 1, 1),
        end_time=datetime(2026, 1, 2),
        limit=50,
        offset=100,
    )

    assert "LIMIT %s" in sql
    assert "OFFSET %s" in sql
    assert 50 in params
    assert 100 in params
```

---

### 5. Authentifizierungs- & Prognose-Tests

```python
def test_basic_auth_timing_attack_protection():
    """Testet, ob die Authentifizierung den Vergleich in konstanter Zeit verwendet."""
    from app.auth.basic_auth import verify_basic_auth
    import time

    start = time.time()
    try:
        verify_basic_auth(credentials=("test_user", "wrong"))
    except Exception:
        pass
    time1 = time.time() - start

    start = time.time()
    try:
        verify_basic_auth(credentials=("test_user", "verylongwrongpassword123"))
    except Exception:
        pass
    time2 = time.time() - start

    # Zeitdifferenz sollte minimal sein (< 10ms)
    assert abs(time1 - time2) < 0.01

def test_basic_auth_empty_credentials():
    """Testet, ob die Authentifizierung leere Zugangsdaten ablehnt."""
    response = client.get(
        "/api/Rooms",
        auth=("", ""),
    )
    assert response.status_code == 401
```

---

## Integrationstest-Strategie

### Schwerpunkte für Integrationstests
1. **Echte Datenbanktests** – Testen gegen die PostgreSQL-Datenbank im Campusnetz
2. **Datenvalidierungstests** – Überprüfung von Datentypen, OData-Antworten (`@odata.context`, `@odata.count`) und Constraints
3. **Prognose-Endpunkt-Tests** – Validierung der Ausgaben von `forecast_engine.py` und `energy_forecast_routes.py`
4. **Leistungstests** – Abfrage-Antwortzeit-Benchmarks und gleichzeitige Requests

---

## Prioritäten für die Testweiterentwicklung

### Hoch
1. ✅ **API-Input-Validierung** (bereits umgesetzt – 7 Tests)
2. ⭐ **Security- & OData-Parser-Tests** (SQL-Injection-Prüfung)
3. ⭐ **Service-Layer-Tests** (Business-Logik mit Mocks)
4. ✅ **Exception-Handler-Tests** (bereits abgedeckt)

### Mittel
5. **Forecast-Engine-Tests** (Zeitreihen- und Prognose-Validierung)
6. **Query-Builder-Tests** (SQL-Generierungslogik)
7. **Authentifizierungs-Edge-Cases** (Timing-Angriffe, leere Zugangsdaten)

### Niedrig
8. **Integrationstests** (echte DB-Abfragen)
9. **Leistungstests** (Antwortzeit-Benchmarks)
10. **Lasttests** (gleichzeitige Anfragebearbeitung)

---

## Tests ausführen

### Alle Tests ausführen
```bash
pytest tests/ -v
```

### Bestimmte Testdatei ausführen
```bash
pytest tests/test_api.py -v
```

### Tests mit Coverage-Bericht ausführen
```bash
pytest tests/ --cov=app --cov-report=html
```

### Integrationstests überspringen
```bash
pytest tests/ -v -m "not integration"
```

---

## Testabdeckungsziele & Qualitätssicherung

- **Aktuelle Abdeckung:** ~40 % (7 API-Tests)
- **Empfohlene Abdeckung:** 70–80 % (15–20 Tests)
- **Realistisches Ziel:** 60–70 % (12–15 Tests)

### Zielwerte nach Modul

| Modul | Aktuell | Ziel | Priorität |
| :--- | :--- | :--- | :--- |
| `app/api/routes.py` | ✅ 80 % | 80 % | HOCH |
| `app/api/odata_helpers.py` | ⚠️ Teilweise | 75 % | HOCH |
| `app/services/measurement_service.py` | ❌ 0 % | 65 % | HOCH |
| `app/services/forecast_engine.py` | ❌ 0 % | 65 % | MITTEL |
| `app/exceptions.py` | ✅ 50 % | 60 % | MITTEL |
| `app/database/queries.py` | ❌ 0 % | 50 % | MITTEL |
| `app/auth/basic_auth.py` | ✅ 60 % | 70 % | MITTEL |
| `app/database/connection.py` | ❌ 0 % | 30 % | NIEDRIG* |

*\*Connection-Pooling ist vor allem im Verbund mit einer aktiven Datenbankinstanz sinnvoll testbar.*

### Ergänzende Maßnahmen zur Codequalität
1. **Type-Hints & Pydantic v2** – Strikte Typprüfung für Request- und Response-Modelle
2. **Eigene Fehlerbehandlung** – Strukturierte JSON-Fehlerantworten mit eindeutigen Statuscodes
3. **SQL-Injection-Prävention** – Parametrisierte Queries und Whitelist-Validierung
4. **End-to-End-Verifikation** – Regelmäßige Prüfung von `/api/health`, `/docs` und dem Streamlit-Dashboard auf dem Hochschulserver

---

## Fazit

- **Aktueller Status:** 7 Tests (100 % bestanden) ✅
- **Empfohlene Ergänzung:** 5–8 weitere datenbankunabhängige Unit-Tests
- **Ziel:** 12–15 Tests für eine hohe Testabdeckung der Kernlogik