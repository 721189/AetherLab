from typing import Optional

from app.ai.providers.base import LLMProvider
from app.ai.providers.openai import OpenAIProvider


def get_llm_provider(
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
) -> LLMProvider:
    """Factory to get an LLM provider based on the requested model name.

    Currently only OpenAI is supported, but the list can be extended with
    additional providers without changing callers.
    """
    return OpenAIProvider(model=model, api_key=api_key)