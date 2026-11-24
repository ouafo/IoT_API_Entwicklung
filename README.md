# KICAGEM IoT Analytics & Dashboard Platform

Eine ganzheitliche Web- und Analyseplattform zur Erfassung, Abfrage, Visualisierung und Prognose von IoT-Telemetriedaten (Raumklima, Wetter, Energieverbrauch) aus PostgreSQL an der Hochschule für Wirtschaft und Gesellschaft Ludwigshafen.

Die Anwendung besteht aus zwei Komponenten, die gemeinsam in einem Docker-Container (`kicagem-api`) betrieben werden:
1. **FastAPI-Backend (Port `8000`):** Asynchrone REST-/OData-API mit PostgreSQL-Connection-Pooling, HTTP Basic Authentication, strukturiertem JSON-Logging und integrierter Energieprognose-Engine.
2. **Streamlit-Dashboard (Port `8501`):** Interaktive Weboberfläche zur visuellen Analyse von Raumklimadaten, Wetterdaten, Energieverbräuchen und Lastprognosen.

---

## Inhaltsverzeichnis

1. [Hauptfunktionen](#hauptfunktionen)
2. [Live-Zugriff auf dem Hochschulserver](#live-zugriff-auf-dem-hochschulserver)
3. [Projektstruktur & Architektur](#projektstruktur--architektur)
4. [Server-Betrieb & Steuerung (Docker)](#server-betrieb--steuerung-docker)
5. [Konfiguration & Zugangsdaten](#konfiguration--zugangsdaten)
6. [API-Nutzung & OData-Konventionen](#api-nutzung--odata-konventionen)
7. [Lokale Installation & Entwicklung](#lokale-installation--entwicklung)
8. [Tests ausführen](#tests-ausführen)
9. [Logging & Health-Check](#logging--health-check)
10. [Weiterführende Dokumentation](#weiterführende-dokumentation)

---

## Hauptfunktionen

- ✅ **FastAPI** – Asynchrone, performante Web-API mit automatischer OpenAPI-/Swagger-Dokumentation
- ✅ **Streamlit-Dashboard** – Mehrseitiges Analyse-Dashboard für Raumklima, Wetter und Energie
- ✅ **PostgreSQL** – Zuverlässige Datenbankanbindung mit Connection Pooling (`psycopg`)
- ✅ **Service Layer Architektur** – Saubere Trennung von API-Routen, Business-Logik, Prognose-Engine und Datenbankzugriff
- ✅ **Energieprognose-Engine** – Datenanalyse und Vorhersagemodelle auf Basis von `numpy`, `pandas` und `scikit-learn`
- ✅ **OData-Filterung** – Unterstützung für `$filter`, `$orderby`, `$top`, `$skip`, `$count` sowie `/api/$metadata`
- ✅ **SQL-Injection-Prävention** – Parametrisierte SQL-Abfragen und Whitelist-Validierung für Query-Parameter
- ✅ **Eigene Fehlerbehandlung** – Strukturierte JSON-Fehlerantworten mit passenden HTTP-Statuscodes
- ✅ **Basic Auth** – Gesicherte API-Endpunkte mit Schutz vor Timing-Angriffen (`secrets.compare_digest`)
- ✅ **Strukturiertes Logging** – JSON-Logs für Konsole und rotierende Log-Dateien
- ✅ **Docker & Docker Compose** – Kombinierter Produktiv-Container für Backend und Frontend
- ✅ **Pytest** – Automatisierte Test-Suite

---

## Live-Zugriff auf dem Hochschulserver

- **Server:** `iwilsv-3.campus.fh-ludwigshafen.de` (Ubuntu 24.04 LTS)
- **Projektverzeichnis:** `/opt/kicagem`
- **GitHub-Repository:** `https://github.com/ouafo/IoT_API_Entwicklung.git` (Branch: `main`)
- **Netzwerkvoraussetzung:** Zugriff im Campus-Netz der HWG Ludwigshafen oder über aktives **HWG-VPN**.

| Dienst | URL | Beschreibung | Authentifizierung |
| :--- | :--- | :--- | :--- |
| **Streamlit-Dashboard** | `http://iwilsv-3.campus.fh-ludwigshafen.de:8501` | Interaktives Analyse-Dashboard | Intern im `APIClient` hinterlegt |
| **Swagger UI (API-Docs)** | `http://iwilsv-3.campus.fh-ludwigshafen.de:8000/docs` | Interaktive API-Dokumentation & Testoberfläche | HTTP Basic Auth (über Button *Authorize*) |
| **ReDoc** | `http://iwilsv-3.campus.fh-ludwigshafen.de:8000/redoc` | Alternative API-Referenz | HTTP Basic Auth |
| **Health-Check** | `http://iwilsv-3.campus.fh-ludwigshafen.de:8000/api/health` | Status von API & PostgreSQL-Pool inkl. Latenz | Öffentlich (keine Auth erforderlich) |

---

## Projektstruktur & Architektur

Beide Python-Dienste laufen zusammen im Docker-Container **`kicagem-api`**. Das Startskript `start.sh` startet Uvicorn (Port `8000`) und Streamlit (Port `8501`) parallel und überwacht beide Prozesse über `wait -n` (stürzt einer der Prozesse ab, startet Docker den Container automatisch neu).

```text
.
├── app/                                   # FastAPI-Backend
│   ├── main.py                            # FastAPI App-Einstieg, Lifespan (DB-Pool), Middleware
│   ├── config.py                          # Backend-Konfiguration & Zugangsdaten
│   ├── logger.py                          # Strukturiertes JSON-Logging
│   ├── exceptions.py                      # Benutzerdefinierte Fehlerklassen & HTTP-Statuscodes
│   ├── requirements.txt                   # Backend- & ML-Abhängigkeiten
│   ├── api/
│   │   ├── routes.py                      # Hauptendpunkte (Rooms, Measurements, Metadata, Health)
│   │   ├── energy_forecast_routes.py      # Endpunkte für Energieprognosen
│   │   └── odata_helpers.py               # OData-Parser ($filter, $orderby,$top, $skip,$count)
│   ├── auth/
│   │   └── basic_auth.py                  # HTTP Basic Auth
│   ├── database/
│   │   ├── connection.py                  # PostgreSQL Connection Pool
│   │   └── queries.py                     # SQL-Query-Builder
│   ├── models/
│   │   └── measurement.py                 # Pydantic-Modelle
│   └── services/
│       ├── measurement_service.py         # Business-Logik für Raum- & Telemetriedaten
│       ├── energy_forecast_service.py     # Service-Layer für Energieprognosen
│       └── forecast_engine.py             # Prognose-Engine (NumPy, Pandas, Scikit-Learn)
├── dashboard/                             # Streamlit-Frontend
│   ├── app.py                             # Einstiegspunkt der Streamlit-Anwendung
│   ├── api_client.py                      # Zentraler HTTP-Client mit Basic Auth für FastAPI
│   ├── config.py                          # Dashboard-Konfiguration (API_BASE_URL, Auth, Timeout)
│   ├── .env.connection                    # Verbindungs-Parameter des Dashboards
│   ├── requirements.txt                   # Frontend-Abhängigkeiten (Streamlit, Plotly, etc.)
│   ├── components/                        # Wiederverwendbare UI- und Diagramm-Komponenten
│   └── pages/                             # Unterseiten (Raumklima, Wetter, Energie)
├── Documentation/                         # Projektdokumentation
│   ├── README.md                          # Schnellstart & Betriebsübersicht
│   ├── DOCUMENTATION.md                   # Ausführliche System- & Architekturdokumentation
│   ├── IMPORTANT_CODE_SNIPPETS.md         # Zentrale Code-Referenz
│   └── TESTING_STRATEGY.md                # Testkonzept & Pytest-Suite
├── tests/
│   └── test_api.py                        # Automatisierte API-Tests
├── start.sh                               # Kombiniertes Startskript für FastAPI & Streamlit
├── Dockerfile                             # Container-Image (Python 3.12-slim)
├── docker-compose.yml                     # Container-Orchestrierung (Ports 8000 & 8501)
└── README.md                              # Diese Datei
```

---

## Server-Betrieb & Steuerung (Docker)

1. **Per SSH auf dem Server anmelden:**
   ```bash
   ssh gruppe3@iwilsv-3.campus.fh-ludwigshafen.de
   cd /opt/kicagem
   ```

2. **Container bauen und im Hintergrund starten (empfohlen):**
   ```bash
   docker compose up -d --build
   ```

3. **Laufenden Status und Erreichbarkeit prüfen:**
   ```bash
   docker compose ps
   curl -i http://localhost:8000/api/health
   curl -I http://localhost:8501
   ```

4. **Logs live verfolgen:**
   ```bash
   docker compose logs -f --tail=50
   ```

5. **Container neu starten oder stoppen:**
   ```bash
   # Neustart ohne Neubau
   docker compose restart

   # Stoppen und Container entfernen
   docker compose down
   ```

6. **Neue Code-Änderungen von GitHub auf den Server einspielen:**
   ```bash
   cd /opt/kicagem
   git pull
   docker compose up -d --build
   ```

---

## Konfiguration & Zugangsdaten

- **Keine `.env`-Datei im Hauptverzeichnis nötig:** Alle erforderlichen Datenbank- und API-Zugangsdaten sind direkt in `app/config.py` (Backend) sowie `dashboard/config.py` und `dashboard/.env.connection` (Dashboard) hinterlegt.
- **Interne Kommunikation:** Da FastAPI und Streamlit im selben Container laufen, kommuniziert `dashboard/api_client.py` über `http://localhost:8000` direkt mit dem Backend.
- **Anmeldung in Swagger UI (`/docs`):**
  1. Öffne `http://iwilsv-3.campus.fh-ludwigshafen.de:8000/docs`.
  2. Klicke oben rechts auf **Authorize** (oder auf das Schloss-Symbol neben einem Endpunkt).
  3. Gib den in `app/config.py` hinterlegten Benutzernamen und das Passwort ein und bestätige mit **Authorize**.

---

## API-Nutzung & OData-Konventionen

### OData-Konventionen & Beispiel-Links

- **Alle Räume abfragen:**  
  `/api/Rooms?$top=10&$skip=0`
- **Einzelnen Raum abfragen:**  
  `/api/Rooms('A203')` bzw. `/api/Rooms('C1.003')`
- **Messwerte für einen Raum (mit Zeitfenster, Filter & Sortierung):**  
  `/api/Rooms('C1.003')/Measurements?StartDateTime=2026-11-18T00:00:00Z&EndDateTime=2026-11-19T00:00:00Z&$filter=SensorTypeCode eq 'temperature'&$orderby=StartDateTime desc&$top=5&$skip=0`
- **OData-Metadaten abrufen:**  
  `/api/$metadata`
- **System- & Datenbankstatus prüfen:**  
  `/api/health`

### Beispiel-Request (`curl`)

```bash
curl -u <BENUTZERNAME>:<PASSWORT> \
  "[http://iwilsv-3.campus.fh-ludwigshafen.de:8000/api/Rooms('C1.003')/Measurements?StartDateTime=2026-11-18T00:00:00Z&EndDateTime=2026-11-19T00:00:00Z](http://iwilsv-3.campus.fh-ludwigshafen.de:8000/api/Rooms('C1.003')/Measurements?StartDateTime=2026-11-18T00:00:00Z&EndDateTime=2026-11-19T00:00:00Z)&\$filter=SensorTypeCode%20eq%20'temperature'&\$top=5"
```

### Wichtige Query-Parameter

- **StartDateTime** (Pflicht bei Messwerten): ISO-8601-Datum/Zeit (z. B. `2026-11-18T00:00:00Z`)
- **EndDateTime** (Pflicht bei Messwerten): ISO-8601-Datum/Zeit
- **$filter** (optional): OData-Filterausdruck (z. B. `SensorTypeCode eq 'temperature'` oder `MeasureContent gt 22`)
- **$orderby** (optional): Sortierung (z. B. `StartDateTime desc`)
- **$top** (optional): Limit (max. `1000`)
- **$skip** (optional): Offset für Pagination
- **$count** (optional): Rückgabe der Gesamtanzahl (`true` / `false`)

---

## Lokale Installation & Entwicklung

1. **Repository klonen und in das Projektverzeichnis wechseln:**
   ```bash
   git clone [https://github.com/ouafo/IoT_API_Entwicklung.git](https://github.com/ouafo/IoT_API_Entwicklung.git)
   cd IoT_API_Entwicklung
   ```

2. **Virtuelle Umgebung erstellen und aktivieren:**
   ```bash
   python3 -m venv .venv
   # macOS / Linux:
   source .venv/bin/activate
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   ```

3. **Abhängigkeiten für Backend und Dashboard installieren:**
   ```bash
   pip install -r app/requirements.txt
   pip install -r dashboard/requirements.txt
   ```

4. **Backend und Dashboard lokal starten (in zwei getrennten Terminals mit aktivierter `.venv`):**
   ```bash
   # Terminal 1 – FastAPI-Backend (http://localhost:8000/docs)
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

   # Terminal 2 – Streamlit-Dashboard (http://localhost:8501)
   streamlit run dashboard/app.py
   ```

---

## Tests ausführen

```bash
pytest tests/ -v
```

Mit Coverage-Bericht:
```bash
pytest tests/ --cov=app
```

---

## Logging & Health-Check

### Logging
Logs werden im strukturierten JSON-Format ausgegeben:
- **Konsole (`stdout`):** Alle Logs (einsehbar über `docker compose logs`)
- **Datei:** `logs/app.log` (automatische Rotation bei 10 MB, bis zu 5 Backups)

### Container Health-Check
```bash
docker inspect kicagem-api --format='{{.State.Health.Status}}'
```

---

## Weiterführende Dokumentation

- **`Documentation/DOCUMENTATION.md`** – Ausführliche technische Systemdokumentation, Architektur, OData-Details und Fehlerbehebung
- **`Documentation/IMPORTANT_CODE_SNIPPETS.md`** – Zentrale Code-Referenz (Lifespan, DB-Pool, Exceptions, API-Client, Startskript)
- **`Documentation/TESTING_STRATEGY.md`** – Teststrategie, bestehende Pytest-Suite und Erweiterungsplan