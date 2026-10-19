# KICAGEM IoT Analytics Service – Dokumentation

**Projekttyp:** FastAPI-basierter IoT-Telemetrie-Analytics-Webservice  
**Erstellt:** Dezember 2025  
**Python-Version:** 3.14.2  
**Status:** ✅ Produktionsbereit

---

## Inhaltsverzeichnis

1. [Projektübersicht](#projektübersicht)
2. [Architektur](#architektur)
3. [Systemvoraussetzungen](#systemvoraussetzungen)
4. [Installation & Setup](#installation--setup)
5. [Wichtige Probleme & Lösungen](#wichtige-probleme--lösungen)
6. [Erweiterungen & Abhängigkeiten](#erweiterungen--abhängigkeiten)
7. [API-Endpunkte & OData-Konventionen](#api-endpunkte--odatakonventionen)
8. [Konfiguration](#konfiguration)
9. [Teststrategie](#teststrategie)
10. [Deployment](#deployment)
11. [Fehlerbehebung](#fehlerbehebung)

---

## Projektübersicht

### Zweck
Ein performanter Webservice zur Abfrage von IoT-Telemetriedaten aus PostgreSQL mit OData-Filterung und sicherer Authentifizierung.

### Hauptfunktionen
- ✅ **FastAPI** – Asynchrone Web-API
- ✅ **PostgreSQL** – Verbindungspooling
- ✅ **OData-Unterstützung** – `$filter`, `$orderby`, `$top`, `$skip`
- ✅ **Authentifizierung** – HTTP Basic Auth
- ✅ **JSON-Logging** – Strukturierte Logs
- ✅ **Docker** – Containerisierung
- ✅ **Testing** – Pytest-Test-Suite
- ✅ **Health Check** – Öffentlicher `/health`-Endpunkt

---

## Architektur

```
kicagem-iot-service/
├── app/
│   ├── main.py              # FastAPI-App
│   ├── config.py            # Konfiguration
│   ├── logger.py            # JSON-Logging
│   ├── api/
│   │   ├── routes.py        # API-Endpunkte
│   │   └── odata_helpers.py # OData-Parser
│   ├── auth/
│   │   └── basic_auth.py    # Authentifizierung
│   ├── database/
│   │   ├── connection.py    # DB-Pool
│   │   └── queries.py       # SQL-Builder
│   ├── models/
│   │   └── measurement.py   # Pydantic-Modelle
│   └── services/
│       └── measurement_service.py  # Business-Logik
├── tests/
│   └── test_api.py          # API-Tests
├── Dockerfile               # Container-Image
├── docker-compose.yml       # Dev-Umgebung
├── .env.example             # Umgebungs-Template
├── .gitignore               # Git Ignore
└── DOCUMENTATION.md         # Diese Datei
```

---

## Systemvoraussetzungen

- **Hardware:** Mind. 512MB RAM, 1 CPU-Kern (empfohlen: 2GB RAM, 2+ Kerne)
- **Software:** Python 3.14.2+, PostgreSQL 12+, Docker (optional), Git
- **Betriebssystem:** Windows 10/11, macOS, Linux

---

## Installation & Setup

1. **Repository klonen:**
   ```bash
   git clone <repository-url>
   cd kicagem-iot-service
   ```
2. **Virtuelle Umgebung erstellen:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   # oder auf macOS/Linux: source .venv/bin/activate
   ```
3. **Abhängigkeiten installieren:**
   ```bash
   pip install -r app/requirements.txt
   ```
4. **Umgebung konfigurieren:**
   ```bash
   cp .env.example .env
   # Bearbeite .env mit deinen DB-Zugangsdaten
   ```
5. **Tests ausführen:**
   ```bash
   pytest tests/test_api.py -v
   ```
6. **Server starten:**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

---

## Wichtige Probleme & Lösungen

- **Python 3.14 Kompatibilität:** psycopg3 statt psycopg2 verwenden
- **OData-Filter:** Filter-Parsing und SQL-Merging korrigiert
- **JSON-Logging:** Eigener Formatter statt pythonjsonlogger
- **httpx/httpcore:** Versionen für Python 3.14 angepasst
- **Docker Healthcheck:** Einzeilige Lösung mit httpx
- **Statuscodes:** 401 für Auth-Fehler

---

## Erweiterungen & Abhängigkeiten

- **Python:** fastapi, uvicorn, starlette, psycopg[binary], passlib, python-dotenv, httpx, pytest, pytest-asyncio
- **VS Code Extensions:** Python, Pylance, Pylint, Docker, PostgreSQL, Thunder Client
- **Tools:** Docker, docker-compose, PowerShell

---

## API-Endpunkte & OData-Konventionen

### Endpunkte
- **GET /api/Rooms** – Liste aller Räume (OData-Query möglich)
- **GET /api/Rooms('A-A203')** – Einzelner Raum
- **GET /api/Rooms('A-A203')/Measurements** – Messwerte für Raum (OData-Query möglich)
- **GET /api/$metadata** – OData-Metadaten (XML)
- **GET /health** – Health-Check (ohne Authentifizierung)

### OData-Konventionen
- **$filter** – Filterung nach Feldwerten (z.B. `SensorTypeCode eq 'temperature'`)
- **$orderby** – Sortierung (z.B. `StartDateTime desc`)
- **$top** – Limitierung der Ergebnisse
- **$skip** – Offset/Pagination
- **$count** – Rückgabe der Gesamtanzahl

#### Beispiel-Links
- `/api/Rooms?$top=10&$skip=0`
- `/api/Rooms('A-A203')`
- `/api/Rooms('A-A203')/Measurements?$filter=SensorTypeCode eq 'temperature'&$orderby=StartDateTime desc&$top=5&$skip=0`
- `/api/$metadata`

---

## Konfiguration

Umgebungsvariablen in `.env`:


## Teststrategie

- **Pytest**-basierte Testsuite
- 7 API-Tests: Health, Auth, Input-Validierung, Fehlerbehandlung
- Empfohlene Erweiterung: Service-Layer-Tests, Security-Tests, Query-Builder-Tests
- Integrationstests nach finaler DB-Schema-Festlegung

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

### Lokal
```bash
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Docker
```bash
docker build -t kicagem-iot-service:1.0.0 .
docker run -p 8000:8000 --env-file .env kicagem-iot-service:1.0.0
```

### Docker Compose
```bash
docker-compose up -d
docker-compose down
docker-compose logs -f api
```

### Produktion
- Externe DB nutzen
- HTTPS aktivieren (Reverse Proxy)
- API skalieren
- Monitoring & Logging
- Backup & Recovery

---

## Fehlerbehebung

- **DB-Verbindungsfehler:** DB_HOST/DB_PORT prüfen, DB läuft?
- **Importfehler:** Virtuelle Umgebung aktivieren, Abhängigkeiten installieren
- **Auth-Fehler:** Base64-Header korrekt setzen
- **OData-Filter:** Spaltennamen und Syntax prüfen
- **Testfehler:** Umgebung und Abhängigkeiten prüfen

---

## Ressourcen
- **README.md** – Schnellstart
- **DOCUMENTATION.md** – Diese Dokumentation
- **.env.example** – Umgebungs-Template
- **app/main.py** – App-Factory
- **app/api/routes.py** – Endpunkte
- **app/api/odata_helpers.py** – OData-Parsing
- **app/database/queries.py** – SQL-Builder
- **tests/test_api.py** – Tests

---

## Zusammenfassung

✅ Produktionsreife IoT-Analytics-API  
✅ FastAPI mit Async-Support  
✅ PostgreSQL mit Pooling  
✅ OData-Filterung  
✅ HTTP Basic Auth  
✅ JSON-Logging  
✅ Test-Suite  
✅ Docker-Containerisierung  
✅ Vollständige Dokumentation

**Letzte Aktualisierung:** 24. Dezember 2025  
**Version:** 1.0.0  
**Status:**  Produktionsbereit
