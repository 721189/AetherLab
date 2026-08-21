import httpx
import pytest

from app.ai import factory
from app.ai.providers.base import HTTP_TIMEOUT
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.openrouter import (
    DEFAULT_FALLBACK_MODEL,
    OpenRouterProvider,
)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Res:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Delta:
    def __init__(self, content):
        self.content = content


class _DeltaChoice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content):
        self.choices = [_DeltaChoice(content)]


class FakeCompletions:
    def __init__(self, handler):
        self.handler = handler

    def create(self, **kwargs):
        return self.handler(**kwargs)


class FakeOpenAIClient:
    """Minimal stand-in for the OpenAI client used to test retry/fallback."""

    def __init__(self, handler):
        self.chat = type("_Chat", (), {"completions": FakeCompletions(handler)})()


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    # Make tenacity exponential backoff instant so tests don't actually sleep.
    monkeypatch.setattr("time.sleep", lambda _: None)
class TestHTTPTimeout:
    def test_shared_timeout_is_30_seconds(self):
        assert HTTP_TIMEOUT.connect == 30.0
        assert HTTP_TIMEOUT.read == 30.0
        assert HTTP_TIMEOUT.write == 30.0
        assert HTTP_TIMEOUT.pool == 30.0

    def test_openai_client_passes_timeout_and_disables_sdk_retries(self, monkeypatch):
        captured = {}
        import app.ai.providers.openai as oai

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(oai, "OpenAI", FakeOpenAI)
        provider = oai.OpenAIProvider(api_key="sk-test")
        _ = provider.client
        assert captured["timeout"] == oai.HTTP_TIMEOUT
        assert captured["max_retries"] == 0

    def test_openrouter_client_passes_timeout(self, monkeypatch):
        captured = {}
        import app.ai.providers.openrouter as orp

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(orp, "OpenAI", FakeOpenAI)
        provider = orp.OpenRouterProvider(api_key="router-key")
        _ = provider.client
        assert captured["timeout"] == orp.HTTP_TIMEOUT
        assert captured["max_retries"] == 0
        assert captured["base_url"] == orp.OPENROUTER_BASE_URL


class TestRetry:
    def test_retries_transient_failure_then_succeeds(self):
        calls = {"n": 0}
        models = []

        def handler(**kwargs):
            calls["n"] += 1
            models.append(kwargs["model"])
            if calls["n"] < 3:
                raise httpx.ConnectTimeout("simulated timeout")
            return _Res("final")

        provider = OpenAIProvider(model="m1", api_key="k", fallback_model="m2")
        provider._client = FakeOpenAIClient(handler)

        result = provider.generate_response([{"role": "user", "content": "hi"}])
        assert result == "final"
        assert calls["n"] == 3  # initial + 2 retries
        assert set(models) == {"m1"}  # fallback model never used

    def test_non_transient_error_is_not_retried(self):
        calls = {"n": 0}
        models = []

        def handler(**kwargs):
            calls["n"] += 1
            models.append(kwargs["model"])
            raise ValueError("bad request - not transient")

        provider = OpenAIProvider(model="m1", api_key="k", fallback_model="m2")
        provider._client = FakeOpenAIClient(handler)

        with pytest.raises(ValueError):
            provider.generate_response([{"role": "user", "content": "hi"}])
        # Not retried: primary exactly once, then a single fallback attempt.
        assert models == ["m1", "m2"]


class TestFallback:
    def test_falls_back_to_smaller_model_after_primary_retries(self):
        models = []

        def handler(**kwargs):
            models.append(kwargs["model"])
            if kwargs["model"] == "primary-model":
                raise httpx.ConnectTimeout("primary down")
            return _Res("fallback reply")

        provider = OpenAIProvider(
            model="primary-model", api_key="k", fallback_model="fallback-model"
        )
        provider._client = FakeOpenAIClient(handler)

        result = provider.generate_response([{"role": "user", "content": "hi"}])
        assert result == "fallback reply"
        # Primary retried 3x, then fallback succeeded once.
        assert models == ["primary-model"] * 3 + ["fallback-model"]

    def test_stream_falls_back_before_any_output(self):
        models = []

        def handler(**kwargs):
            models.append(kwargs["model"])
            if kwargs["model"] == "primary":
                raise httpx.ConnectTimeout("primary down")
            return [_Chunk("A"), _Chunk("B")]

        provider = OpenAIProvider(
            model="primary", api_key="k", fallback_model="fallback"
        )
        provider._client = FakeOpenAIClient(handler)

        out = "".join(provider.stream_response([{"role": "user", "content": "hi"}]))
        assert out == "AB"
        assert models == ["primary"] * 3 + ["fallback"]

    def test_no_fallback_when_model_matches(self):
        calls = {"n": 0}

        def handler(**kwargs):
            calls["n"] += 1
            raise httpx.ConnectTimeout("down")

        provider = OpenAIProvider(model="m", api_key="k", fallback_model="m")
        provider._client = FakeOpenAIClient(handler)

        with pytest.raises(httpx.ConnectTimeout):
            provider.generate_response([{"role": "user", "content": "hi"}])
        assert calls["n"] == 3  # only the primary model is retried


class TestFactoryWiring:
    def test_openrouter_fallback_default(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "router-key")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        provider = factory.get_llm_provider()
        assert isinstance(provider, OpenRouterProvider)
        assert provider.fallback_model == DEFAULT_FALLBACK_MODEL

    def test_openai_provider_has_fallback(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        provider = factory.get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
        assert provider.fallback_model == OpenAIProvider.DEFAULT_FALLBACK_MODEL

