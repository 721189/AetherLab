import os
from typing import Any, Dict, List, Optional

import httpx
from openai import OpenAI

from app.ai.providers.base import (
    HTTP_TIMEOUT,
    LLMProvider,
    logger,
    retry_transient,
    with_fallback,
)

# OpenRouter exposes an OpenAI-compatible chat-completions API.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Free / open Nemotron model exposed through OpenRouter (no charge per token).
# Override per-agent via the agent's `model` field or with LLM_MODEL.
DEFAULT_NEMOTRON_MODEL = "nvidia/nemotron-4-340b-base"

# Real small free model used as a fallback when the primary fails after
# retries, so chat keeps working if the primary endpoint is overloaded.
DEFAULT_FALLBACK_MODEL = "meta-llama/llama-3.1-8b-instruct:free"


class OpenRouterProvider(LLMProvider):
    """OpenRouter LLM provider backed by free Nemotron models.

    OpenRouter is OpenAI-compatible, so the official OpenAI SDK is used with a
    custom base URL. Adding the HTTP-Referer / X-Title headers improves
    standing and is recommended by OpenRouter. Requests carry a bounded timeout
    and transient failures are retried (tenacity) before falling back to a
    smaller free tier model.
    """

    def __init__(
        self,
        model: str = DEFAULT_NEMOTRON_MODEL,
        api_key: Optional[str] = None,
        site_url: Optional[str] = None,
        app_name: str = "AetherLab",
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
    ) -> None:
        self.model = model
        self.fallback_model = fallback_model
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self._site_url = site_url or os.getenv(
            "OPENROUTER_SITE_URL", "https://aetherlab.app"
        )
        self._app_name = app_name
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY is not set; configure it or pass api_key"
                )
            self._client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=self._api_key,
                timeout=HTTP_TIMEOUT,
                max_retries=0,
                default_headers={
                    "HTTP-Referer": self._site_url,
                    "X-Title": self._app_name,
                },
            )
        return self._client

    def _build_messages(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
    ) -> List[Dict[str, str]]:
        full = []
        if system_prompt:
            full.append({"role": "system", "content": system_prompt})
        full.extend(messages)
        return full

    @retry_transient
    def _complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=self._build_messages(messages, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        primary = lambda: self._complete(
            self.model, messages, system_prompt, temperature, max_tokens, **kwargs
        )
        if self.fallback_model and self.fallback_model != self.model:
            fallback = lambda: self._complete(
                self.fallback_model,
                messages,
                system_prompt,
                temperature,
                max_tokens,
                **kwargs,
            )
            return with_fallback(
                primary, fallback, self.model, self.fallback_model
            )
        return primary()

    @retry_transient
    def _open_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any,
    ):
        return self.client.chat.completions.create(
            model=model,
            messages=self._build_messages(messages, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            stream=True,
            **kwargs,
        )

    def stream_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        for idx, model in enumerate(models):
            yielded_any = False
            try:
                stream = self._open_stream(
                    model, messages, system_prompt, temperature, max_tokens, **kwargs
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta is not None:
                        yielded_any = True
                        yield delta
                return
            except Exception:
                if yielded_any or idx == len(models) - 1:
                    raise
                logger.warning(
                    "Streaming with %s failed before output; falling back to %s",
                    model,
                    models[idx + 1],
                )
