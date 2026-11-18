from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import DatabaseException
from app.routers import forecasts, health, rooms, weather


TAGS_METADATA = [
    {
        "name": "System",
        "description": "Systemstatus und Datenbank-Erreichbarkeit prüfen.",
    },
    {
        "name": "Räume & Messwerte",
        "description": "Metadaten, verfügbare Zeiträume und historische Sensordaten der Räume.",
    },
    {
        "name": "Wetterdaten",
        "description": "Historische Messwerte der campusweiten Wetterstationen.",
    },
    {
        "name": "Prognosen (+7 Tage)",
        "description": (
            "KI-gestützte 7-Tage-Wochenprognosen (gleicher Wochentag und gleiche Uhrzeit "
            "nächste Woche) für Raumklima, Energieverbrauch und Wetter."
        ),
    },
]

app = FastAPI(
    title="KICaGEM API – Campus-, Gebäude- und Energiemanagement",
    description=(
        "REST-API zur Abfrage historischer Raumklima-, Energie- und Wetterdaten sowie "
        "zur Berechnung von 7-Tage-Wochenprognosen auf Basis von PostgreSQL."
    ),
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
)


@app.exception_handler(DatabaseException)
async def database_exception_handler(request: Request, exc: DatabaseException):
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Datenbankfehler bei der Verarbeitung der Anfrage: {exc.message}",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fehler_details = [
        f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Ungültige Eingabeparameter: " + "; ".join(fehler_details),
        },
    )


app.include_router(health.router, prefix=settings.API_PREFIX, tags=["System"])
app.include_router(rooms.router, prefix=settings.API_PREFIX, tags=["Räume & Messwerte"])
app.include_router(weather.router, prefix=settings.API_PREFIX, tags=["Wetterdaten"])
app.include_router(forecasts.router, prefix=settings.API_PREFIX, tags=["Prognosen (+7 Tage)"])