"""Structured logging configuration."""

import logging
import logging.handlers
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from contextvars import ContextVar
import uuid

from ..config.settings import settings

# Context variable for correlation ID
correlation_id: ContextVar[str] = ContextVar('correlation_id', default='')


class CorrelationIDFilter(logging.Filter):
    """Add correlation ID to log records."""
    
    def filter(self, record):
        record.correlation_id = correlation_id.get('')
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'correlation_id': getattr(record, 'correlation_id', ''),
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add extra fields if they exist
        if hasattr(record, 'method'):
            log_entry['method'] = record.method
        if hasattr(record, 'path'):
            log_entry['path'] = record.path
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = record.status_code
        if hasattr(record, 'response_time_ms'):
            log_entry['response_time_ms'] = record.response_time_ms
        if hasattr(record, 'ip'):
            log_entry['ip'] = record.ip
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'extra'):
            log_entry['extra'] = record.extra
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging():
    """Configure logging with proper handlers and formatting."""
    
    # Create logs directory structure
    logs_dir = Path("logs")
    for subdir in ["info", "error", "warning", "debug"]:
        (logs_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    # Remove default handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set root logger level
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Create correlation ID filter
    correlation_filter = CorrelationIDFilter()
    
    # JSON formatter
    json_formatter = JSONFormatter()
    
    # Console handler with JSON format for production, simple for development.
    # Windows consoles default to cp1252, so a job title with an em dash or a
    # non-Latin character raised UnicodeEncodeError inside logging itself and
    # buried the real output under tracebacks. Log lines are not worth losing
    # a character over, let alone a run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    console_handler = logging.StreamHandler(sys.stdout)
    if settings.environment == "development":
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
    else:
        console_handler.setFormatter(json_formatter)
    
    console_handler.addFilter(correlation_filter)
    root_logger.addHandler(console_handler)
    
    # File handlers for different log levels
    handlers_config = [
        {
            'filename': logs_dir / 'info' / 'info.log',
            'level': logging.INFO,
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 30  # Keep 30 days
        },
        {
            'filename': logs_dir / 'error' / 'error.log',
            'level': logging.ERROR,
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 30
        },
        {
            'filename': logs_dir / 'warning' / 'warning.log',
            'level': logging.WARNING,
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 30
        },
        {
            'filename': logs_dir / 'debug' / 'debug.log',
            'level': logging.DEBUG,
            'maxBytes': 20 * 1024 * 1024,  # 20MB for debug logs
            'backupCount': 7  # Keep 7 days only
        }
    ]
    
    for config in handlers_config:
        handler = logging.handlers.RotatingFileHandler(
            filename=config['filename'],
            maxBytes=config['maxBytes'],
            backupCount=config['backupCount'],
            encoding='utf-8'
        )
        handler.setLevel(config['level'])
        handler.setFormatter(json_formatter)
        handler.addFilter(correlation_filter)
        
        root_logger.addHandler(handler)
    
    # Suppress some noisy loggers
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logging.info("Logging system initialized")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


def set_correlation_id(correlation_id_value: str = None) -> str:
    """Set correlation ID for the current context."""
    if correlation_id_value is None:
        correlation_id_value = str(uuid.uuid4())
    
    correlation_id.set(correlation_id_value)
    return correlation_id_value


def get_correlation_id() -> str:
    """Get the current correlation ID."""
    return correlation_id.get('')


# Application logger
logger = get_logger(__name__)
