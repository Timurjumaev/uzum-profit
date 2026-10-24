"""Uzum Seller Open API mijozi: sarlavha ``Authorization: <kalit>`` ("Bearer"siz), xato turlari (03 §6, 08 §8).

Kalit faqat ``SecretStr`` sifatida yuradi va faqat so'rov sarlavhasiga qo'yiladi. Xato matnlarida kalit ham, Uzum
javobi tanasi ham yo'q — faqat HTTP kod va tur (javob tanasi xato matni orqali logga tushib qolmasin).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx
from pydantic import SecretStr

from upapi import __version__
from upapi.logs import get_logger

USER_AGENT = f"uzum-profit/{__version__}"
QUOTA_HEADER = "x-ratelimit-remaining-per-day"
_log = get_logger("upapi.uzum")


class UzumError(Exception):
    """Uzum so'rovi muvaffaqiyatsiz. ``kind`` — tur (log va API xato kodi uchun), ``status`` — HTTP kod."""

    kind = "upstream"

    def __init__(self, status: int | None = None, quota_remaining: int | None = None) -> None:
        super().__init__(f"uzum {self.kind}" + (f" (HTTP {status})" if status else ""))
        self.status = status
        self.quota_remaining = quota_remaining


class AuthError(UzumError):
    """JSON 401/403 yoki ``404 Token not found`` — kalit yaroqsiz yoki bekor qilingan."""

    kind = "auth"


class WafBlocked(UzumError):
    """HTML 403 — Uzum himoyasi (IP O'zbekistondan tashqarida); kalit xatosi emas."""

    kind = "waf"


class BurstLimited(UzumError):
    """429, kunlik qoldiq bor — sekundlik limit."""

    kind = "burst"


class QuotaExhausted(UzumError):
    """429, kunlik qoldiq 0."""

    kind = "quota"


class UpstreamError(UzumError):
    """5xx yoki tarmoq xatosi."""

    kind = "upstream"


class BadRequest(UzumError):
    """400 — so'rov noto'g'ri, qayta urinilmaydi."""

    kind = "bad_request"


class UnexpectedResponse(UzumError):
    """Kutilmagan holat yoki javob shakli (JSON emas, ro'yxat emas ...)."""

    kind = "unexpected"


@dataclass(frozen=True, slots=True)
class UzumShop:
    external_id: int
    name: str


_TOKEN_NOT_FOUND = re.compile(rb"token\s+not\s+found", re.IGNORECASE)


def normalize_token(raw: str) -> str:
    """Nusxalashda qo'shilib qoladigan bo'sh joy va "Bearer " old qo'shimchasini olib tashlaydi (Uzum'da yo'q)."""
    token = raw.strip()
    if token[:7].lower() == "bearer ":
        token = token[7:].strip()
    return token


def _quota(response: httpx.Response) -> int | None:
    value = response.headers.get(QUOTA_HEADER, "")
    return int(value) if value.isdigit() else None


def classify(response: httpx.Response) -> UzumError | None:
    """HTTP javob → xato turi (``None`` — 2xx)."""
    status, quota = response.status_code, _quota(response)
    if 200 <= status < 300:
        return None
    body = response.content.lstrip()
    html = "html" in response.headers.get("content-type", "") or body.startswith(b"<")
    if status == 403 and html:
        return WafBlocked(status, quota)
    if status in (401, 403) or (status == 404 and _TOKEN_NOT_FOUND.search(body)):
        return AuthError(status, quota)
    if status == 429:
        return (QuotaExhausted if quota == 0 else BurstLimited)(status, quota)
    if status == 400:
        return BadRequest(status, quota)
    if status >= 500:
        return UpstreamError(status, quota)
    return UnexpectedResponse(status, quota)


class UzumClient:
    """``async with UzumClient(token, base_url=...) as uzum: shops = await uzum.shops()``."""

    def __init__(
        self,
        token: SecretStr,
        *,
        base_url: str,
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        self.quota_remaining: int | None = None

    def __repr__(self) -> str:
        return f"UzumClient(base_url={str(self._client.base_url)!r})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self._client.get(
                path,
                params=params,
                headers={"Authorization": self._token.get_secret_value()},
            )
        except Exception as exc:
            # Transport chegarasi: tarmoq (yoki boshqa kutubxona) xatosi matni sarlavhalarni o'z ichiga olishi mumkin —
            # logga faqat turi yoziladi, ``from None`` bilan zanjir ham kesiladi (traceback'da ko'rinmaydi).
            _log.warning("uzum_transport_error", error_code=type(exc).__name__)
            raise UpstreamError() from None
        if (quota := _quota(response)) is not None:
            self.quota_remaining = quota
        if (error := classify(response)) is not None:
            raise error
        try:
            return response.json()
        except ValueError:
            raise UnexpectedResponse(response.status_code, self.quota_remaining) from None

    async def shops(self) -> list[UzumShop]:
        """``GET /v1/shops`` — kalitga tegishli do'konlar. Javob ro'yxat yoki ``{"payload": [...]}`` (legacy)."""
        data = await self.get("/v1/shops")
        rows = data.get("payload") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise UnexpectedResponse(200, self.quota_remaining)
        shops: dict[int, UzumShop] = {}
        for row in rows:
            ext = row.get("id") if isinstance(row, dict) else None
            if isinstance(ext, bool) or not isinstance(ext, int):
                raise UnexpectedResponse(200, self.quota_remaining)
            name = row.get("name")
            shops[ext] = UzumShop(
                ext, name.strip() if isinstance(name, str) and name.strip() else f"#{ext}"
            )
        return list(shops.values())
