"""Tests for the Prometheus metrics integration (``app.core.metrics``).

The Prometheus registry is a process-wide singleton, so counters accumulate
across tests in the same session. These assertions therefore check for the
*presence* of correctly-labelled samples and monotonic growth rather than
exact values.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.core.metrics import REQUEST_COUNT, REQUEST_LATENCY
from app.main import app


def _scrape(client: TestClient) -> str:
    """Fetch and decode the ``/metrics`` exposition body."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # The Prometheus text exposition format is plain text.
    assert response.headers["content-type"].startswith("text/plain")
    return response.text


def _sample(body: str, series: str) -> float | None:
    """Return the value of a fully-qualified sample line (name + labels).

    ``series`` is the complete label selector, e.g.
    ``http_requests_total{endpoint="/",method="GET",status="200"}``.
    """
    match = re.search(rf"^{re.escape(series)}\s+([0-9.eE+-]+)$", body, re.M)
    return float(match.group(1)) if match else None



def test_metrics_endpoint_serves_prometheus_text(client: TestClient) -> None:
    body = _scrape(client)
    assert "# HELP http_requests_total" in body
    assert "# TYPE http_requests_total counter" in body
    assert "# HELP http_request_duration_seconds" in body


def test_metrics_endpoint_is_not_self_counted(client: TestClient) -> None:
    """Scraping ``/metrics`` must not increment its own request counter."""
    _scrape(client)  # warm-up scrape (also exercises the endpoint)
    body = _scrape(client)
    assert 'endpoint="/metrics"' not in body


def test_successful_requests_are_counted_and_timed(client: TestClient) -> None:
    """Hitting ``/`` increments the counter twice and records latency."""
    before = _sample(_scrape(client), 'http_requests_total{endpoint="/",method="GET",status="200"}') or 0.0

    first = client.get("/")
    second = client.get("/")
    assert first.status_code == 200
    assert second.status_code == 200

    body = _scrape(client)
    after = _sample(body, 'http_requests_total{endpoint="/",method="GET",status="200"}')
    assert after is not None, "expected an http_requests_total sample for '/'"
    assert after >= before + 2, f"counter should grow by >= 2, got {before} -> {after}"

    # Latency histogram: at least one observation bucket exists for '/'.
    assert re.search(
        r'http_request_duration_seconds_bucket\{[^}]*endpoint="/"',
        body,
    ), "expected histogram buckets for endpoint '/'"


def test_error_statuses_are_recorded_with_their_status_label(
    client: TestClient,
) -> None:
    """A 404 for an unknown URL is counted under status="404"."""
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404

    body = _scrape(client)
    # Unrouted requests have no route template, so they fall back to the raw path.
    assert (
        'http_requests_total{endpoint="/this-route-does-not-exist",method="GET",status="404"}'
        in body
    )


def test_templated_route_labels_bound_cardinality(client: TestClient) -> None:
    """Two different project IDs share one templated label value."""
    for project_id in (11111, 22222):
        response = client.get(f"/api/v1/projects/{project_id}")
        # 401 because no credentials are supplied -- the route still matched.
        assert response.status_code == 401

    body = _scrape(client)
    # Both IDs collapse onto the single templated endpoint label.
    assert (
        'http_requests_total{endpoint="/projects/{project_id}",method="GET",status="401"}'
        in body
    )
    # And neither raw URL appears as its own time series.
    assert 'endpoint="/api/v1/projects/11111"' not in body
    assert 'endpoint="/api/v1/projects/22222"' not in body


def test_metrics_are_registered_in_the_default_registry() -> None:
    """The two custom metrics live in the global registry used by /metrics."""
    # prometheus_client stores Counters internally without the ``_total``
    # suffix (it is re-appended in the text exposition), hence "http_requests".
    names = {metric.name for metric in REQUEST_COUNT.collect()} | {
        metric.name for metric in REQUEST_LATENCY.collect()
    }
    assert "http_requests" in names
    assert "http_request_duration_seconds" in names



def test_metrics_endpoint_is_exempt_from_rate_limiting() -> None:
    """/metrics is registered in slowapi's exempt set so scrapes never 429."""
    from app.core.metrics import metrics_endpoint
    from app.core.rate_limiter import limiter

    exempt_name = f"{metrics_endpoint.__module__}.{metrics_endpoint.__name__}"
    assert exempt_name == "app.core.metrics.metrics_endpoint"
    assert exempt_name in limiter._exempt_routes

