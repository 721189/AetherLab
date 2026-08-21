import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

import httpx
import openai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("app.ai.providers")

# Timeout applied to the underlying HTTP client for every LLM request. A hard
# cap prevents a hung upstream endpoint from blocking a request indefinitely.
HTTP_TIMEOUT = httpx.Timeout(30.0)

# Exceptions considered transient (network timeouts/errors, rate limits and
# 5xx server errors). These are safe to retry without corrupting state.
TRANSIENT_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.TransportError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)

# Shared tenacity policy: retry transient failures up to 3 times with
# exponential backoff (1s → 2s → 4s), re-raising after the final attempt.
retry_transient = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


def with_fallback(
    primary: Callable[[], Any],
    fallback: Callable[[], Any],
    primary_label: str,
    fallback_label: str,
) -> Any:
    """Run ``primary``; on any exception log and run ``fallback``.

    Used to degrade to a smaller / free model when the primary one fails after
    retries, so a single provider outage does not break chat end-to-end.
    """
    try:
        return primary()
    except Exception:
        logger.warning(
            "LLM primary (%s) failed; falling back to (%s)",
            primary_label,
            fallback_label,
            exc_info=True,
        )
        return fallback()


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Generate a complete response from the LLM."""
        raise NotImplementedError

    @abstractmethod
    def stream_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        """Yield response chunks from the LLM as an iterator."""
        raise NotImplementedError
