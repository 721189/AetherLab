import os
from typing import Optional

from app.ai.providers.base import LLMProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.openrouter import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_NEMOTRON_MODEL,
    OpenRouterProvider,
)
from app.core.config import settings

# When set, model requests resolve against OpenRouter (hosting free
# Nemotron models) instead of the paid OpenAI API.
OPENROUTER_ENV_KEY = "OPENROUTER_API_KEY"


def get_llm_provider(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """Factory to get an LLM provider based on configured keys + model name.

    Resolution order:
      1. If an OpenRouter API key is available, use OpenRouter (free Nemotron
         by default) — override via settings.LLM_MODEL or an explicit model.
      2. Otherwise fall back to OpenAI.

    A fallback model (settings.LLM_FALLBACK_MODEL or the provider's built-in
    smaller / free tier model) is wired so a failed primary can degrade.
    """
    default_model = settings.LLM_MODEL or DEFAULT_NEMOTRON_MODEL

    router_key = api_key or settings.OPENROUTER_API_KEY
    if router_key:
        resolved_model = model or default_model
        fallback = settings.LLM_FALLBACK_MODEL or DEFAULT_FALLBACK_MODEL
        return OpenRouterProvider(
            model=resolved_model,
            api_key=router_key,
            fallback_model=fallback,
        )

    openai_key = api_key or os.getenv("OPENAI_API_KEY")
    resolved_model = model or default_model or "gpt-4o"
    fallback = settings.LLM_FALLBACK_MODEL or OpenAIProvider.DEFAULT_FALLBACK_MODEL
    return OpenAIProvider(
        model=resolved_model,
        api_key=openai_key,
        fallback_model=fallback,
    )