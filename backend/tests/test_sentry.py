"""Tests for Sentry bootstrap (no network; SDK calls are mocked)."""

from types import SimpleNamespace
from unittest import mock

from app.core import sentry as sentry_mod


def _fake_settings(dsn="http://x@example.com/1"):
    return SimpleNamespace(
        SENTRY_DSN=dsn,
        SENTRY_RELEASE="release-1.0",
        SENTRY_SEND_DEFAULT_PII=False,
        SENTRY_TRACES_SAMPLE_RATE=0.1,
        APP_ENV="testing",
        APP_NAME="AetherLab API",
    )


def test_init_sentry_is_noop_without_dsn():
    """No DSN configured -> sentry_sdk.init must never be called."""
    fake = _fake_settings(dsn="")
    with mock.patch.object(sentry_mod, "settings", fake):
        with mock.patch("sentry_sdk.init") as init_mock:
            sentry_mod.init_sentry()
            init_mock.assert_not_called()


def test_init_sentry_initializes_when_dsn_configured():
    """A DSN is present -> sentry_sdk.init is called with the DSN + env."""
    fake = _fake_settings(dsn="http://x@example.com/1")
    with mock.patch.object(sentry_mod, "settings", fake):
        with mock.patch("sentry_sdk.init") as init_mock:
            sentry_mod.init_sentry()
            init_mock.assert_called_once()
            kwargs = init_mock.call_args.kwargs
            assert kwargs["dsn"] == "http://x@example.com/1"
            assert kwargs["environment"] == "testing"


def test_init_sentry_swallows_init_errors():
    """sentry_sdk.init raising must not crash the app bootstrap."""
    fake = _fake_settings(dsn="http://x@example.com/1")
    with mock.patch.object(sentry_mod, "settings", fake):
        with mock.patch("sentry_sdk.init", side_effect=RuntimeError("boom")):
            sentry_mod.init_sentry()  # must not raise


def test_before_send_tags_request_id_and_redacts_secrets():
    """before_send tags events with the current request_id and redacts secrets."""
    from app.core.logging import _request_id_var

    token = _request_id_var.set("req-123")
    try:
        event = {
            "tags": {},
            "extra": {"password": "hunter2", "detail": "boom"},
            "user": {"email": "a@b.com", "password": "secret"},
        }
        out = sentry_mod.before_send(event, None)
        assert out["tags"]["request_id"] == "req-123"
        # Sensitive keys have their *value* redacted (key preserved).
        assert out["extra"]["password"] == "[REDACTED]"
        assert out["user"]["password"] == "[REDACTED]"
        # Non-sensitive keys/values are preserved.
        assert out["extra"]["detail"] == "boom"
        assert out["user"]["email"] == "a@b.com"
    finally:
        _request_id_var.reset(token)
