"""B2.6 testlari uchun soxta Uzum sotuvchi akkaunti (``httpx.MockTransport``) va bazada tashkilot/akkaunt/do'konlar.

Javob shakllari — Temurning haqiqiy yozuvi (``fixtures/uzum/recorded.json``, 08 §8) bo'yicha: ``finance/orders`` —
``{"orderItems", "totalElements"}``, ``finance/expenses`` — ``{"payload": {"payments"}}``, mahsulotlar —
``{"productList", "totalProductsAmount"}``, postavkalar va ``/v1/return`` — ro'yxat. Sahifalash (``page``, ``size``),
``dateFrom`` filtri, xato rejimlari va "Uzum bu sanadan oldingisini bermaydi" (400) qo'llab-quvvatlanadi.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from mptools import MODES, settings_for
from pydantic import SecretStr
from upapi.crypto import TokenCipher, account_aad
from upapi.db.session import make_engine
from upapi.settings import Settings
from upapi.sync.engine import Runtime
from upapi.uzum.limiter import RateLimiter

PREFIX = "/api/seller-openapi"
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)  # Toshkent: 17:00


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def order(
    ident: int,
    shop: int,
    when: datetime,
    sku: str = "SKU-A",
    *,
    status: str = "TO_WITHDRAW",
    price: int = 100_000,
    amount: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "id": ident,
        "status": status,
        "date": ms(when),
        "orderId": ident * 10,
        "skuTitle": sku,
        "productId": 700_000 + shop % 1000,
        "shopId": shop,
        "dateIssued": None,
        "sellPrice": price,
        "amount": amount,
        "amountReturns": 0,
        "commission": price * amount // 5,
        "sellerProfit": price * amount - price * amount // 5,
        "purchasePrice": 50_000,
        "logisticDeliveryFee": 4_000,
        "cancelled": None,
        "withdrawnProfit": 0,
        "comment": None,
        "productTitle": "Mahsulot",
        "returnCause": None,
    }
    return {**row, **extra}


def expense(
    ident: int,
    shop: int,
    when: datetime,
    code: str = "С000003",
    price: int = 1_500,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "id": ident,
        "dateCreated": ms(when),
        "dateUpdated": None,
        "name": "Saqlash",
        "source": "Ombor",
        "shopId": shop,
        "sellerId": 1,
        "paymentPrice": price,
        "amount": 1,
        "status": "CONFIRMED",
        "externalId": f"ID{ident}",
        "code": code,
        "dateService": ms(when),
        "type": "OUTCOME",
    }
    return {**row, **extra}


def product(ident: int, skus: list[tuple[int, str]], **sku_extra: Any) -> dict[str, Any]:
    return {
        "productId": ident,
        "category": "Kiyim",
        "title": f"Mahsulot {ident}",
        "status": {"value": "IN_STOCK"},
        "skuList": [
            {
                "skuId": sku_id,
                "skuFullTitle": code,
                "skuTitle": code,
                "barcode": 4_780_000_000_000 + sku_id,
                "ikpu": "06109100001000000",
                "price": 100_000,
                "commission": 20.5,
                "quantityActive": 10,
                "quantityFbs": 0,
                "quantityDefected": 1,
                "quantityPending": 2,
                "quantitySold": 30,
                "quantityReturned": 3,
                "avgdsales": 1.25,
                "rankInfo": {"rank": "A"},
                "paidStoragePriceItem": 120,
                "status": {"value": "IN_STOCK"},
                "sellerItemCode": f"ART-{sku_id}",
                **sku_extra,
            }
            for sku_id, code in skus
        ],
    }


def invoice(
    ident: int, status: str = "ACCEPTED", created: Any = "24.10.2026 10:30"
) -> dict[str, Any]:
    return {
        "id": ident,
        "invoiceNumber": ident + 1,
        "dateCreated": created,
        "status": "Qabul qilindi",
        "invoiceStatus": {"text": "Qabul qilindi", "value": status},
        "fullPrice": 500_000,
        "totalAccepted": 5,
        "totalToStock": 5,
        "hasIssue": False,
    }


def invoice_product(sku_id: int, qty: int = 5) -> dict[str, Any]:
    return {
        "id": sku_id + 1,
        "quantityToStock": qty,
        "quantityAccepted": qty,
        "skuForInvoiceDtoList": [
            {"id": sku_id, "quantityToStock": qty, "quantityAccepted": qty, "purchasePrice": 1}
        ],
    }


def return_row(
    ident: int, shop: int, sku_id: int, kind: str = "RETURN", **extra: Any
) -> dict[str, Any]:
    row = {
        "id": ident,
        "dateCreated": ms(NOW - timedelta(days=2)),
        "status": "ASSEMBLED",
        "type": kind,
        "shopId": shop,
        "returnItems": [{"id": ident + 1, "skuId": sku_id, "amount": 2, "purchasePrice": 1}],
    }
    return {**row, **extra}


@dataclass
class FakeSeller:
    """Bitta sotuvchi (kalit). ``fail`` — endpoint nomi → xato rejimi (``mptools.MODES`` yoki ``network``);
    ``fail_from_page`` — xato faqat shu sahifadan boshlab; ``oldest`` — orders/expenses ``dateFrom`` bundan oldin
    bo'lsa 400 (Uzum butun tarixni bermasa)."""

    token: str
    shops: list[dict[str, Any]]
    orders: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    expenses: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    products: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    invoices: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    invoice_products: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    returns: list[dict[str, Any]] = field(default_factory=list)
    quota: int = 90_000
    fail: dict[str, str] = field(default_factory=dict)
    fail_from_page: dict[str, int] = field(default_factory=dict)
    oldest: int | None = None
    seen: list[httpx.Request] = field(default_factory=list)

    def requests(self, name: str) -> list[httpx.Request]:
        return [r for r in self.seen if _endpoint(r.url.path) == name]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        name = _endpoint(request.url.path)
        params = request.url.params
        page, size = int(params.get("page", 0)), int(params.get("size", 10_000))
        mode = self.fail.get(name)
        if mode and page >= self.fail_from_page.get(name, 0):
            if mode == "network":
                raise httpx.ConnectError("ulanib bo'lmadi", request=request)
            if mode == "crash":  # sarlavhani xato matniga qo'shadigan "yomon" kutubxona
                raise RuntimeError(f"buzildi: {request.headers.get('authorization')}")
            status, headers, body = MODES[mode]
            return httpx.Response(status, headers=headers, content=body)
        headers = {"x-ratelimit-remaining-per-day": str(self.quota)}
        if request.headers.get("authorization") != self.token:
            return httpx.Response(
                403, headers=headers, json={"errors": [{"code": "x"}], "payload": None}
            )

        def sliced(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return rows[page * size : (page + 1) * size]

        path = request.url.path.removeprefix(PREFIX)
        if name == "shops":
            return httpx.Response(200, headers=headers, json=self.shops)
        if name in ("orders", "expenses"):
            shop, date_from = int(params["shopIds"]), int(params["dateFrom"])
            if self.oldest is not None and date_from < self.oldest:
                return httpx.Response(400, headers=headers, json={"error": "dateFrom"})
            key = "date" if name == "orders" else "dateCreated"
            source = self.orders if name == "orders" else self.expenses
            rows = [r for r in source.get(shop, []) if r[key] >= date_from]
            rows.sort(key=lambda r: r[key], reverse=True)
            if name == "orders":
                body: Any = {"orderItems": sliced(rows), "totalElements": len(rows)}
            else:
                body = {"payload": {"payments": sliced(rows), "totalElements": 0}}
            return httpx.Response(200, headers=headers, json=body)
        if name == "products":
            rows = self.products.get(int(path.rsplit("/", 1)[1]), [])
            return httpx.Response(
                200,
                headers=headers,
                json={"productList": sliced(rows), "totalProductsAmount": len(rows)},
            )
        if name == "invoices":
            rows = self.invoices.get(int(path.split("/")[3]), [])
            return httpx.Response(200, headers=headers, json=sliced(rows))
        if name == "invoice_products":
            rows = self.invoice_products.get(int(params["invoiceId"]), [])
            return httpx.Response(200, headers=headers, json=sliced(rows))
        if name == "returns":
            return httpx.Response(200, headers=headers, json=sliced(self.returns))
        return httpx.Response(404, headers=headers, json={"error": "not found"})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _endpoint(path: str) -> str:
    path = path.removeprefix(PREFIX)
    if path == "/v1/shops":
        return "shops"
    if path == "/v1/finance/orders":
        return "orders"
    if path == "/v1/finance/expenses":
        return "expenses"
    if path.startswith("/v1/product/shop/"):
        return "products"
    if path.endswith("/invoice/products"):
        return "invoice_products"
    if path.endswith("/invoice"):
        return "invoices"
    if path == "/v1/return":
        return "returns"
    return path


A, B = 900_001, 900_002
TOKEN = "uzk-sync-test-token-0001"
BOTH = [{"id": A, "name": "byDurii"}, {"id": B, "name": "EL-ONE"}]


def seller(**kw: Any) -> FakeSeller:
    day = timedelta(days=1)
    data: dict[str, Any] = {
        "token": TOKEN,
        "shops": [
            {"id": A, "name": "byDurii"}
        ],  # B — testda kerak bo'lsa (Uzum bergan yangi do'kon qo'shiladi)
        "orders": {
            A: [
                order(1, A, NOW - 100 * day, "SKU-A"),
                order(2, A, NOW - 10 * day, "SKU-B", status="PROCESSING"),
                order(3, A, NOW - day, "SKU-A", amount=2),
            ],
            B: [order(11, B, NOW - 2 * day, "SKU-C")],
        },
        "expenses": {
            A: [
                expense(101, A, NOW - 20 * day),
                expense(
                    102,
                    A,
                    NOW - day,
                    "logistics-volume",
                    4_000,
                    name="Logistika",
                    source="Logistika",
                    externalId="3",
                ),
                expense(103, A, NOW - day, "У000120", 1_881, name="Reklama", source="Marketing"),
            ],
            B: [],
        },
        "products": {
            A: [product(501, [(5011, "SKU-A"), (5012, "SKU-B")])],
            B: [product(502, [(5021, "SKU-C")])],
        },
        "invoices": {A: [invoice(601)], B: []},
        "invoice_products": {601: [invoice_product(5011)]},
        "returns": [
            return_row(701, A, 5011),
            return_row(702, B, 5021, "DEFECTED"),
            return_row(703, 123_456, 1),  # boshqa (ulanmagan) do'kon
        ],
    }
    data.update(kw)
    return FakeSeller(**data)


# --- Baza ----------------------------------------------------------------------------------------


@dataclass
class Account:
    org_id: uuid.UUID
    user_id: uuid.UUID
    account_id: uuid.UUID
    shops: dict[int, uuid.UUID]  # tashqi id → bizning id


def create_account(
    urls: dict[str, str],
    settings: Settings,
    token: str,
    shop_ids: list[int],
    *,
    status: str = "active",
) -> Account:
    """Superuser bilan (RLS chetlab): tashkilot, egasi, shifrlangan kalitli akkaunt va faol do'konlar."""
    org, user, account = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cipher = TokenCipher.from_settings(settings.token_keys, settings.token_key_version)
    blob, version = cipher.encrypt(SecretStr(token), account_aad(org, account))
    shops = {ext: uuid.uuid4() for ext in shop_ids}
    with psycopg.connect(urls["admin"]) as conn:
        conn.execute("INSERT INTO orgs (id, name) VALUES (%s, 'Sinxron')", [org])
        phone = f"+99893{uuid.uuid4().int % 10_000_000:07d}"
        conn.execute("INSERT INTO users (id, phone) VALUES (%s, %s)", [user, phone])
        conn.execute(
            "INSERT INTO memberships (org_id, user_id, role) VALUES (%s, %s, 'owner')", [org, user]
        )
        conn.execute(
            "INSERT INTO mp_accounts (id, org_id, token_encrypted, key_version, token_last4, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [account, org, blob, version, token[-4:], status],
        )
        for ext, shop in shops.items():
            conn.execute(
                "INSERT INTO shops (id, org_id, account_id, external_id, name) VALUES (%s, %s, %s, %s, %s)",
                [shop, org, account, ext, f"Do'kon {ext}"],
            )
    return Account(org, user, account, shops)


def admin(urls: dict[str, str], sql: str, params: list[Any] | None = None) -> Any:
    with psycopg.connect(urls["admin"]) as conn:
        cur = conn.execute(sql, params or [])
        return cur.fetchall() if cur.description else cur.rowcount


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@contextmanager
def runtime(
    urls: dict[str, str], fake: FakeSeller, clock: Clock | None = None, **extra: Any
) -> Iterator[Callable[..., Any]]:
    """``run(fn)`` — ``fn(rt)`` korutinasini yangi hodisa tsiklida bajaradi (engine o'sha tsiklda yopiladi)."""
    settings = settings_for(urls, **extra)
    clock = clock or Clock()

    async def no_sleep(_: float) -> None:
        return None

    def run(fn: Callable[[Runtime], Any]) -> Any:
        async def main() -> Any:
            rt = Runtime(
                engine=make_engine(urls["app"]),
                settings=settings,
                cipher=TokenCipher.from_settings(settings.token_keys, settings.token_key_version),
                limiter=RateLimiter(0),
                transport=fake.transport,
                clock=clock,
                sleep=no_sleep,
            )
            try:
                return await fn(rt)
            finally:
                await rt.aclose()

        return asyncio.run(main())

    yield run
