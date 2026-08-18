import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.ai.providers.base import LLMProvider

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set; configure it or pass api_key"
                )
            self._client = OpenAI(api_key=self._api_key)
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