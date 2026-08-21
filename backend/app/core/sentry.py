"""Sentry initialization for the AetherLab backend.

Sentry is only activated when ``SENTRY_DSN`` is configured (i.e. in
production). When the DSN is empty, :func:`init_sentry` is a no-op and the
SDK is never initialised — so tests and local development are unaffected and
there is no extra dependency surface at runtime.

Two cross-cutting concerns are handled here:

* **Request-ID propagation** — every Sentry event is tagged with the
  request-scoped ``request_id`` (see :mod:`app.core.logging`), so failures can
  be correlated back to a single request's JSON logs.
* **Sensitive-data scrubbing** — well-known secret keys are redacted from the
  ``extra`` / ``request`` / ``user`` payloads before an event leaves the host,
  complementing the log-level ``SensitiveDataFilter``.
"""

from __future__ import annotations

import logging
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.stdlib import StdlibIntegration

from app.core.config import settings
from app.core.logging import (
    SENSITIVE_KEYS,
    SENSITIVE_FIELD_VALUE,
    SENSITIVE_SUBSTRINGS,
    _request_id_var,
)


def _redact_string(text: str) -> str:
    if not isinstance(text, str):
        return text
    for secret in SENSITIVE_SUBSTRINGS:
        if secret:
            text = text.replace(secret, SENSITIVE_FIELD_VALUE)
    return text


def _scrub(value: Any) -> Any:
    """Recursively redact sensitive keys and secret substrings."""
    if isinstance(value, dict):
        return {
            k: (
                SENSITIVE_FIELD_VALUE
                if isinstance(k, str) and k.lower() in SENSITIVE_KEYS
                else _scrub(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


def before_send(event: dict, hint: Any) -> dict | None:
    """Attach the request ID and scrub sensitive data before an event is sent."""
    event.setdefault("tags", {})
    event["tags"]["request_id"] = _request_id_var.get()

    for key in ("extra", "request", "user"):
        if isinstance(event.get(key), dict):
            event[key] = _scrub(event[key])

    return event


def init_sentry() -> None:
    """Configure Sentry from settings.

    A no-op when no ``SENTRY_DSN`` is provided. Any failure is swallowed and
    logged so that observability can never break application startup.
    """
    if not settings.SENTRY_DSN:
        return

    try:
        # Route Python stdlib logging warnings/errors into Sentry so tracebacks
        # and ``logger.exception`` calls are captured without extra wiring.
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        )

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            release=settings.SENTRY_RELEASE or None,
            send_default_pii=settings.SENTRY_SEND_DEFAULT_PII,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            attach_stacktrace=True,
            integrations=[
                FastApiIntegration(),
                StdlibIntegration(),
                SqlalchemyIntegration(),
                sentry_logging,
            ],
            before_send=before_send,
        )
        logging.getLogger("app.sentry").info(
            "Sentry initialised (environment=%s, release=%s, sample_rate=%s)",
            settings.APP_ENV,
            settings.SENTRY_RELEASE,
            settings.SENTRY_TRACES_SAMPLE_RATE,
        )
    except Exception as exc:  # never let observability break startup
        logging.getLogger("app.sentry").warning(
            "Sentry initialization failed: %s", exc
        )
