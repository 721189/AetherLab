import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any
from contextlib import contextmanager

from app.core.config import settings

# Holds the request ID for the current request context.
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


@contextmanager
def request_id_context(request_id: str):
    """Run a block with the given request ID bound to the current context."""
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach the context-bound request ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


# Values that must never appear in logs, even partially.
SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "authorization",
    "database_url",
    "jwt",
}

# Substrings matched against the raw message for redaction.
SENSITIVE_SUBSTRINGS = [
    settings.SECRET_KEY,
]

SENSITIVE_FIELD_VALUE = "[REDACTED]"


class SensitiveDataFilter(logging.Filter):
    """Redact passwords, tokens, keys, and secret material from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.msg)
        if record.args:
            args = self._redact(record.args)
            record.args = args
        if hasattr(record, "exc_text") and record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        return True

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._redact_value(k, v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self._redact(item) for item in value)
        if isinstance(value, str):
            return self._redact_string(value)
        return value

    def _redact_value(self, key: Any, value: Any) -> Any:
        if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
            return SENSITIVE_FIELD_VALUE
        return self._redact(value)

    def _redact_string(self, text: str) -> str:
        for secret in SENSITIVE_SUBSTRINGS:
            if secret:
                text = text.replace(secret, SENSITIVE_FIELD_VALUE)
        return text


class JsonFormatter(logging.Formatter):
    """Emit structured JSON log records for production."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": settings.APP_NAME,
            "environment": settings.APP_ENV,
            "request_id": getattr(record, "request_id", None),
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)

        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """Configure logging for the application based on environment."""
    root = logging.getLogger()
    root.handlers.clear()

    level = logging.DEBUG if settings.DEBUG else logging.INFO
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(SensitiveDataFilter())
    handler.addFilter(RequestIdFilter())

    if settings.APP_ENV == "production":
        handler.setFormatter(JsonFormatter())
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(request_id)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)

    root.addHandler(handler)

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

