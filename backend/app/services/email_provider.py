"""Pluggable email delivery.

Architecture:

    AuthService -> EmailProvider -> concrete provider

Keeping delivery behind this interface means the provider is replaceable
(Console for dev, Resend/Postmark/SES/SendGrid in production) without touching
the registration flow.

Dev convenience: :data:`OUTBOX` captures everything sent by the
:class:`ConsoleEmailProvider` so tests (and local development) can read the
verification link without a real mailbox.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("aetherlab.email")

# Captured dev-mode emails: list of {"to": ..., "subject": ..., "body": ...}.
OUTBOX: List[dict] = []


class EmailDeliveryError(Exception):
    """Raised when the configured provider fails to send an email."""


def verification_url(token: str) -> str:
    """Build the clickable verification link emailed to new users."""
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/verify-email?token={token}"


class EmailProvider(ABC):
    """Common interface for transactional email providers."""

    name: str = "abstract"

    @abstractmethod
    async def send_verification_email(self, to_email: str, token: str) -> None:
        """Deliver the verification email containing ``token``."""

    @staticmethod
    def _render_body(token: str) -> str:
        url = verification_url(token)
        return (
            "Welcome to AetherLab!\n\n"
            "Please confirm your email address by clicking the link below:\n"
            f"{url}\n\n"
            "This link expires in 24 hours. If you did not create an account, "
            "you can safely ignore this email.\n"
        )


class ConsoleEmailProvider(EmailProvider):
    """Development provider: logs the email and captures it in OUTBOX."""

    name = "console"

    async def send_verification_email(self, to_email: str, token: str) -> None:
        body = self._render_body(token)
        entry = {"to": to_email, "subject": "Verify your AetherLab account", "body": body}
        OUTBOX.append(entry)
        logger.info("DEV EMAIL to=%s:\n%s", to_email, body)


class ResendEmailProvider(EmailProvider):
    """Production provider backed by the Resend HTTP API."""

    name = "resend"

    def __init__(self, api_key: str, from_email: Optional[str] = None):
        self.api_key = api_key
        self.from_email = from_email or settings.EMAIL_FROM

    async def send_verification_email(self, to_email: str, token: str) -> None:
        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": "Verify your AetherLab account",
            "text": self._render_body(token),
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"Resend unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise EmailDeliveryError(
                f"Resend error {resp.status_code}: {resp.text[:200]}"
            )
        logger.info("Verification email sent to %s via Resend", to_email)


def get_email_provider() -> EmailProvider:
    """Choose the provider from configuration.

    RESEND_API_KEY set  -> ResendEmailProvider
    otherwise           -> ConsoleEmailProvider (dev: logged + captured)
    """
    if settings.RESEND_API_KEY:
        return ResendEmailProvider(settings.RESEND_API_KEY)
    return ConsoleEmailProvider()
