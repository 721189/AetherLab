"""Celery application for AetherLab background & periodic tasks.

The Celery app is deliberately kept in its own module (``app.tasks.celery_app``)
so workers can be started with the conventional

    celery -A app.tasks.celery_app worker --loglevel=info
    celery -A app.tasks.celery_app beat   --loglevel=info

without importing the FastAPI application. Only ``app.core.config.settings``
is imported at module scope, which is cheap and side-effect free.

Both the broker and the result backend point at Redis (``settings.REDIS_URL``):
Redis is already a hard dependency of the rate limiter, so no extra
infrastructure is introduced.

Beat schedule
-------------
A single periodic entry collects environmental readings (weather + air
quality) for every monitored location every 15 minutes.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (kept for future schedules)

from app.core.config import settings

#: Interval (seconds) between scheduled environmental collections: 15 minutes.
ENVIRONMENTAL_COLLECTION_INTERVAL_SECONDS = 900.0

celery_app = Celery(
    "aetherlab",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    # Task modules that must be imported so their ``@celery_app.task``
    # decorators register against this app in both worker and beat processes.
    include=["app.tasks.environmental"],
)

celery_app.conf.update(
    # Serialisation -- JSON only, never pickle (arbitrary code execution risk).
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Never silently drop messages: workers ack only after a task completes,
    # so a crash mid-task re-queues the work instead of losing it.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Periodic schedule (Celery Beat).
    beat_schedule={
        "fetch-environmental-data-every-15-min": {
            "task": "app.tasks.environmental.collect_all_locations",
            "schedule": ENVIRONMENTAL_COLLECTION_INTERVAL_SECONDS,
        },
    },
)
