"""B2.5: Uzum mijozi — xato turlari, qayta urinish, kvota, tezlik navbati, sahifalash, xom JSON; yozib olingan
javoblar (kassetalar, ``fixtures/uzum``) bilan.

Haqiqiy Uzum'ga chiqilmaydi. Kassetalar: ``synthetic.json`` (legacy maydonlari asosida) va ``recorded*.json``
(Temurning Mac'ida ``scripts/record_uzum.py`` bilan yozilgan, anonimlashtirilgan) — har test ikkalasida ham.
"""

from __future__ import annotations

import asyncio
import itertools
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from cassette import Cassette, Replay, all_cassettes
from pydantic import SecretStr
from upapi.uzum import client as uz
from upapi.uzum.limiter import Priority, RateLimiter

BASE = "https://uzum.test/api/seller-openapi"
TOKEN = SecretStr("k" * 24)
CASSETTES = all_cassettes()

# B2.6 xaritalashi tayanadigan maydonlar (legacy selfcheck EXPECTED, Temurning real natijasida tasdiqlangan).
CONTRACT: dict[str, set[str]] = {
    "orders": {
        "id",
        "orderId",
        "status",
        "date",
        "sellPrice",
        "amount",
        "commission",
        "sellerProfit",
    },
    "expenses": {"id", "dateCreated", "code", "type", "paymentPrice"},
    "products": {"productId", "skuList"},
    "invoices": {"id", "invoiceNumber", "dateCreated", "invoiceStatus"},
    "invoice_products": {"id", "quantityToStock", "quantityAccepted"},
    "returns": {"id", "dateCreated", "status", "type"},
    "returns_all": {"id", "shopId", "dateCreated", "status", "type", "returnItems"},
}


class Sleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def client(handler: Callable[[httpx.Request], httpx.Response], **kw: Any) -> uz.UzumClient:
    kw.setdefault("sleep", Sleeper())
    return uz.UzumClient(TOKEN, base_url=BASE, transport=httpx.MockTransport(handler), **kw)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def collect(pages: Any) -> list[uz.Page]:
    return [p async for p in pages]


def respond(
    *responses: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Ketma-ket javoblar; oxirgisi takrorlanadi."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[min(len(seen) - 1, len(responses) - 1)]

    return handler, seen


def ok(body: Any, quota: int = 50_000) -> httpx.Response:
    return httpx.Response(200, headers={uz.QUOTA_HEADER: str(quota)}, json=body)


SHOPS = [{"id": 1, "name": "A"}]
FAIL_502 = httpx.Response(502, text="bad gateway")
BURST = httpx.Response(429, headers={uz.QUOTA_HEADER: "800"}, json={})
DAY = httpx.Response(429, headers={uz.QUOTA_HEADER: "0"}, json={})


# --- Kassetalar ------------------------------------------------------------------------------------


def test_cassettes_present() -> None:
    files = [c.file for c in CASSETTES]
    assert "synthetic.json" in files
    for c in CASSETTES:
        assert c.interactions and c.source
        names = {i.name for i in c.interactions}
        assert {"shops", "orders", "expenses", "products"} <= names, c.file


# Kasseta nomi → (endpoint, chaqiruv: mijoz, so'rov parametrlari, yo'ldagi do'kon id).
ENDPOINT_CALLS: dict[str, tuple[uz.Endpoint, Callable[[uz.UzumClient, Any, int], Any]]] = {
    "orders": (uz.ORDERS, lambda c, p, s: c.orders(p["shopIds"], 0, max_pages=1)),
    "orders_end": (uz.ORDERS, lambda c, p, s: c.orders(p["shopIds"], 0, max_pages=1)),
    "expenses": (uz.EXPENSES, lambda c, p, s: c.expenses(p["shopIds"], 0, max_pages=1)),
    "products": (uz.PRODUCTS, lambda c, p, s: c.products(s, max_pages=1)),
    "invoices": (uz.INVOICES, lambda c, p, s: c.invoices(s, max_pages=1)),
    "invoice_products": (
        uz.INVOICE_PRODUCTS,
        lambda c, p, s: c.invoice_products(s, p["invoiceId"], max_pages=1),
    ),
    "returns": (uz.SHOP_RETURNS, lambda c, p, s: c.shop_returns(s, max_pages=1)),
    "returns_all": (uz.RETURNS, lambda c, p, s: c.returns(max_pages=1)),
}


def _cases(names: Any) -> list[Any]:
    """Har yozuv alohida (bir nom bir necha marta — har do'kon uchun)."""
    return [
        pytest.param(c, n, id=f"{c.file}:{n}:{i.name}")
        for c in CASSETTES
        for n, i in enumerate(c.interactions)
        if i.name in names
    ]


@pytest.mark.parametrize(("cassette", "index"), _cases(ENDPOINT_CALLS))
def test_recorded_pages(cassette: Cassette, index: int) -> None:
    """Yozib olingan javob → sahifa: ``raw`` o'zgarishsiz, qatorlar — o'sha obyektlar, kontrakt maydonlari bor."""
    interaction = cassette.interactions[index]
    name = interaction.name
    assert interaction.status == 200
    endpoint, call = ENDPOINT_CALLS[name]
    shop = re.search(r"/shop/(\d+)", interaction.path)
    replay = Replay(interaction)
    uzum = client(replay.handler)
    pages = run(collect(call(uzum, interaction.params, int(shop.group(1)) if shop else 0)))
    assert len(pages) == 1
    page = pages[0]
    assert page.raw == interaction.body and page.endpoint == endpoint.name
    if name == "orders_end":
        assert page.rows == [] and not page.has_more
    extracted = endpoint.rows(page.raw)
    assert all(any(r is e for e in extracted) for r in page.rows)  # nusxa emas
    required = CONTRACT.get(name, set())
    for row in page.rows:
        assert required <= set(row), (cassette.file, name, required - set(row))
    if name == "products":
        for product in page.rows:
            assert isinstance(product["skuList"], list)
            for sku in product["skuList"]:
                assert {"skuId", "price"} <= set(sku), (cassette.file, set(sku))
    assert page.quota_remaining == uz._quota(interaction.response())
    assert replay.seen[0].headers["authorization"] == TOKEN.get_secret_value()


@pytest.mark.parametrize("cassette", CASSETTES, ids=lambda c: c.file)
def test_recorded_shops(cassette: Cassette) -> None:
    interaction = cassette.get("shops")
    assert interaction is not None
    shops = run(client(Replay(interaction).handler).shops())
    assert shops and all(isinstance(s.external_id, int) and s.name for s in shops)


_ERRORS = {
    "auth_error": uz.AuthError,
    "bad_request": uz.BadRequest,
    "waf": uz.WafBlocked,
    "burst": uz.BurstLimited,
    "quota": uz.QuotaExhausted,
    "server_error": uz.UpstreamError,
}


@pytest.mark.parametrize(("cassette", "index"), _cases(_ERRORS))
def test_recorded_errors(cassette: Cassette, index: int) -> None:
    interaction = cassette.interactions[index]
    name = interaction.name
    if interaction.status == 200:  # masalan, Uzum manfiy hajmni rad etmadi — yozuvda shunday
        pytest.skip(f"{name}: Uzum 200 qaytargan")
    uzum = client(Replay(interaction).handler, retry=uz.NO_RETRY)
    with pytest.raises(_ERRORS[name]):
        run(uzum.get(interaction.path, {**interaction.params, "page": 0}))


# --- Qayta urinish -------------------------------------------------------------------------------


def test_upstream_retried_with_backoff() -> None:
    handler, seen = respond(FAIL_502, FAIL_502, ok(SHOPS))
    sleeper = Sleeper()
    uzum = client(handler, sleep=sleeper)
    assert run(uzum.shops()) == [uz.UzumShop(1, "A")]
    assert sleeper.calls == [0.8, 1.6] and len(seen) == 3 and uzum.requests == 3


def test_upstream_gives_up_after_four_attempts() -> None:
    handler, seen = respond(FAIL_502)
    sleeper = Sleeper()
    with pytest.raises(uz.UpstreamError):
        run(client(handler, sleep=sleeper).shops())
    assert sleeper.calls == [0.8, 1.6, 3.2] and len(seen) == 4


def test_network_error_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return ok(SHOPS)

    assert run(client(handler).shops())[0].external_id == 1 and len(calls) == 2


def test_burst_waits_and_retries() -> None:
    handler, seen = respond(BURST, BURST, ok(SHOPS))
    sleeper = Sleeper()
    assert run(client(handler, sleep=sleeper).shops())
    assert sleeper.calls == [1.0, 2.0] and len(seen) == 3


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (DAY, uz.QuotaExhausted),
        (httpx.Response(401, json={}), uz.AuthError),
        (httpx.Response(403, text="<html>blocked</html>"), uz.WafBlocked),
        (httpx.Response(400, json={}), uz.BadRequest),
        (httpx.Response(200, text="not json"), uz.UnexpectedResponse),
    ],
)
def test_not_retried(response: httpx.Response, error: type[uz.UzumError]) -> None:
    handler, seen = respond(response, ok(SHOPS))
    sleeper = Sleeper()
    with pytest.raises(error):
        run(client(handler, sleep=sleeper).shops())
    assert len(seen) == 1 and sleeper.calls == []


def test_retry_policy() -> None:
    policy = uz.RetryPolicy(upstream=(0.1,), burst=())
    assert policy.delay(uz.UpstreamError(), 0) == 0.1
    assert policy.delay(uz.UpstreamError(), 1) is None
    assert policy.delay(uz.BurstLimited(429), 0) is None
    assert policy.delay(uz.AuthError(401), 0) is None
    assert uz.NO_RETRY.delay(uz.UpstreamError(), 0) is None


# --- Kvota ---------------------------------------------------------------------------------------


def test_quota_tracked_and_reported() -> None:
    reported: list[int] = []
    handler, _ = respond(ok(SHOPS, quota=70_000), httpx.Response(200, json=SHOPS))
    uzum = client(handler, on_quota=reported.append)
    run(uzum.shops())
    run(uzum.shops())  # sarlavhasiz javob — oxirgi qiymat qoladi
    assert uzum.quota_remaining == 70_000 and reported == [70_000]


def test_async_quota_callback() -> None:
    reported: list[int] = []

    async def save(value: int) -> None:
        reported.append(value)

    handler, _ = respond(ok(SHOPS, quota=12))
    run(client(handler, on_quota=save).shops())
    assert reported == [12]


def test_background_stops_at_reserve_user_passes() -> None:
    handler, seen = respond(ok(SHOPS, quota=9_000))
    uzum = client(handler, quota_reserve=10_000)
    run(uzum.shops())  # qoldiq noma'lum — birinchi so'rov o'tadi
    with pytest.raises(uz.QuotaReserved) as info:
        run(uzum.shops())
    assert info.value.quota_remaining == 9_000 and len(seen) == 1  # so'rov yuborilmadi
    uzum.priority = Priority.USER
    assert run(uzum.shops()) and len(seen) == 2
    # Saqlangan qoldiq bilan boshlash (akkauntdan).
    fresh = client(handler, quota_reserve=10_000, quota_remaining=500)
    with pytest.raises(uz.QuotaReserved):
        run(fresh.shops())


# --- Sahifalash va xom JSON ----------------------------------------------------------------------


def orders_page(ids: list[int], total: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"orderItems": [{"id": i, "status": "TO_WITHDRAW"} for i in ids]}
    if total is not None:
        body["totalElements"] = total
    return body


def test_orders_params_and_paging() -> None:
    pages_by_number = {
        "0": orders_page(list(range(1000)), total=2100),
        "1": orders_page(list(range(1000, 2000)), total=2100),
        "2": orders_page(list(range(2000, 2100)), total=2100),
    }
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(pages_by_number[request.url.params["page"]])

    since = datetime(2026, 10, 1, tzinfo=UTC)
    pages = run(collect(client(handler).orders(106121, since, 1_761_955_200_000)))
    assert [len(p.rows) for p in pages] == [1000, 1000, 100]
    assert [p.has_more for p in pages] == [True, True, False]
    assert pages[0].total == 2100 and pages[0].endpoint == "orders"
    params = seen[0].url.params
    assert seen[0].url.path == "/api/seller-openapi/v1/finance/orders"
    assert params["shopIds"] == "106121" and params["group"] == "false"
    assert params["dateFrom"] == str(int(since.timestamp() * 1000))
    assert params["dateTo"] == "1761955200000" and params["size"] == "5000"
    assert [r.url.params["page"] for r in seen] == ["0", "1", "2"]
    # Xom JSON: sahifa javobi o'zgarishsiz, qatorlar — o'sha obyektlar.
    assert pages[1].raw is not None and pages[1].rows[0] is pages[1].raw["orderItems"][0]
    assert pages[2].params == {
        "shopIds": 106121,
        "group": "false",
        "dateFrom": int(since.timestamp() * 1000),
        "dateTo": 1761955200000,
        "page": 2,
        "size": 1000,
    }


def test_silently_clamped_page_size() -> None:
    """Uzum 5000 so'ralganda 500 bersa (jami 1200) — haqiqiy hajm 500, sahifalash davom etadi."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        ids = list(range(page * 500, min(page * 500 + 500, 1200)))
        return ok(orders_page(ids, total=1200))

    pages = run(collect(client(handler).orders(1, 0)))
    assert sum(len(p.rows) for p in pages) == 1200 and len(pages) == 3
    assert [r.url.params["size"] for r in seen] == ["5000", "500", "500"]


def test_duplicates_across_pages_dropped() -> None:
    bodies = [orders_page([1, 2, 3], total=None), orders_page([3, 4], total=None)]
    handler, _ = respond(*(ok(b) for b in bodies))
    pages = run(
        collect(client(handler).pages(uz.Endpoint("t", "/t", (3,), lambda d: d["orderItems"])))
    )
    assert [[r["id"] for r in p.rows] for p in pages] == [[1, 2, 3], [4]]
    assert len(pages[1].raw["orderItems"]) == 2  # xom javob to'liq qoladi


def test_max_pages_leaves_has_more() -> None:
    handler, seen = respond(
        ok(orders_page([1, 2], total=None)), ok(orders_page([3, 4], total=None))
    )
    endpoint = uz.Endpoint("t", "/t", (2,), lambda d: d["orderItems"])
    pages = run(collect(client(handler).pages(endpoint, max_pages=1)))
    assert len(pages) == 1 and pages[0].has_more and len(seen) == 1


def test_page_size_fallback_on_bad_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params["size"] == "100":
            return httpx.Response(400, json={})
        return ok({"productList": [{"productId": 7, "skuList": []}], "totalProductsAmount": 1})

    pages = run(collect(client(handler).products(55)))
    assert [r.url.params["size"] for r in seen] == ["100", "50"]
    assert seen[0].url.path.endswith("/v1/product/shop/55") and pages[0].size == 50


def test_page_size_fallback_exhausted() -> None:
    handler, seen = respond(httpx.Response(400, json={}))
    with pytest.raises(uz.BadRequest):
        run(collect(client(handler).invoices(1)))
    assert [r.url.params["size"] for r in seen] == ["50", "20"]


@pytest.mark.parametrize(
    "body", [{"orderItems": None}, {"orderItems": [1, 2]}, {"boshqa": []}, [{"id": 1}]]
)
def test_unexpected_page_shape(body: Any) -> None:
    handler, _ = respond(ok(body))
    with pytest.raises(uz.UnexpectedResponse):
        run(collect(client(handler).orders(1, 0)))


def test_endpoint_paths_and_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "expenses" in request.url.path:
            return ok({"payload": {"payments": []}})
        return ok([])

    uzum = client(handler)
    run(collect(uzum.expenses(9, 1000, 2000)))
    run(collect(uzum.invoices(9)))
    run(collect(uzum.invoice_products(9, 77)))
    run(collect(uzum.returns()))
    run(collect(uzum.shop_returns(9)))
    got = [(r.url.path.removeprefix("/api/seller-openapi"), dict(r.url.params)) for r in seen]
    assert got == [
        (
            "/v1/finance/expenses",
            {"shopIds": "9", "dateFrom": "1000", "dateTo": "2000", "page": "0", "size": "2000"},
        ),
        ("/v1/shop/9/invoice", {"page": "0", "size": "50"}),
        ("/v1/shop/9/invoice/products", {"invoiceId": "77", "page": "0", "size": "50"}),
        ("/v1/return", {"page": "0", "size": "50"}),
        ("/v1/shop/9/return", {"page": "0", "size": "50"}),
    ]


def test_first_list_and_helpers() -> None:
    assert uz._first_list([1]) == [1]
    assert uz._first_list({"a": 1, "payload": [2]}) == [2]
    assert uz._first_list({"payload": {"items": [3]}}) == [3]
    assert uz._first_list({"a": 1}) is None and uz._first_list("x") is None
    assert uz.to_ms(datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)) == 1000 and uz.to_ms(5) == 5


# --- Tezlik navbati ------------------------------------------------------------------------------


def test_limiter_spaces_requests() -> None:
    async def scenario() -> list[float]:
        limiter = RateLimiter(0.05)
        marks: list[float] = []

        async def one() -> None:
            await limiter.acquire("acc")
            marks.append(time.monotonic())

        await asyncio.gather(*(one() for _ in range(4)))
        return marks

    marks = sorted(run(scenario()))
    gaps = [b - a for a, b in itertools.pairwise(marks)]
    assert all(g >= 0.045 for g in gaps), gaps


def test_limiter_keys_are_independent() -> None:
    async def scenario() -> float:
        limiter = RateLimiter(1.0)
        start = time.monotonic()
        await limiter.acquire("a")
        await limiter.acquire("b")
        return time.monotonic() - start

    assert run(scenario()) < 0.5


def test_limiter_user_goes_first() -> None:
    async def scenario() -> list[str]:
        limiter = RateLimiter(0.1, yield_every=0.005)
        order: list[str] = []

        async def go(name: str, priority: Priority, delay: float) -> None:
            await asyncio.sleep(delay)
            await limiter.acquire("acc", priority)
            order.append(name)

        await asyncio.gather(
            go("bg1", Priority.BACKGROUND, 0),
            go("bg2", Priority.BACKGROUND, 0.01),
            go("bg3", Priority.BACKGROUND, 0.015),
            go("user", Priority.USER, 0.03),
        )
        return order

    order = run(scenario())
    assert order[0] == "bg1" and order[1] == "user", order


def test_client_uses_limiter() -> None:
    acquired: list[tuple[str, Priority]] = []

    class Spy(RateLimiter):
        async def acquire(self, key: str, priority: Priority = Priority.BACKGROUND) -> None:
            acquired.append((key, priority))

    handler, _ = respond(FAIL_502, ok(SHOPS))
    run(client(handler, limiter=Spy(0), key_id="acc-1", priority=Priority.USER).shops())
    assert acquired == [("acc-1", Priority.USER)] * 2  # qayta urinish ham navbatdan o'tadi


def test_provider_interface() -> None:
    """``UzumClient`` provayder interfeysiga mosligini mypy tekshiradi (client.py oxiri); bu yerda — tarkibi."""
    from upapi.marketplace import MarketplaceProvider

    for method in (
        "shops",
        "orders",
        "expenses",
        "products",
        "invoices",
        "invoice_products",
        "returns",
    ):
        assert hasattr(MarketplaceProvider, method) and hasattr(uz.UzumClient, method)


# --- Haqiqiy yozuvdan chiqqan faktlar (recorded.json, 2026-10-24) ---------------------------------

RECORDED = next((c for c in CASSETTES if c.file == "recorded.json"), None)
needs_recording = pytest.mark.skipif(RECORDED is None, reason="recorded.json yo'q")


@needs_recording
def test_recorded_facts() -> None:
    """Mijoz qarorlari tayangan haqiqiy Uzum xatti-harakati — kasseta yangilansa ham saqlanishi kerak."""
    assert RECORDED is not None
    by_name: dict[str, list[Any]] = {}
    for i in RECORDED.interactions:
        by_name.setdefault(i.name, []).append(i)
    # Noto'g'ri kalit — 403 JSON (401 emas): kalit xatosi, WAF emas.
    auth = by_name["auth_error"][0]
    assert auth.status == 403 and isinstance(uz.classify(auth.response()), uz.AuthError)
    # Kunlik qoldiq sarlavhasi.
    assert uz.QUOTA_HEADER in by_name["shops"][0].headers
    # 5000 li sahifa kesilmaydi (sotuvlar: qatorlar = jami) — ORDERS.sizes[0] shunga tayanadi.
    for probe in RECORDED.probes:
        if probe["name"] == "size_probe_orders":
            assert probe["status"] == 200 and probe["rows"] == probe["total"]
    assert uz.ORDERS.sizes[0] == 5000
    # Xarajatlar: payload.totalElements ishonchsiz (qatorlar bor, jami 0) — EXPENSES jami sonini ishlatmaydi.
    expenses = by_name["expenses"][0].body["payload"]
    assert expenses["payments"] and expenses["totalElements"] == 0
    assert uz.EXPENSES.total(by_name["expenses"][0].body) is None
    # /v1/return shopId filtrini e'tiborsiz qoldiradi: boshqa do'kon so'ralganda ham o'sha qatorlar.
    asked = {i.params["shopId"]: {r["shopId"] for r in i.body} for i in by_name["returns_all"]}
    assert len(asked) == 2 and len({frozenset(v) for v in asked.values()}) == 1
    assert any(shop not in got for shop, got in asked.items())
    assert "shopId" not in uz.RETURNS.path
