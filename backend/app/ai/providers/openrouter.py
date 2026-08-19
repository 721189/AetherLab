import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.ai.providers.base import LLMProvider

# OpenRouter exposes an OpenAI-compatible chat-completions API.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Free / open Nemotron model exposed through OpenRouter (no charge per token).
# Override per-agent via the agent's `model` field or with LLM_MODEL.
DEFAULT_NEMOTRON_MODEL = "nvidia/nemotron-4-340b-base"


class OpenRouterProvider(LLMProvider):
    """OpenRouter LLM provider backed by free Nemotron models.

    OpenRouter is OpenAI-compatible, so the official OpenAI SDK is used with a
    custom base URL. Adding the HTTP-Referer / X-Title headers improves
    standing and is recommended by OpenRouter.
    """

    def __init__(
        self,
        model: str = DEFAULT_NEMOTRON_MODEL,
        api_key: Optional[str] = None,
        site_url: Optional[str] = None,
        app_name: str = "AetherLab",
    ) -> None:
        self.model = model
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

    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(messages, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def stream_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(messages, system_prompt),
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta is not None:
                yield delta
