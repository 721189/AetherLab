"""Tests for LLM provider factory resolution (OpenRouter/Nemotron vs OpenAI)."""
import pytest

from app.ai import factory
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.openrouter import OpenRouterProvider


class TestProviderResolution:
    def test_prefers_openrouter_when_key_present(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "router-key")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        provider = factory.get_llm_provider()
        assert isinstance(provider, OpenRouterProvider)

    def test_falls_back_to_openai_without_router_key(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        provider = factory.get_llm_provider()
        assert isinstance(provider, OpenAIProvider)

    def test_default_model_is_free_nemotron(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "router-key")
        monkeypatch.setattr(factory.settings, "LLM_MODEL", "")
        provider = factory.get_llm_provider()
        assert provider.model == factory.DEFAULT_NEMOTRON_MODEL

    def test_explicit_model_wins(self, monkeypatch):
        monkeypatch.setattr(factory.settings, "OPENROUTER_API_KEY", "router-key")
        provider = factory.get_llm_provider(model="nvidia/nemotron-3-ultra-550b-a55b")
        assert provider.model == "nvidia/nemotron-3-ultra-550b-a55b"

    def test_openrouter_provider_requires_key(self, monkeypatch):
        monkeypatch.setattr("os.getenv", lambda k, d=None: d or "")
        provider = OpenRouterProvider(api_key="")
        with pytest.raises(ValueError):
            _ = provider.client
