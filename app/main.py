"""FastAPI application factory."""

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.api import routes, weather_routes #"neuer import" 

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.config import settings
from app.api import routes
from app.database import connection
from app.logger import logger
from app.exceptions import TelemetryException, create_error_response


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
        logger.info("Shutdown: DB Pool schließen")
        try:
            connection.close_db_pool()
            logger.info("DB Pool geschlossen")
        except Exception as exc: 
            logger.error("DB Pool close error", exc_info=exc)


def create_app() -> FastAPI:
    """FastAPI App erstellen."""
    app = FastAPI(
        title=settings. API_TITLE,
        version=settings.API_VERSION,
        description="IoT Analytics Service mit OData URL Conventions",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    app.include_router(routes.router)
    app.include_router(weather_routes.router)

    @app.middleware("http")
    async def log_requests(request:  Request, call_next):
        """Request Logging."""
        start = time.perf_counter()
        status_code = 500
        try: 
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            log_level = logger.info
            if 400 <= status_code < 500:
                log_level = logger.warning
            elif status_code >= 500:
                log_level = logger.error

            log_level(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 2),
                    "client": request.client. host if request.client else None,
                },
            )

    @app.exception_handler(TelemetryException)
    async def telemetry_exception_handler(request: Request, exc: TelemetryException):
        """Custom Exception Handler."""
        logger.error(f"Telemetry exception:  {exc.message}", exc_info=exc)
        response = create_error_response(
            status_code=exc.status_code,
            message=exc.message,
            detail=exc.detail
        )
        return JSONResponse(status_code=exc.status_code, content=response)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc:  Exception):
        """Unhandled Exception Handler."""
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
        response = create_error_response(
            status_code=500,
            message="Internal server error",
            detail="An unexpected error occurred"
        )
        return JSONResponse(status_code=500, content=response)

    return app


app = create_app()