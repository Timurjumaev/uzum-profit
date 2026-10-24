"""Kirish kodini yetkazish (ADR-027, ADR-028).

Kodni ilova o'zi yaratadi va tekshiradi (xesh, urinishlar, blok — bazada); yetkazuvchi faqat yuboradi. Shu sabab
keyin SMS zaxira kanali (Eskiz va h.k.) xuddi shu interfeys bilan qo'shiladi.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from upapi.auth.tokens import mask_phone
from upapi.logs import get_logger
from upapi.settings import OtpSender, Settings

GATEWAY_URL = "https://gatewayapi.telegram.org"


class DeliveryError(Exception):
    """Kod yetkazilmadi. ``reason`` — provayder xato kodi (logga yoziladi, kod va token emas)."""

    def __init__(self, reason: str, *, not_on_telegram: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.not_on_telegram = not_on_telegram


class CodeSender(Protocol):
    async def send(self, phone: str, code: str, ttl_seconds: int) -> None: ...

    async def aclose(self) -> None: ...


@dataclass
class MemorySender:
    """Test va dev: kodlar xotirada; dev'da terminalga ham chiqariladi (logga emas)."""

    echo: bool = False
    outbox: list[tuple[str, str]] = field(default_factory=list)

    async def send(self, phone: str, code: str, ttl_seconds: int) -> None:
        self.outbox.append((phone, code))
        if self.echo:
            print(f"[dev] {phone} uchun kirish kodi: {code}", file=sys.stderr)

    def last_code(self, phone: str) -> str:
        return next(code for p, code in reversed(self.outbox) if p == phone)

    async def aclose(self) -> None:
        return None


# Telegram Gateway xato kodlari: raqam Telegram'da yo'q — foydalanuvchiga boshqa yo'l kerak.
_NOT_ON_TELEGRAM = ("PHONE_NUMBER_NOT_FOUND", "PHONE_NUMBER_INVALID", "PHONE_NOT_REGISTERED")


class TelegramGatewaySender:
    """Telegram Gateway API (``sendVerificationMessage``): kod foydalanuvchining Telegram'iga, "Verification
    Codes" chatiga keladi. Bot shart emas; narx taxminan $0.01 / kod, o'z raqamiga — bepul (08 §10)."""

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(base_url=GATEWAY_URL, timeout=10)
        self._headers = {"Authorization": f"Bearer {token}"}
        self._log = get_logger("upapi.auth.gateway")

    async def send(self, phone: str, code: str, ttl_seconds: int) -> None:
        try:
            r = await self._client.post(
                "/sendVerificationMessage",
                headers=self._headers,
                json={"phone_number": phone, "code": code, "ttl": ttl_seconds},
            )
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            self._log.warning("gateway_unavailable", error_code=type(exc).__name__)
            raise DeliveryError("gateway_unavailable") from exc
        if not isinstance(body, dict) or not body.get("ok"):
            reason = (
                str(body.get("error", f"http_{r.status_code}"))
                if isinstance(body, dict)
                else "bad_response"
            )
            self._log.warning("gateway_error", error_code=reason, phone=mask_phone(phone))
            raise DeliveryError(reason, not_on_telegram=reason.upper() in _NOT_ON_TELEGRAM)
        result = body.get("result") or {}
        self._log.info(
            "gateway_sent",
            phone=mask_phone(phone),
            request_id=result.get("request_id"),
            cost=result.get("request_cost"),
            balance=result.get("remaining_balance"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def build_sender(settings: Settings) -> CodeSender:
    if settings.otp_sender is OtpSender.TELEGRAM_GATEWAY:
        if not settings.telegram_gateway_token:
            raise RuntimeError("UP_TELEGRAM_GATEWAY_TOKEN berilmagan")
        return TelegramGatewaySender(settings.telegram_gateway_token.get_secret_value())
    return MemorySender(echo=settings.env == "dev")
