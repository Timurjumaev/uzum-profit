"""Uzum Seller Open API mijozi (03 §6, 08 §8): sarlavha ``Authorization: <kalit>`` ("Bearer"siz), xato turlari,
kalit bo'yicha tezlik navbati, qayta urinish, kunlik kvota, sahifalash, xom JSON.

- **Xom JSON:** har sahifa :class:`Page` — Uzum javobi o'zgarishsiz (``raw``) va undan olingan qatorlar (``rows`` —
  o'sha obyektlar, nusxa emas). Maydonlarni o'qish va bazaga yozish — sinxron ishlari (B2.6); yangi maydon chiqsa,
  qayta so'ramasdan ``raw`` dan qayta ishlanadi (02 M3).
- **Qayta urinish:** 5xx va tarmoq — 0,8 → 1,6 → 3,2 s (ko'pi bilan 4 urinish); sekundlik 429 — kutib qayta;
  401/403, WAF, kunlik 429, 400 — qayta urinilmaydi.
- **Kvota:** javob sarlavhasidagi kunlik qoldiq kuzatiladi (``on_quota``); qoldiq ``quota_reserve`` dan kam bo'lsa
  fon so'rovlari yuborilmaydi (:class:`QuotaReserved`) — oxirgi qism foydalanuvchi amallari uchun.
- **Maxfiylik:** kalit faqat ``SecretStr`` sifatida yuradi va faqat so'rov sarlavhasiga qo'yiladi. Xato matnlarida
  kalit ham, javob tanasi ham yo'q — faqat HTTP kod va tur.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

import httpx
from pydantic import SecretStr

from upapi import __version__
from upapi.logs import get_logger
from upapi.uzum.limiter import Priority, RateLimiter

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


class QuotaReserved(UzumError):
    """So'rov yuborilmadi: kunlik qoldiq zaxiradan kam, fon so'rovlari to'xtatilgan (foydalanuvchi amali o'tadi)."""

    kind = "quota_reserved"


RETRYABLE: tuple[type[UzumError], ...] = (UpstreamError, BurstLimited)


@dataclass(frozen=True, slots=True)
class UzumShop:
    external_id: int
    name: str


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Qayta urinishlar orasidagi kutish (soniya). Urinishlar soni = ``len(delays) + 1``."""

    upstream: tuple[float, ...] = (0.8, 1.6, 3.2)
    burst: tuple[float, ...] = (1.0, 2.0, 4.0)

    def delay(self, error: UzumError, attempt: int) -> float | None:
        delays = self.burst if isinstance(error, BurstLimited) else self.upstream
        if not isinstance(error, RETRYABLE) or attempt >= len(delays):
            return None
        return delays[attempt]


NO_RETRY = RetryPolicy(upstream=(), burst=())


@dataclass(slots=True)
class Page:
    """Bitta sahifa: ``raw`` — Uzum javobi o'zgarishsiz; ``rows`` — undagi qatorlar (takrorlar olib tashlangan)."""

    endpoint: str
    path: str
    params: dict[str, Any]
    page: int
    size: int
    rows: list[dict[str, Any]]
    raw: Any
    total: int | None
    has_more: bool
    status: int = 200
    quota_remaining: int | None = None
    fetched_at: float = field(default_factory=time.time)


def _first_list(data: Any) -> list[Any] | None:
    """Ro'yxatning o'zi, ``{"payload": [...]}`` yoki birinchi ichma-ich ro'yxat (2 qavatgacha)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
        for value in data.values():
            if isinstance(value, dict):
                for inner in value.values():
                    if isinstance(inner, list):
                        return inner
    return None


def _key(data: Any, *path: str) -> Any:
    for name in path:
        if not isinstance(data, dict):
            return None
        data = data.get(name)
    return data


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Uzum endpointi: yo'l, sahifa hajmlari (birinchisi rad etilsa keyingisi), qatorlar va jami soni qayerda."""

    name: str
    path: str
    sizes: tuple[int, ...]
    rows: Callable[[Any], Any]
    id_key: str | None = "id"
    total: Callable[[Any], Any] = lambda _: None


# Sahifa hajmlari (08 §8, Temurning yozuvi 2026-10-24): ``finance/orders`` 5000 ni kesmasdan beradi (2529 / 2529).
# Jami soni bor endpointlarda Uzum hajmni jimgina kessa haqiqiy hajm birinchi sahifadan aniqlanadi (``Page.size``);
# jami sonisiz endpointlarda kesishni bilib bo'lmaydi — hujjatlangan xavfsiz hajm ishlatiladi (xarajatlar 2000:
# 5000 so'ralganda 2254 qator keldi, ``payload.totalElements`` esa doim 0 — ishonib bo'lmaydi).
ORDERS = Endpoint(
    "orders",
    "/v1/finance/orders",
    (5000, 1000, 200),
    lambda d: _key(d, "orderItems"),
    total=lambda d: _key(d, "totalElements"),
)
EXPENSES = Endpoint(
    "expenses", "/v1/finance/expenses", (2000, 1000, 200), lambda d: _key(d, "payload", "payments")
)
PRODUCTS = Endpoint(
    "products",
    "/v1/product/shop/{shop_id}",
    (100, 50, 20),
    lambda d: _key(d, "productList"),
    id_key="productId",
    total=lambda d: _key(d, "totalProductsAmount"),
)
INVOICES = Endpoint("invoices", "/v1/shop/{shop_id}/invoice", (50, 20), _first_list)
INVOICE_PRODUCTS = Endpoint(
    "invoice_products", "/v1/shop/{shop_id}/invoice/products", (50, 20), _first_list
)
# Qaytarishlar butun akkaunt bo'yicha: ``shopId`` parametrini Uzum e'tiborsiz qoldiradi (yozuvda boshqa do'kon
# so'ralganda ham o'sha qaytarishlar keldi); har qatorda ``shopId`` va ``returnItems`` (SKU, dona, narx) bor.
RETURNS = Endpoint("returns", "/v1/return", (50, 20), _first_list)
# Do'kon bo'yicha ro'yxat (``{"payload": [...]}``) — ``returnItems`` siz; tarkib uchun :data:`RETURNS`.
SHOP_RETURNS = Endpoint("shop_returns", "/v1/shop/{shop_id}/return", (50, 20), _first_list)


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


def to_ms(value: datetime | int) -> int:
    """Uzum sanalari — Unix millisekund."""
    return value if isinstance(value, int) else int(value.timestamp() * 1000)


class UzumClient:
    """``async with UzumClient(token, base_url=...) as uzum: shops = await uzum.shops()``.

    ``limiter`` + ``key_id`` (akkaunt id) — kalit bo'yicha tezlik navbati; ``priority`` — navbatdagi o'rni va kvota
    zaxirasiga ruxsat. ``on_quota`` — har javobdagi kunlik qoldiq (akkauntga yozish uchun)."""

    def __init__(
        self,
        token: SecretStr,
        *,
        base_url: str,
        timeout: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
        limiter: RateLimiter | None = None,
        key_id: str = "",
        priority: Priority = Priority.BACKGROUND,
        retry: RetryPolicy = RetryPolicy(),  # noqa: B008 — o'zgarmas (frozen)
        quota_reserve: int = 0,
        quota_remaining: int | None = None,
        on_quota: Callable[[int], Awaitable[None] | None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        self._limiter = limiter
        self._key_id = key_id
        self.priority = priority
        self._retry = retry
        self._reserve = quota_reserve
        self._on_quota = on_quota
        self._sleep = sleep
        self.quota_remaining = quota_remaining
        self.requests = 0  # yuborilgan HTTP so'rovlar (qayta urinishlar bilan) — sync_runs uchun

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

    # --- Past daraja ------------------------------------------------------------------------------

    async def _send(self, path: str, params: dict[str, Any] | None) -> httpx.Response:
        if (
            self.priority is Priority.BACKGROUND
            and self.quota_remaining is not None
            and self.quota_remaining < self._reserve
        ):
            raise QuotaReserved(quota_remaining=self.quota_remaining)
        if self._limiter is not None:
            await self._limiter.acquire(self._key_id, self.priority)
        self.requests += 1
        start = time.perf_counter()
        try:
            response = await self._client.get(
                path,
                params=params,
                headers={"Authorization": self._token.get_secret_value()},
            )
        except Exception as exc:
            # Transport chegarasi: tarmoq (yoki boshqa kutubxona) xatosi matni sarlavhalarni o'z ichiga olishi mumkin —
            # logga faqat turi yoziladi, ``from None`` bilan zanjir ham kesiladi (traceback'da ko'rinmaydi).
            _log.warning("uzum_transport_error", path=path, error_code=type(exc).__name__)
            raise UpstreamError() from None
        if (quota := _quota(response)) is not None:
            self.quota_remaining = quota
            if self._on_quota is not None and (pending := self._on_quota(quota)) is not None:
                await pending
        _log.debug(
            "uzum_request",
            path=path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            quota_remaining=self.quota_remaining,
            priority=self.priority.value,
        )
        return response

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET + qayta urinish. Qaytaradi JSON (xom); xato — :class:`UzumError`."""
        attempt = 0
        while True:
            try:
                response = await self._send(path, params)
                if (error := classify(response)) is not None:
                    raise error
                try:
                    return response.json()
                except ValueError:
                    raise UnexpectedResponse(response.status_code, self.quota_remaining) from None
            except UzumError as exc:
                delay = self._retry.delay(exc, attempt)
                if delay is None:
                    raise
                _log.info(
                    "uzum_retry", path=path, error_code=exc.kind, attempt=attempt + 1, delay_s=delay
                )
                attempt += 1
                await self._sleep(delay)

    async def pages(
        self,
        endpoint: Endpoint,
        params: dict[str, Any] | None = None,
        *,
        shop_id: int | None = None,
        max_pages: int = 1000,
        start_page: int = 0,
        size: int | None = None,
    ) -> AsyncIterator[Page]:
        """Hamma sahifalar ketma-ket (``start_page`` dan). To'xtaydi: bo'sh yoki to'lmagan sahifa, jami soniga yetdi
        yoki ``max_pages`` ta sahifa (oxirgi sahifada ``has_more=True`` qoladi — chaqiruvchi davom ettirishi mumkin).

        Birinchi sahifada 400 bo'lsa keyingi (kichikroq) hajm sinaladi. Uzilgan yuklashni davom ettirish
        (``start_page``) avvalgi hajm bilan bo'ladi — ``size`` (``Page.size``), aks holda sahifalar siljiydi. Qatorlar
        endpoint id'si bo'yicha takrorlanmaydi (sahifalar orasida yangi yozuv qo'shilib siljish bo'lsa)."""
        path = endpoint.path.format(shop_id=shop_id)
        base = dict(params or {})
        sizes = (size,) if size else endpoint.sizes
        size, first = sizes[0], None
        for size in sizes:
            try:
                first = await self.get(path, {**base, "page": start_page, "size": size})
                break
            except BadRequest:
                if size == sizes[-1]:
                    raise
        seen: set[Any] = set()
        fetched, page, data = start_page * size, start_page, first
        while True:
            rows = endpoint.rows(data)
            if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                raise UnexpectedResponse(200, self.quota_remaining)
            total = _int_or_none(endpoint.total(data))
            if page == 0 and total is not None and 0 < len(rows) < min(size, total):
                size = len(rows)  # Uzum hajmni jimgina kesdi — haqiqiy hajm
            fetched += len(rows)
            fresh = []
            for row in rows:
                ident = row.get(endpoint.id_key) if endpoint.id_key else None
                if ident is not None:
                    if ident in seen:
                        continue
                    seen.add(ident)
                fresh.append(row)
            has_more = bool(rows) and len(rows) >= size and (total is None or fetched < total)
            yield Page(
                endpoint=endpoint.name,
                path=path,
                params={**base, "page": page, "size": size},
                page=page,
                size=size,
                rows=fresh,
                raw=data,
                total=total,
                has_more=has_more,
                quota_remaining=self.quota_remaining,
            )
            page += 1
            if not has_more or page - start_page >= max_pages:
                return
            data = await self.get(path, {**base, "page": page, "size": size})

    # --- Endpointlar ------------------------------------------------------------------------------

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

    def orders(
        self,
        shop_id: int,
        date_from: datetime | int,
        date_to: datetime | int | None = None,
        **kw: Any,
    ) -> AsyncIterator[Page]:
        """Sotuvlar (``finance/orders``, ``group=false`` — har SKU qatori alohida)."""
        params: dict[str, Any] = {
            "shopIds": shop_id,
            "group": "false",
            "dateFrom": to_ms(date_from),
        }
        if date_to is not None:
            params["dateTo"] = to_ms(date_to)
        return self.pages(ORDERS, params, **kw)

    def expenses(
        self,
        shop_id: int,
        date_from: datetime | int,
        date_to: datetime | int | None = None,
        **kw: Any,
    ) -> AsyncIterator[Page]:
        params: dict[str, Any] = {"shopIds": shop_id, "dateFrom": to_ms(date_from)}
        if date_to is not None:
            params["dateTo"] = to_ms(date_to)
        return self.pages(EXPENSES, params, **kw)

    def products(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]:
        """Mahsulotlar va SKU'lar (qoldiq, narx, komissiya) — ``skuList`` ichida."""
        return self.pages(PRODUCTS, shop_id=shop_id, **kw)

    def invoices(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]:
        """FBO postavkalari (fakturalar)."""
        return self.pages(INVOICES, shop_id=shop_id, **kw)

    def invoice_products(self, shop_id: int, invoice_id: int, **kw: Any) -> AsyncIterator[Page]:
        """Postavka tarkibi."""
        return self.pages(INVOICE_PRODUCTS, {"invoiceId": invoice_id}, shop_id=shop_id, **kw)

    def returns(self, **kw: Any) -> AsyncIterator[Page]:
        """Qaytarishlar (FBO qaytarish va brak) — **butun akkaunt**, do'kon qatordagi ``shopId`` dan; tarkibi bilan."""
        return self.pages(RETURNS, **kw)

    def shop_returns(self, shop_id: int, **kw: Any) -> AsyncIterator[Page]:
        """Do'kon qaytarishlari ro'yxati (tarkibsiz)."""
        return self.pages(SHOP_RETURNS, shop_id=shop_id, **kw)


if TYPE_CHECKING:  # UzumClient provayder interfeysiga mos (mypy tekshiradi)
    from upapi.marketplace import MarketplaceProvider

    _provider: type[MarketplaceProvider] = UzumClient
