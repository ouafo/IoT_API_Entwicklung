# Important Code Snippets - KICAGEM IoT Analytics Service

## app/main.py
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan."""
    logger.info("Startup: DB Pool initialisieren")
    try:
        connection.init_db_pool()
        logger.info("DB Pool initialisiert")
    except Exception as exc:
        logger.error("DB Pool init failed", exc_info=exc)
    try:
        yield
    finally: 
        logger.info("Shutdown: DB Pool schlieen")
        try:
            connection.close_db_pool()
            logger.info("DB Pool geschlossen")
        except Exception as exc: 
            logger.error("DB Pool close error", exc_info=exc)

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        description="IoT Analytics Service mit OData URL Conventions",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    app.include_router(routes.router)
    # ...middleware and error handler...
    return app
```

## app/api/routes.py
```python
@router.get("/health")
async def health_check():
    db_status = "unknown"
    try:
        import time
        start = time.perf_counter()
        conn = connection.get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            db_status = "ok"
        finally:
            connection.put_conn(conn)
    except Exception:
        db_status = "error"
    return {"status": "healthy", "db": db_status}
```

## app/database/connection.py
```python
def _make_conn() -> psycopg.Connection:
    connection_params = {
        "host": settings.DB_HOST,
        "port": int(settings.DB_PORT) if settings.DB_PORT else None,
        "dbname": settings.DB_NAME,
        "user": settings.DB_USER,
        "password":  settings.DB_PASSWORD,
    }
    connection_params = {k: v for k, v in connection_params.items() if v is not None}
    conn = psycopg.connect(**connection_params)
    if settings.DB_SCHEMA:
        try:
            cur = conn.cursor()
            cur.execute(f"SET search_path TO {settings.DB_SCHEMA}, public")
            conn.commit()
            logger.debug(f"Schema gesetzt: {settings.DB_SCHEMA}")
        except Exception as e:
            logger.warning(f"Schema-Set fehlgeschlagen: {e}")  
    return conn
```

## app/exceptions.py
```python
class TelemetryException(Exception):
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)

class InvalidSensorTypeException(TelemetryException):
    def __init__(self, sensor_type: str, allowed_types: list):
        message = f"Invalid sensor type: '{sensor_type}'"
        detail = f"Muss einer sein:  {', '.join(allowed_types)}"
        super().__init__(message=message, status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
```
