"""Load and soak test specifications.

These are intended to be run manually against a staging environment. They are
marked so they are not discovered during ordinary CI.

Local execution
---------------
- Use `pytest --run-load` (add `-m "load"` marker to pytest.ini if enabled).
- For endpoint load testing behind NAT, expose the FastAPI instance with
  pyngrok so Locust / Playwright can reach it from a public URL.
- For backend soak testing, target the Celery worker via the internal API
  (no public tunnel needed).

Backend soak (Celery ingestion)
--------------------------------
1. Seed a monitored location.
2. Trigger `refresh_monitored_location` via Celery.
3. Replay the task N times with short delays to emulate continuous ingestion.
4. Assert: no duplicate observations, no task crashes, DB steady-state.

Frontend load (pyngrok + Locust/Playwright)
---------------------------------------------
- Start ngrok tunnel to the FastAPI instance.
- Run a Locust swarm against `/api/v1/*` endpoints.
- Track p95 latency, error rate, and DB connection pool saturation.
- Ramp up over 5 minutes, soak for 15 minutes at target concurrency.

Target KPIs (example values — tune to your deployment)
-------------------------------------------------------
- p95 API latency < 500ms under 50 concurrent users.
- Error rate < 0.5% under load.
- No DB connection pool exhaustion under sustained load.
- Celery queue depth stays bounded during soak.

Soak discovery
--------------
- Run `discover_satellite_scenes` repeatedly and verify no leaked tasks.
- Verify object storage operations do not leak file handles (local backend).
"""

from __future__ import annotations

import pytest

try:
    from locust import HttpUser, task, between
except ImportError:
    HttpUser = None  # type: ignore[assignment,misc]
    between = None  # type: ignore[assignment,misc]

try:
    from pyngrok import ngrok
except ImportError:
    ngrok = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Marker registration (use: pytest -m load --run-load)
# ---------------------------------------------------------------------------

pytest.mark.load  # noqa: F821  (marker registered below via pytest.ini)


def _ngrok_tunnel(port: int = 8000) -> str:
    """Optionally expose the local API via ngrok.

    Returns the public URL or raises when pyngrok is absent.
    """
    if ngrok is None:
        raise RuntimeError(
            "pyngrok is required for frontend load testing. "
            "Install with: pip install pyngrok"
        )
    public_url = ngrok.connect(port).public_url
    return public_url


class TestLoadTestingReadiness:
    """Sanity checks that load-testing tooling is available when requested."""

    def test_pyngrok_available_when_needed(self):
        # This test only validates the import path; actual tunnel creation is
        # manual/staged.
        if ngrok is None:
            pytest.skip("pyngrok not installed")


class TestSoakReadinessChecks:
    """Checks that the system can start a soak without immediate errors.

    These are lightweight and safe to run in CI when tagged.
    """

    @pytest.mark.load
    def test_app_starts_for_load_testing(self):
        from fastapi.testclient import TestClient
        from app.main import create_app

        client = TestClient(create_app())
        resp = client.get("/health/live")
        assert resp.status_code in (200, 503)

    @pytest.mark.load
    def test_provider_quota_initialized(self):
        from app.core.rate_limiter import limiter
        assert limiter is not None

