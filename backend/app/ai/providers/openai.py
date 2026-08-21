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

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider with timeout, retry and fallback."""

    # Smaller/cheaper model used when the configured model fails after retries.
    DEFAULT_FALLBACK_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
    ) -> None:
        self.model = model
        self.fallback_model = fallback_model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set; configure it or pass api_key"
                )
            # A bounded timeout (see HTTP_TIMEOUT) prevents a hung upstream from
            # blocking indefinitely; max_retries is left to tenacity below.
            self._client = OpenAI(
                api_key=self._api_key,
                timeout=HTTP_TIMEOUT,
                max_retries=0,
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
                # Only degrade to the next model before any content has been
                # delivered; mid-stream errors are surfaced to avoid emitting
                # duplicate tokens.
                if yielded_any or idx == len(models) - 1:
                    raise
                logger.warning(
                    "Streaming with %s failed before output; falling back to %s",
                    model,
                    models[idx + 1],
                )