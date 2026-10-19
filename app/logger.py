"""Application logging mit JSON output."""

import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone

LOG_LEVEL: str = os. getenv("LOG_LEVEL", "INFO")


class JSONFormatter(logging.Formatter):
    """JSON formatter für structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Log Record als JSON formatieren."""
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Extra fields aus record.__dict__ holen
        for key, value in record.__dict__. items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info"
            ]:
                log_obj[key] = value
        
        return json.dumps(log_obj, default=str)


def setup_logging() -> logging.Logger:
    """Logging konfigurieren."""
    os.makedirs("logs", exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    root_logger.handlers = []
    
    json_formatter = JSONFormatter()
    console_handler = logging. StreamHandler()
    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)
    
    file_handler = logging.handlers. RotatingFileHandler(
        "logs/app.log",
        maxBytes=10_485_760,
        backupCount=5,
    )
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)
    
    logger = logging.getLogger("app")
    logger.info("Logging initialized")
    return logger


logger = setup_logging()