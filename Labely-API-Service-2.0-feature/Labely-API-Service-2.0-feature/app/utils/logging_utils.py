"""Centralized logging configuration for the Labely application."""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

class HealthCheckFilter(logging.Filter):
    """Filter out health check and root endpoint logs."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if this is an access log for health endpoints
        if hasattr(record, 'request_path'):
            path = record.request_path
            if path in ['/health', '/redis-status', '/']:
                return False
        
        # Also check message content for health-related patterns
        message = record.getMessage()
        if any(pattern in message.lower() for pattern in [
            'health check',
            'get /health',
            'get /redis-status',
            '"GET /health"',
            '"GET /redis-status"',
            '"GET / HTTP/1.1"',
        ]):
            return False
        
        return True

class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production environments."""

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Merge any extra fields attached to the record
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            log_record.update(extra)

        return json.dumps(log_record, default=str)


def setup_logging(level: str = "INFO", json_format: bool = False, log_to_file: bool = True) -> None:
    """
    Configure root logging for the application.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, emit structured JSON; otherwise emit human-readable text.
        log_to_file: If True, also write logs to a file.
    """
    root_logger = logging.getLogger()

    # Clear existing handlers
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Set log level
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Create formatters
    if json_format:
        formatter: logging.Formatter = JsonFormatter()
        file_formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Create health check filter
    health_filter = HealthCheckFilter()

    # Console handler (always enabled) - apply filter to console logs
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(health_filter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_to_file:
        # Create logs directory if it doesn't exist
        log_dir = os.getenv("LOG_DIR", "./logs")
        os.makedirs(log_dir, exist_ok=True)

        # Main application log file
        log_file = os.path.join(log_dir, "app.log")
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(health_filter)
        root_logger.addHandler(file_handler)

        # Error log file (only errors and above)
        error_log_file = os.path.join(log_dir, "error.log")
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        error_handler.addFilter(health_filter)
        root_logger.addHandler(error_handler)

        # Access log (for HTTP requests)
        access_log_file = os.path.join(log_dir, "access.log")
        access_handler = RotatingFileHandler(
            access_log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        )
        access_handler.setFormatter(file_formatter)
        access_handler.addFilter(health_filter)

        # Create a separate logger for access logs
        access_logger = logging.getLogger("uvicorn.access")
        access_logger.addHandler(access_handler)
        access_logger.addFilter(health_filter) # Ensure health check logs are filtered from access logs 

        print(f"Logging to file: {log_file}")

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
