"""Prometheus metrics integration for the AetherLab backend.

Provides two pieces of cross-cutting instrumentation:

* :class:`PrometheusMiddleware` -- a raw ASGI middleware counting every HTTP
  request and recording its latency, partitioned by method, templated endpoint
  and response status.
* a ``GET /metrics`` endpoint serving the scraped metrics in the Prometheus
  text exposition format.

Public entry point: :func:`register_metrics`, called once from
:mod:`app.main` (same convention as ``register_exception_handlers`` and
``init_sentry``).

Design notes
------------
* ``/metrics`` is exempt from slowapi rate limiting and is **not** counted by
  the middleware, avoiding a self-referential feedback loop.
* Labels use the *templated* route path (e.g. ``/projects/{project_id}``)
  rather than the raw URL so metric cardinality stays bounded regardless of
  how many distinct resource IDs are requested. Unrouted requests (e.g. 404s)
  fall back to the raw request path.
* The middleware is native ASGI (not ``BaseHTTPMiddleware``): accurate latency
  (no thread-pool hop) and untouched streaming (the SSE reply stream).
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, List

from fastapi import FastAPI, Request, Response
from prometheus_client import REGISTRY, Counter, Histogram, generate_latest
from starlette.types import ASGIApp, Receive, Scope

# Metric definitions (registered against the default global REGISTRY).
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests, partitioned by method, endpoint and response status.",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, partitioned by method and endpoint.",
    ["method", "endpoint"],
)

METRICS_PATH = "/metrics"


def _resolve_endpoint(scope: Scope) -> str:
    """Return the templated endpoint path for a request.

    Prefers the matched route's path template. Falls back to the raw request
    path when no route matched (e.g. an unknown URL that produced a 404).
    """
    route = scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return scope.get("path", "/")


class PrometheusMiddleware:
    """ASGI middleware recording request counts and latency."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Callable[[Any], Awaitable[None]]
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")
        # Never instrument the metrics endpoint itself -- doing so would turn
        # every scrape into an incrementing counter (a feedback loop) and
        # pollute dashboards with scrape traffic.
        if path == METRICS_PATH:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        start = time.perf_counter()
        # Default to 500: if no ``http.response.start`` was observed (i.e. the
        # request failed before a response was produced) we still record the
        # request, classified as a server error. Overwritten on response start.
        status_code: List[int] = [500]

        async def _record_status(message: Any) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, _record_status)
        finally:
            duration = time.perf_counter() - start
            endpoint = _resolve_endpoint(scope)
            REQUEST_COUNT.labels(
                method=method, endpoint=endpoint, status=str(status_code[0])
            ).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


async def metrics_endpoint(request: Request) -> Response:
    """Serve Prometheus metrics in the text exposition format.

    The endpoint is deliberately unauthenticated and exempt from rate limiting
    so that a local Prometheus instance can scrape it. In hardened deployments
    protect it with a reverse proxy or bind it to an internal interface; see
    the README "Observability" section.
    """
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def register_metrics(app: FastAPI) -> None:
    """Register the Prometheus middleware and ``/metrics`` route on ``app``.

    Must be called once during application startup, after the app has been
    constructed.
    """
    # Exempt the metrics endpoint from slowapi rate limiting so frequent
    # scrapes never trip a 429. ``limiter.exempt`` preserves the endpoint's
    # identity so slowapi's route matching still exempts it.
    from app.core.rate_limiter import limiter

    limiter.exempt(metrics_endpoint)

    # Registered last so it becomes the outermost middleware, observing the
    # full request lifecycle (including CORS / rate limiting) and counting
    # rejected (429) responses as well.
    app.add_middleware(PrometheusMiddleware)

    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        tags=["observability"],
        summary="Prometheus metrics scrape endpoint",
        description=(
            "Returns service metrics in the Prometheus text exposition "
            "format. This endpoint is unauthenticated and exempt from rate "
            "limiting for simplicity; protect it with a reverse proxy or bind "
            "it to an internal interface in production."
        ),
    )
