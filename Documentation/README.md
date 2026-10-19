# KICAGEM IoT Analytics Service

Ein moderner FastAPI-Webservice zur Analyse von IoT-Telemetriedaten aus PostgreSQL mit OData-Filterung und sicherer Authentifizierung.

## Hauptfunktionen

✅ **FastAPI** – Asynchrone, performante Web-API  
✅ **PostgreSQL** – Zuverlässige Datenbank mit Connection Pooling  
✅ **Service Layer Architektur** – Saubere Trennung von API, Logik und Datenbank  
✅ **Eigene Fehlerbehandlung** – Strukturierte Fehlerantworten mit passenden HTTP-Statuscodes  
✅ **SQL-Injection-Prävention** – Whitelist-Validierung für Query-Parameter  
✅ **OData-Filterung** – Unterstützung für `$filter`, `$orderby`, `$top`, `$skip`  
✅ **Basic Auth** – Sichere Endpunkte mit Schutz vor Timing-Angriffen  
✅ **Strukturiertes Logging** – JSON-Logs für Monitoring  
✅ **Docker-Support** – Vollständiges Docker- und docker-compose-Setup  
✅ **Pytest** – Automatisierte Tests mit 100% Erfolgsrate

## OData-Konventionen & Beispiel-Links

- **Alle Räume abfragen:**  
  `/api/Rooms?$top=10&$skip=0`
- **Einzelnen Raum abfragen:**  
  `/api/Rooms('A-A203')`
- **Messwerte für einen Raum (mit Filter & Sortierung):**  
  `/api/Rooms('A-A203')/Measurements?$filter=SensorTypeCode eq 'temperature'&$orderby=StartDateTime desc&$top=5&$skip=0`
- **Metadaten abrufen:**  
  `/api/$metadata`

## Installation & Start

1. **Umgebung einrichten:**
   ```bash
   cp .env.example .env
   # Bearbeite .env mit deinen PostgreSQL-Zugangsdaten
   ```
2. **Abhängigkeiten installieren:**
   ```bash
   pip install -r app/requirements.txt
   ```
3. **Server starten:**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
4. **API aufrufen:**
   - Swagger UI: http://127.0.0.1:8000/docs
   - Beispiel-Endpunkt: http://127.0.0.1:8000/api/Rooms

## Docker-Nutzung

1. **Mit docker-compose (empfohlen):**
   ```bash
   docker-compose up -d
   ```
2. **Manuell mit Docker:**
   ```bash
   docker build -t kicagem-api .
   docker run -p 8000:8000 --env-file .env kicagem-api
   ```

## API-Nutzung

### Beispiel-Request

```bash
curl -H "Authorization: Basic $(echo -n 'admin:98558979c' | base64)" \
  "http://127.0.0.1:8000/api/Rooms('A-A203')/Measurements?$filter=SensorTypeCode eq 'temperature'&$top=5"
```

### Wichtige Query-Parameter

- **SensorType** (Pflicht): `temperature|humidity|co2|light|energy`
- **StartDateTime** (Pflicht): ISO 8601 Datum/Zeit (z.B. `2025-01-01T00:00:00Z`)
- **EndDateTime** (Pflicht): ISO 8601 Datum/Zeit
- **$filter** (optional): OData-Filterausdruck (z.B. `value gt 22`)
- **$orderby** (optional): Sortierung (z.B. `StartDateTime desc`)
- **$top** (optional): Limit (max: 1000)
- **$skip** (optional): Offset
- **roomNumber** (optional): Raum-Filter

## Testen

Tests ausführen:
```bash
pytest tests/ -v
```
Mit Coverage:
```bash
pytest tests/ --cov=app
```

## Projektstruktur

```
.
├── app/
│   ├── main.py              # FastAPI App-Einstieg
│   ├── config.py            # Konfiguration
│   ├── logger.py            # Logging
│   ├── requirements.txt     # Python-Abhängigkeiten
│   ├── api/
│   │   ├── routes.py        # API-Endpunkte
│   │   └── odata_helpers.py # OData-Parsing
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
└── README.md                # Diese Datei
```

## Umgebungsvariablen

Siehe `.env` für alle Optionen.

## Logging

Logs werden als JSON ausgegeben:
- **Konsole**: Alle Logs
- **Datei**: `logs/app.log` (Rotation bei 10MB, 5 Backups)

## Health Check

Container Health Check:
```bash
docker inspect kicagem_api --format='{{.State.Health.Status}}'
```

## Produktion

1. **Zugangsdaten** in `.env` aktualisieren
2. **Externe PostgreSQL** nutzen
3. **HTTPS aktivieren** (Reverse Proxy)
4. **API skalieren** (mehrere Instanzen)
5. **Logs überwachen**
6. **Backup & Recovery** einrichten
