"""FastAPI application factory."""

import time as time_module
from contextlib import asynccontextmanager
from typing import AsyncIterator
from datetime import datetime, time as datetime_time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from starlette.requests import Request

from app.api import (
    energy_forecast_routes,
    room_forecast_routes,
    routes,
    weather_routes,
    weather_forecast_routes,
)

from app.config import settings
from app.database import connection
from app.exceptions import TelemetryException, create_error_response
from app.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and close the database connection pool."""
    logger.info("Startup: Initializing DB pool")

    try:
        connection.init_db_pool()
        logger.info("DB pool initialized")

    except Exception as exc:
        logger.error("DB pool init failed", exc_info=exc)

    try:
        yield

    finally:
        logger.info("Shutdown: Closing DB pool")

        try:
            connection.close_db_pool()
            logger.info("DB pool closed")

        except Exception as exc:
            logger.error("DB pool close error", exc_info=exc)


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        description="IoT Analytics Service with OData URL Conventions",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Register API routers
    app.include_router(routes.router)
    app.include_router(energy_forecast_routes.router)
    app.include_router(room_forecast_routes.router)
    app.include_router(weather_routes.router)
    app.include_router(weather_forecast_routes.router)

    def custom_openapi():
        """Generate OpenAPI schema with required StartDateTime/EndDateTime pre-filled for Swagger UI."""
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # Pre-fill today 00:00:00 and current datetime so user can edit them in Swagger UI
        now = datetime.now().astimezone()
        start_datetime = datetime.combine(
            now.date(),
            datetime_time.min,
            tzinfo=now.tzinfo,
        )

        start_default = start_datetime.isoformat(timespec="seconds")
        end_default = now.isoformat(timespec="seconds")

        path = f"{settings.API_PREFIX}/Rooms('{{RoomID}}')/Measurements"
        if path in openapi_schema.get("paths", {}):
            parameters = openapi_schema["paths"][path]["get"].get("parameters", [])
            for parameter in parameters:
                if parameter["name"] == "StartDateTime":
                    parameter["required"] = True
                    parameter["example"] = start_default
                    parameter.setdefault("schema", {})["default"] = start_default
                elif parameter["name"] == "EndDateTime":
                    parameter["required"] = True
                    parameter["example"] = end_default
                    parameter.setdefault("schema", {})["default"] = end_default

        return openapi_schema

    app.openapi = custom_openapi

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log incoming HTTP requests."""
        start = time_module.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        finally:
            duration_ms = (time_module.perf_counter() - start) * 1000
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
                    "client": (
                        request.client.host
                        if request.client
                        else None
                    ),
                },
            )

    # Application-specific exception handler
    @app.exception_handler(TelemetryException)
    async def telemetry_exception_handler(
        request: Request,
        exc: TelemetryException,
    ):
        """Handle application-specific telemetry exceptions."""
        logger.error(
            f"Telemetry exception: {exc.message}",
            exc_info=exc,
        )

        response = create_error_response(
            status_code=exc.status_code,
            message=exc.message,
            detail=exc.detail,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response,
        )

    # General exception handler
    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ):
        """Handle unexpected exceptions."""
        logger.error(
            f"Unhandled exception: {str(exc)}",
            exc_info=exc,
        )

        response = create_error_response(
            status_code=500,
            message="Internal server error",
            detail="An unexpected error occurred",
        )

        return JSONResponse(
            status_code=500,
            content=response,
        )

    return app


app = create_app()