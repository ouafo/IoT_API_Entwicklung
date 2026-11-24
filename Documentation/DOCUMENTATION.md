# KICAGEM IoT Analytics & Dashboard Platform – Dokumentation

**Projekttyp:** FastAPI-basierter IoT-Telemetrie-Analytics-Webservice & Streamlit-Dashboard  
**Server-Pfad:** `/opt/kicagem` (`iwilsv-3.campus.fh-ludwigshafen.de`)  
**Python-Version:** 3.12 (Docker-Container `kicagem-api`)  
**Status:** ✅ Produktiv im Einsatz

---

## Inhaltsverzeichnis

1. [Projektübersicht](#projektübersicht)
2. [Architektur](#architektur)
3. [Systemvoraussetzungen](#systemvoraussetzungen)
4. [Installation & Setup](#installation--setup)
5. [Wichtige Probleme & Lösungen](#wichtige-probleme--lösungen)
6. [Erweiterungen & Abhängigkeiten](#erweiterungen--abhängigkeiten)
7. [API-Endpunkte & OData-Konventionen](#api-endpunkte--odata-konventionen)
8. [Konfiguration](#konfiguration)
9. [Teststrategie](#teststrategie)
10. [Deployment](#deployment)
11. [Fehlerbehebung](#fehlerbehebung)

---

## Projektübersicht

### Zweck
Ein performanter Webservice zur Abfrage, Analyse und Prognose von IoT-Telemetriedaten (Raumklima, Wetter, Energieverbrauch) aus PostgreSQL mit OData-Filterung, sicherer Authentifizierung und einem interaktiven Streamlit-Analyse-Dashboard.

### Hauptfunktionen
- ✅ **FastAPI** – Asynchrone Web-API mit OpenAPI-/Swagger-UI (`/docs`)
- ✅ **PostgreSQL** – Verbindungspooling mit `psycopg`
- ✅ **Energieprognose** – Zeitreihen- und Lastprognosen auf Basis von `numpy`, `pandas` und `scikit-learn`
- ✅ **Streamlit-Dashboard** – Interaktive Weboberfläche für Raumklima, Wetter und Energieauswertungen
- ✅ **OData-Unterstützung** – `$filter`, `$orderby`, `$top`, `$skip`, `$count` und `/api/$metadata`
- ✅ **Authentifizierung** – HTTP Basic Auth
- ✅ **JSON-Logging** – Strukturierte Logs für Konsole und Log-Dateien
- ✅ **Docker** – Kombinierte Containerisierung von Backend und Dashboard
- ✅ **Testing** – Pytest-Test-Suite
- ✅ **Health Check** – Öffentlicher `/api/health`-Endpunkt inkl. Datenbank-Latenzmessung

---

## Architektur

```text
/opt/kicagem/
├── app/
│   ├── main.py                        # FastAPI-App, Lifespan (DB-Pool), Middleware
│   ├── config.py                      # Konfiguration & Zugangsdaten
│   ├── logger.py                      # JSON-Logging
│   ├── exceptions.py                  # Benutzerdefinierte Ausnahmen
│   ├── requirements.txt               # Backend- & ML-Abhängigkeiten
│   ├── api/
│   │   ├── routes.py                  # Hauptendpunkte (Rooms, Measurements, Metadata, Health)
│   │   ├── energy_forecast_routes.py  # Endpunkte für Energieprognosen
│   │   └── odata_helpers.py           # OData-Parser
│   ├── auth/
│   │   └── basic_auth.py              # Authentifizierung
│   ├── database/
│   │   ├── connection.py              # DB-Pool
│   │   └── queries.py                 # SQL-Builder
│   ├── models/
│   │   └── measurement.py             # Pydantic-Modelle
│   └── services/
│       ├── measurement_service.py     # Business-Logik Telemetrie
│       ├── energy_forecast_service.py # Business-Logik Energieprognose
│       └── forecast_engine.py         # Prognose-Engine (NumPy, Pandas, Scikit-Learn)
├── dashboard/
│   ├── app.py                         # Streamlit-Hauptanwendung
│   ├── api_client.py                  # HTTP-Client mit Basic Auth
│   ├── config.py                      # Dashboard-Konfiguration
│   ├── .env.connection                # Verbindungs-Konfiguration
│   ├── requirements.txt               # Dashboard-Abhängigkeiten
│   ├── components/                    # UI- & Chart-Komponenten
│   └── pages/                         # Dashboard-Seiten
├── Documentation/
│   ├── README.md                      # Schnellstart & Betriebsübersicht
│   ├── DOCUMENTATION.md               # Diese Dokumentation
│   ├── IMPORTANT_CODE_SNIPPETS.md     # Zentrale Code-Snippets
│   └── TESTING_STRATEGY.md            # Teststrategie
├── tests/
│   └── test_api.py                    # API-Tests
├── start.sh                           # Startskript für Uvicorn + Streamlit
├── Dockerfile                         # Container-Image
├── docker-compose.yml                 # Container-Konfiguration (Ports 8000 & 8501)
└── README.md                          # Haupt-README im Repository-Root
```

---

## Systemvoraussetzungen

- **Hardware:** Mind. 1 GB RAM, 1 CPU-Kern (empfohlen: 2 GB RAM, 2+ Kerne für ML-Prognosen und Dashboard)
- **Software Server:** Docker Engine, Docker Compose (`docker compose`), Git
- **Software Lokal:** Python 3.12+, PostgreSQL-Netzwerkzugriff (HWG-Campusnetz oder VPN), Git
- **Betriebssystem:** Linux (Ubuntu 24.04 LTS auf dem Server), macOS, Windows 10/11

---

## Installation & Setup

### Auf dem Hochschulserver (`/opt/kicagem`)
1. **Zielverzeichnis erstellen und Rechte setzen:**
   ```bash
   sudo mkdir -p /opt/kicagem
   sudo chown -R gruppe3:gruppe3 /opt/kicagem
   ```
2. **Repository klonen:**
   ```bash
   cd /opt/kicagem
   git clone [https://github.com/ouafo/IoT_API_Entwicklung.git](https://github.com/ouafo/IoT_API_Entwicklung.git) .
   ```
3. **Container bauen und starten:**
   ```bash
   docker compose up -d --build
   ```

### Lokale Entwicklungsumgebung
1. **Repository klonen:**
   ```bash
   git clone [https://github.com/ouafo/IoT_API_Entwicklung.git](https://github.com/ouafo/IoT_API_Entwicklung.git)
   cd IoT_API_Entwicklung
   ```
2. **Virtuelle Umgebung erstellen:**
   ```bash
   python3 -m venv .venv
   # macOS/Linux:
   source .venv/bin/activate
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   ```
3. **Abhängigkeiten installieren:**
   ```bash
   pip install -r app/requirements.txt
   pip install -r dashboard/requirements.txt
   ```
4. **Tests ausführen:**
   ```bash
   pytest tests/test_api.py -v
   ```
5. **Backend und Dashboard starten:**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   streamlit run dashboard/app.py
   ```

---

## Wichtige Probleme & Lösungen

- **PostgreSQL-Treiber:** `psycopg` (psycopg3) wird für die Datenbankanbindung und das Connection-Pooling verwendet.
- **Pydantic v2 Namenskonflikt in `MeasurementResponse`:** Für das optionale Feld `Room` wird in `app/models/measurement.py` der Typ-Alias `RoomModel = Room` verwendet (`Room: Optional[RoomModel] = Field(default=None)`), damit Python den Klassennamen `Room` im Klassen-Namespace nicht mit `None` überschreibt.
- **ML-Abhängigkeiten im Container:** `app/requirements.txt` enthält `numpy`, `pandas` und `scikit-learn`, damit `app/services/forecast_engine.py` beim Container-Start geladen werden kann.
- **OData-Filter:** Filter-Parsing und parametrisiertes SQL-Merging für `$filter`, `$orderby`, `$top`, `$skip` und `$count`.
- **JSON-Logging:** Eigener JSON-Formatter in `app/logger.py` für einheitliche Log-Ausgaben.
- **Docker Healthcheck:** Prüft `http://localhost:8000/api/health` (mit dem API-Präfix `/api`).
- **Kombinierter Container-Start (`start.sh`):** Startet Uvicorn (`8000`) und Streamlit (`8501`) parallel und beendet den Container über `wait -n`, sobald einer der beiden Prozesse abstürzt, damit Docker den Container automatisch neu startet.
- **Statuscodes:** `401` bei fehlender oder ungültiger Authentifizierung.

---

## Erweiterungen & Abhängigkeiten

- **Backend & Prognose (`app/requirements.txt`):** `fastapi`, `uvicorn`, `starlette`, `pydantic`, `psycopg[binary]`, `passlib`, `python-dotenv`, `httpx`, `numpy`, `pandas`, `scikit-learn`, `pytest`, `pytest-asyncio`
- **Dashboard (`dashboard/requirements.txt`):** `streamlit`, `requests`, `plotly`, `pandas`
- **VS Code Extensions:** Python, Pylance, Pylint, Docker, PostgreSQL, Thunder Client
- **Tools:** Docker, Docker Compose, Git

---

## API-Endpunkte & OData-Konventionen

### Endpunkte
- **`GET /api/Rooms`** – Liste aller Räume (OData-Query möglich)
- **`GET /api/Rooms('A203')`** – Einzelner Raum (z. B. `A203`, `C1.003`)
- **`GET /api/Rooms('C1.003')/Measurements`** – Messwerte für einen Raum (Zeitfenster + OData-Query)
- **`GET /api/$metadata`** – OData-Metadaten (XML)
- **`GET /api/health`** – Health-Check (ohne Authentifizierung)
- **Energieprognose-Endpunkte** – Alle Routen und Schemata im Bereich *Energy Forecast* unter `/docs`

### OData-Konventionen
- **`$filter`** – Filterung nach Feldwerten (z. B. `SensorTypeCode eq 'temperature'`)
- **`$orderby`** – Sortierung (z. B. `StartDateTime desc`)
- **`$top`** – Limitierung der Ergebnisse
- **`$skip`** – Offset/Pagination
- **`$count`** – Rückgabe der Gesamtanzahl

#### Beispiel-Links
- `/api/Rooms?$top=10&$skip=0`
- `/api/Rooms('A203')`
- `/api/Rooms('C1.003')/Measurements?StartDateTime=2026-11-18T00:00:00Z&EndDateTime=2026-11-19T00:00:00Z&$filter=SensorTypeCode eq 'temperature'&$orderby=StartDateTime desc&$top=5&$skip=0`
- `/api/$metadata`

---

## Konfiguration

Das Projekt benötigt keine externe `.env`-Datei im Hauptverzeichnis. Alle Konfigurationsparameter sind direkt im Repository hinterlegt:
- **Backend (`app/config.py`):** `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SCHEMA`, `API_PREFIX` (`/api`) sowie Benutzername/Passwort für HTTP Basic Auth.
- **Dashboard (`dashboard/config.py` & `dashboard/.env.connection`):** `API_BASE_URL` (`http://localhost:8000`), `API_USERNAME`, `API_PASSWORD`, `REQUEST_TIMEOUT`.

---

## Teststrategie

- **Pytest**-basierte Testsuite (`tests/test_api.py`)
- 7 API-Tests: Health-Check, Authentifizierung, Input-Validierung, Zeitbereichs-Prüfung
- Geplante Erweiterungen: Service-Layer-Tests, Security-Tests, Query-Builder-Tests, Forecast-Engine-Tests (siehe `Documentation/TESTING_STRATEGY.md`)

### Tests ausführen
```bash
pytest tests/ -v
```
Mit Coverage:
```bash
pytest tests/ --cov=app
```

---

## Deployment

### Hochschulserver mit Docker Compose (`/opt/kicagem`)
```bash
cd /opt/kicagem
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=50
```

### Container stoppen
```bash
docker compose down
```

### Lokal
```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
streamlit run dashboard/app.py
```

### Produktion
- Externe Hochschul-PostgreSQL-Datenbank angebunden
- Automatischer Neustart bei Server-Reboot (`restart: unless-stopped`)
- Container-Überwachung über Docker `HEALTHCHECK` (`/api/health`) und `start.sh` (`wait -n`)

---

## Fehlerbehebung

- **DB-Verbindungsfehler:** `DB_HOST`, `DB_PORT` und Zugangsdaten in `app/config.py` prüfen; sicherstellen, dass Campusnetz/VPN aktiv ist.
- **Importfehler (`ModuleNotFoundError`):** Virtuelle Umgebung aktivieren und `pip install -r app/requirements.txt` bzw. `pip install -r dashboard/requirements.txt` ausführen (im Container `docker compose up -d --build`).
- **Auth-Fehler (`401`) in `/docs`:** In Swagger UI vor dem Ausführen von Requests über den Button **Authorize** anmelden; bei gecachten Fehlversuchen im Browser ein Inkognito-Fenster verwenden.
- **Dashboard zeigt „Offline“:** Prüfen, ob FastAPI unter `http://localhost:8000/api/health` antwortet (`docker compose logs --tail=50`).
- **OData-Filter:** Spaltennamen und OData-Syntax (`eq`, `gt`, `lt`, `and`) prüfen.
- **`git pull` Konflikt auf dem Server:** Falls Dateien auf dem Server manuell geändert wurden, mit `git fetch origin && git reset --hard origin/main` auf den aktuellen GitHub-Stand zurücksetzen.

---

## Ressourcen

- **`README.md`** – Schnellstart & Betriebsübersicht
- **`Documentation/DOCUMENTATION.md`** – Diese Dokumentation
- **`Documentation/IMPORTANT_CODE_SNIPPETS.md`** – Zentrale Code-Snippets
- **`Documentation/TESTING_STRATEGY.md`** – Teststrategie
- **`app/main.py`** – FastAPI App-Factory & Lifespan
- **`app/api/routes.py`** – Hauptendpunkte
- **`app/api/energy_forecast_routes.py`** – Energieprognose-Endpunkte
- **`app/api/odata_helpers.py`** – OData-Parsing
- **`app/database/queries.py`** – SQL-Builder
- **`dashboard/app.py`** – Streamlit-Dashboard
- **`tests/test_api.py`** – Automatisierte Tests

---

## Zusammenfassung

✅ Produktive IoT-Analytics- und Dashboard-Plattform  
✅ FastAPI-Backend + Streamlit-Dashboard in einem Docker-Container  
✅ PostgreSQL mit Connection Pooling  
✅ Energieprognose-Engine (`numpy`, `pandas`, `scikit-learn`)  
✅ OData-Filterung & Metadaten  
✅ HTTP Basic Auth & JSON-Logging  
✅ Vollständige Dokumentation