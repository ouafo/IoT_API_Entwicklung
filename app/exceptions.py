"""Custom Exceptions."""

from fastapi import status
from typing import Any, Dict, Optional


class TelemetryException(Exception):
    """Base Exception für Service."""
    
    def __init__(
        self,
        message: str,
        status_code: int = status. HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Optional[str] = None
    ):
        self.message = message
        self. status_code = status_code
        self.detail = detail or message
        super().__init__(self.message)


class InvalidSensorTypeException(TelemetryException):
    """Invalid sensor type."""
    
    def __init__(self, sensor_type: str, allowed_types: list):
        message = f"Invalid sensor type: '{sensor_type}'"
        detail = f"Muss einer sein:  {', '.join(allowed_types)}"
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class InvalidDatetimeException(TelemetryException):
    """Invalid datetime format."""
    
    def __init__(self, datetime_str: str, parameter_name: str):
        message = f"Invalid datetime in {parameter_name}"
        detail = f"Erwartet ISO8601 (z.B. 2025-01-01T00:00:00Z). Erhalten: '{datetime_str}'"
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class TimeRangeException(TelemetryException):
    """Invalid time range."""
    
    def __init__(self, start_time:  str, end_time: str):
        message = "Invalid time range: startTime muss vor endTime sein"
        detail = f"startTime ({start_time}) muss vor endTime ({end_time}) sein"
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class DatabaseException(TelemetryException):
    """Database error."""
    
    def __init__(self, error: str, original_error: Optional[Exception] = None):
        message = error or "Database operation failed"
        detail = error or "DB-Zugriff fehlgeschlagen"
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )
        self.original_error = original_error


class AuthenticationException(TelemetryException):
    """Authentication failed."""
    
    def __init__(self, reason:  str = "Invalid credentials"):
        message = "Authentication failed"
        detail = reason
        super().__init__(
            message=message,
            status_code=status. HTTP_401_UNAUTHORIZED,
            detail=detail
        )


class FilterException(TelemetryException):
    """Invalid OData filter."""
    
    def __init__(self, filter_str: str, error_details: str):
        message = "Invalid filter expression"
        detail = f"Filter parsing failed: {error_details}. Filter: '{filter_str}'"
        super().__init__(
            message=message,
            status_code=status. HTTP_400_BAD_REQUEST,
            detail=detail
        )


def create_error_response(
    status_code: int,
    message: str,
    detail:  Optional[str] = None
) -> Dict[str, Any]: 
    """Standardized error response."""
    return {
        "status_code": status_code,
        "message": message,
        "detail": detail or message,
        "type": "error"
    }