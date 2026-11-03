"""B2.11 real sinov hisoboti: ``python -m upapi.realcheck > realcheck.json`` (staging serverda,
``infra/staging/realcheck.sh`` orqali).

Sinxronlangan ma'lumotdan JSON chiqaradi (stdout; xulosa — stderr):

- **sotuvlar** — do'kon × oy (Toshkent sanasi, F1) × holat bo'yicha dona, tushum (F3), komissiya (F4), logistika
  (F5), ``sellerProfit``, qaytgan dona va qatorlar ro'yxati (legacy bilan qator darajasida solishtirish uchun);
- **taxminlar** (B2.6, B2.8 dan, 05 B2.11): postavka tarkibidagi ``skuForInvoiceDtoList[].id`` = SKU id, faktura
  ``dateCreated`` formati, ``/v1/return`` sahifalash va hajmi, logistika xarajati ``externalId`` = sotuv qatori id,
  ``amount`` / ``amountReturns`` semantikasi (``sellerProfit`` qaysi dona bilan F6 ga to'g'ri keladi), noma'lum
  xarajat kodlari;
- **sinxron holati** — oxirgi 24 soatdagi ishlar va xatolar;
- **qoldiq joylari** (ADR-034) — SKU ``quantity*`` maydonlari (yig'indi, nol bo'lmagan SKU'lar, SKU holati bo'yicha),
  postavka holatlari (e'lon qilingan / qabul qilingan), qaytarish turi × holati, sotuv holatlari (oxirgi 60 kun) —
  maydonlar ma'nosini real ma'lumotda aniqlash uchun; faqat yig'indilar, nom va shaxsiy ma'lumot yo'q;
- **xarajatlar SKU va sotuvga** (B4.21, ADR-039) — boshqa xarajat turlarining matn / ``externalId`` ko'rinishlari va
  sotuv / SKU / mahsulotga mosligi, logistika farqi namunalari, saqlash ↔ qoldiq × narx modeli;
- **xarajatlar vaqti va bog'lanishi** (B4.20, 07 Q10) — Uzum yechgan logistika ↔ sotuv qatoridagi logistika (holat
  bo'yicha), reklama turlari (buyurtmaga bog'liq "xaridor olganida" turi, ``AD#`` → sotuv qatori, yechilgan kun
  buyurtma va topshirilgan kunga nisbatan), ``dateService`` ↔ ``dateCreated`` farqi va saqlash yechiladigan kunlar.

Kalit va boshqa sirlar o'qilmaydi (ustunlar aniq sanab olinadi). Solishtirish — Temurning Mac'ida
``scripts/compare_staging.py`` (legacy ``uzum.db`` bilan). Ulanish — ilova roli (``up_app``) bilan, RLS ostida:
tashkilotlar ``sync_accounts()`` dan, har biri o'z ``org_transaction`` ida.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, TextIO
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from upcore.metrics import SaleLine

from upapi.db.session import make_engine, org_transaction
from upapi.reports.cells import storage_split
from upapi.settings import Settings, get_settings
from upapi.sync.mapping import TASHKENT

FORMAT = 1
TOL = Decimal(1)  # so'm: F6 tekshiruvida yaxlitlash
SAMPLE = 20  # misollar va kodlar ro'yxati uzunligi


def money(value: Decimal) -> str:
    """JSON'da pul — matn (Decimal aniqligi saqlanadi)."""
    value += 0  # "-0" → "0"
    return format(value.normalize() if value == value.to_integral() else value, "f")


def pattern(value: Any) -> str:
    """Qiymat ko'rinishi (raqamlar → ``9``): ``24.10.2026 10:30`` → ``99.99.9999 99:99``, son → ``<number>``."""
    if value is None:
        return "<null>"
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return f"<{type(value).__name__}>"
    if not isinstance(value, str):
        return "<number>"
    return re.sub(r"\d", "9", value)[:40]


# --- Sotuvlar ------------------------------------------------------------------------------------


@dataclass(slots=True)
class Sale:
    external_id: int
    order_id: int
    status: str
    ordered_at: datetime
    sell_price: Decimal
    amount: int
    commission: Decimal
    logistics: Decimal
    seller_profit: Decimal | None
    amount_returns: int

    @property
    def line(self) -> SaleLine:
        return SaleLine(
            sku="",
            order_date=self.ordered_at.astimezone(TASHKENT).date(),
            status=self.status,
            sell_price=self.sell_price,
            amount=self.amount,
            commission=self.commission,
            logistics=self.logistics,
            seller_profit=self.seller_profit,
            amount_returns=self.amount_returns,
        )


@dataclass(slots=True)
class Totals:
    lines: int = 0
    units: int = 0
    revenue: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    logistics: Decimal = Decimal(0)
    seller_profit: Decimal = Decimal(0)
    amount_returns: int = 0

    def add(self, line: SaleLine) -> None:
        self.lines += 1
        self.units += line.amount
        self.revenue += line.revenue
        self.commission += line.commission
        self.logistics += line.logistics
        self.seller_profit += line.seller_profit or 0
        self.amount_returns += line.amount_returns

    def out(self) -> dict[str, Any]:
        return {
            "lines": self.lines,
            "units": self.units,
            "revenue": money(self.revenue),
            "commission": money(self.commission),
            "logistics": money(self.logistics),
            "seller_profit": money(self.seller_profit),
            "amount_returns": self.amount_returns,
        }


@dataclass(slots=True)
class Semantics:
    """``sellerProfit`` (Uzum) F6 ga (tushum − komissiya − logistika) qaysi dona bilan teng: hamma qatorlarda
    ``amount`` bilan (va logistikasiz variant), qaytgani bor qatorlarda — ``amount`` bilan yoki
    ``amount − amountReturns`` bilan (``amount`` qolgan donami yoki asl donami). Holat bo'yicha sanaladi."""

    lines: int = 0
    no_profit: int = 0
    f6_amount: int = 0  # sellerProfit = sellPrice × amount − komissiya − logistika
    f6_no_logistics: int = 0  # sellerProfit = sellPrice × amount − komissiya
    with_returns: int = 0
    returns_f6_amount: int = 0  # qaytgani bor qatorlar: × amount
    returns_f6_net: int = 0  # qaytgani bor qatorlar: × (amount − amountReturns)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def add(self, sale: Sale) -> None:
        self.lines += 1
        returned = sale.amount_returns > 0
        self.with_returns += returned
        if sale.seller_profit is None:
            self.no_profit += 1
            return
        fees = sale.commission + sale.logistics

        def f6(units: int, costs: Decimal = fees) -> bool:
            assert sale.seller_profit is not None
            return abs(sale.sell_price * units - costs - sale.seller_profit) <= TOL

        self.f6_amount += f6(sale.amount)
        self.f6_no_logistics += f6(sale.amount, sale.commission)
        if returned:
            self.returns_f6_amount += f6(sale.amount)
            self.returns_f6_net += f6(sale.amount - sale.amount_returns)
        if (returned or sale.status == "PARTIALLY_CANCELLED") and len(self.examples) < SAMPLE:
            self.examples.append(
                {
                    "id": sale.external_id,
                    "status": sale.status,
                    "amount": sale.amount,
                    "amount_returns": sale.amount_returns,
                    "sell_price": money(sale.sell_price),
                    "commission": money(sale.commission),
                    "logistics": money(sale.logistics),
                    "seller_profit": money(sale.seller_profit),
                }
            )

    def out(self) -> dict[str, Any]:
        return {
            "lines": self.lines,
            "no_seller_profit": self.no_profit,
            "f6_amount": self.f6_amount,
            "f6_without_logistics": self.f6_no_logistics,
            "with_returns": self.with_returns,
            "returns_f6_amount": self.returns_f6_amount,
            "returns_f6_net": self.returns_f6_net,
            "examples": self.examples,
        }


async def _sales(conn: AsyncConnection, shop: UUID) -> list[Sale]:
    rows = await conn.execute(
        text(
            "SELECT external_id, order_id, status, ordered_at, sell_price, amount, commission, "
            "logistics_fee, seller_profit, amount_returns FROM sale_items WHERE shop_id = :s "
            "ORDER BY ordered_at, external_id"
        ),
        {"s": shop},
    )
    return [Sale(*r) for r in rows]


def sales_report(sales: Sequence[Sale]) -> dict[str, Any]:
    months: dict[str, dict[str, Totals]] = defaultdict(lambda: defaultdict(Totals))
    semantics: dict[str, Semantics] = defaultdict(Semantics)
    for sale in sales:
        line = sale.line
        months[line.order_date.strftime("%Y-%m")][sale.status].add(line)
        semantics[sale.status].add(sale)
    return {
        "months": {
            month: {status: t.out() for status, t in sorted(by.items())}
            for month, by in sorted(months.items())
        },
        "semantics": {status: s.out() for status, s in sorted(semantics.items())},
        # [id, buyurtma, holat, Toshkent sanasi, dona, narx, komissiya, logistika, sellerProfit, qaytgan dona]
        "lines": [
            [
                s.external_id,
                s.order_id,
                s.status,
                s.line.order_date.isoformat(),
                s.amount,
                money(s.sell_price),
                money(s.commission),
                money(s.logistics),
                None if s.seller_profit is None else money(s.seller_profit),
                s.amount_returns,
            ]
            for s in sales
        ],
    }


# --- Taxminlar -----------------------------------------------------------------------------------


async def _scalar_row(conn: AsyncConnection, sql: str, shop: UUID) -> dict[str, Any]:
    row = (await conn.execute(text(sql), {"s": shop})).mappings().one()
    return dict(row)


async def _patterns(conn: AsyncConnection, table: str, key: str, shop: UUID) -> dict[str, int]:
    rows = await conn.execute(
        text(f"SELECT raw -> '{key}' FROM {table} WHERE shop_id = :s"),  # nomlar kodda
        {"s": shop},
    )
    return dict(Counter(pattern(r[0]) for r in rows).most_common(SAMPLE))


async def invoices_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """Postavka: ``dateCreated`` o'qildimi (``created_on``), tarkib SKU'ga bog'landimi. Bog'lanmagan id mahsulot
    id'siga to'g'ri kelsa — ``skuForInvoiceDtoList[].id`` SKU emas, mahsulot id'si (taxmin noto'g'ri)."""
    out = await _scalar_row(
        conn,
        "SELECT count(*) AS invoices, count(created_on) AS date_parsed FROM fbo_invoices "
        "WHERE shop_id = :s",
        shop,
    )
    out["date_patterns"] = await _patterns(conn, "fbo_invoices", "dateCreated", shop)
    out |= await _scalar_row(
        conn,
        "SELECT count(*) AS items, count(i.sku_id) AS items_linked, "
        "count(DISTINCT i.sku_external_id) FILTER (WHERE i.sku_id IS NULL) AS unlinked_ids, "
        "count(DISTINCT i.sku_external_id) FILTER (WHERE i.sku_id IS NULL AND EXISTS ("
        "  SELECT 1 FROM mp_products p WHERE p.shop_id = v.shop_id AND p.external_id = i.sku_external_id"
        ")) AS unlinked_match_product "
        "FROM fbo_invoice_items i JOIN fbo_invoices v ON v.id = i.invoice_id WHERE v.shop_id = :s",
        shop,
    )
    return out


async def returns_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """``/v1/return``: turlar, sana formati, tarkib SKU'ga bog'lanishi; oxirgi ish — Uzum aytgan jami
    (``total``) bilan olingan qatorlar (``fetched``) va so'rovlar (sahifalar) soni."""
    rows = await conn.execute(
        text("SELECT type, count(*) FROM mp_returns WHERE shop_id = :s GROUP BY type ORDER BY 1"),
        {"s": shop},
    )
    out: dict[str, Any] = {"by_type": {r[0]: r[1] for r in rows}}
    out |= await _scalar_row(
        conn,
        "SELECT count(*) AS returns, count(created_on) AS date_parsed, min(created_on) AS first, "
        "max(created_on) AS last FROM mp_returns WHERE shop_id = :s",
        shop,
    )
    out["date_patterns"] = await _patterns(conn, "mp_returns", "dateCreated", shop)
    out |= await _scalar_row(
        conn,
        "SELECT count(*) AS items, count(i.sku_id) AS items_linked, coalesce(sum(i.quantity), 0) "
        "AS units FROM mp_return_items i JOIN mp_returns r ON r.id = i.return_id WHERE r.shop_id = :s",
        shop,
    )
    last = (
        (
            await conn.execute(
                text(
                    "SELECT status, mode, fetched, written, total, requests, started_at FROM sync_runs "
                    "WHERE shop_id = :s AND kind = 'returns' AND status <> 'running' "
                    "ORDER BY started_at DESC LIMIT 1"
                ),
                {"s": shop},
            )
        )
        .mappings()
        .one_or_none()
    )
    out["last_run"] = dict(last) if last else None
    return out


async def logistics_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """Logistika xarajati → sotuv qatori (``externalId`` = qator id). Bog'lanmaganlari buyurtma id'siga to'g'ri
    kelsa — ``externalId`` buyurtma id'si (taxmin noto'g'ri)."""
    return await _scalar_row(
        conn,
        "SELECT count(*) AS expenses, count(e.item_external_id) AS with_external_id, "
        "count(e.sale_item_id) AS linked, "
        "count(*) FILTER (WHERE e.sale_item_id IS NULL AND e.item_external_id IS NOT NULL AND EXISTS ("
        "  SELECT 1 FROM sale_items s WHERE s.shop_id = e.shop_id AND s.order_id = e.item_external_id"
        ")) AS unlinked_match_order, "
        "count(*) FILTER (WHERE e.sale_item_id IS NULL AND e.item_external_id IS NOT NULL AND NOT EXISTS ("
        "  SELECT 1 FROM sale_items s WHERE s.shop_id = e.shop_id AND s.external_id = e.item_external_id"
        ")) AS unlinked_no_sale, "
        "coalesce(sum(e.amount), 0) AS amount "
        "FROM mp_expenses e WHERE e.shop_id = :s AND e.category IN ('logistics', 'logistics_refund')",
        shop,
    )


async def processing_logistics_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """ADR-037: Uzum Jarayondagi qatorga logistikani qachon yozadi — ``dateIssued`` (topshirilgan) × logistika (0 / > 0).
    Kutilayotgan logistika taxmini (F5) "topshirilmagan va 0" qatorlarga qo'shiladi; "topshirilgan va 0" — Uzum bergani.
    Yakunlangan qatorlarda ``dateIssued`` bo'shligi — maydon ishonchliligini ko'rsatadi."""
    processing = "upper(trim(status)) = 'PROCESSING'"
    return await _scalar_row(
        conn,
        f"SELECT count(*) FILTER (WHERE {processing}) AS processing, "
        f"count(*) FILTER (WHERE {processing} AND issued_at IS NULL AND logistics_fee = 0) AS not_issued_zero, "
        f"count(*) FILTER (WHERE {processing} AND issued_at IS NULL AND logistics_fee > 0) AS not_issued_paid, "
        f"count(*) FILTER (WHERE {processing} AND issued_at IS NOT NULL AND logistics_fee = 0) AS issued_zero, "
        f"count(*) FILTER (WHERE {processing} AND issued_at IS NOT NULL AND logistics_fee > 0) AS issued_paid, "
        "count(*) FILTER (WHERE upper(trim(status)) = 'TO_WITHDRAW') AS completed, "
        "count(*) FILTER (WHERE upper(trim(status)) = 'TO_WITHDRAW' AND issued_at IS NULL) AS completed_not_issued "
        "FROM sale_items WHERE shop_id = :s",
        shop,
    )


_NET = "CASE WHEN e.type = 'OUTCOME' THEN e.amount ELSE -e.amount END"  # F9 ishorasi: chiqim +, qaytim −
_TASHKENT_DAY = "(timezone('Asia/Tashkent', {}))::date"


def _day(column: str) -> str:
    return _TASHKENT_DAY.format(column)


async def logistics_reconcile_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """Uzum yechgan logistika (``finance/expenses``, sotuv qatoriga bog'langan, chiqim − qaytim) ↔ sotuv qatoridagi
    logistika (F5) — holat bo'yicha. P&L logistikani faqat sotuv qatoridan oladi (xarajat qatorlari qayta ayrilmaydi):
    ``differ`` va ayniqsa Bekor qatorlardagi ``expense_net`` — sotuv qatorida ko'rinmaydigan (yashirin) logistika;
    ``fee_without_expense`` — Uzum qatorga yozgan, lekin hali yechmagan logistika (masalan, buyurtma paytida yozilgan)."""
    rows = await conn.execute(
        text(
            "WITH x AS (SELECT e.sale_item_id AS id, sum(" + _NET + ") AS net FROM mp_expenses e "
            "WHERE e.shop_id = :s AND e.sale_item_id IS NOT NULL "
            "AND e.category IN ('logistics', 'logistics_refund') AND e.excluded IS DISTINCT FROM 'status' "
            "GROUP BY 1) "
            "SELECT upper(trim(s.status)) AS status, count(*) AS lines, count(x.id) AS with_expense, "
            "count(*) FILTER (WHERE x.id IS NOT NULL AND abs(x.net - s.logistics_fee) <= 1) AS equal, "
            "count(*) FILTER (WHERE x.id IS NOT NULL AND abs(x.net - s.logistics_fee) > 1) AS differ, "
            "count(*) FILTER (WHERE x.id IS NULL AND s.logistics_fee > 0) AS fee_without_expense, "
            "coalesce(sum(s.logistics_fee), 0) AS line_fee, coalesce(sum(x.net), 0) AS expense_net "
            "FROM sale_items s LEFT JOIN x ON x.id = s.id WHERE s.shop_id = :s GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop},
    )
    return {
        "by_status": [
            {**dict(r._mapping), "line_fee": money(r.line_fee), "expense_net": money(r.expense_net)}
            for r in rows
        ]
    }


async def ads_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """Reklama xarajatlari (F9, F19) — qaysi turi buyurtmaga bog'liq ("Xaridor tovarni olganida ... yechib oldik",
    ``AD#<sotuv qatori id>-...``) va u qachon yechiladi: buyurtma kuniga, topshirilgan kunga nisbatan (kun), ``AD#``
    dagi sana nimani bildiradi. P&L hozir reklamani yechilgan kunga yozadi va o'sha kungi sotuvlarga tushum ulushida
    bo'ladi — bog'liq turi buyurtmaning o'ziga yozilishi kerakmi (07 Q10), shu raqamlar bilan hal qilinadi.
    Matnlar raqamlarsiz (``9``) — buyurtma raqami chiqmaydi."""
    base = (
        "FROM mp_expenses e LEFT JOIN LATERAL (SELECT s.id, s.status, s.ordered_at, s.issued_at FROM sale_items s "
        "WHERE s.shop_id = e.shop_id AND s.external_id = e.item_external_id ORDER BY s.ordered_at LIMIT 1) s ON true "
        "WHERE e.shop_id = :s AND e.category = 'advertising' AND e.excluded IS NULL"
    )
    rows = await conn.execute(
        text(
            "SELECT coalesce(e.raw_code, '<null>') AS code, count(*) AS n, coalesce(sum("
            + _NET
            + "), 0) AS amount, "
            "count(*) FILTER (WHERE e.name ILIKE '%olganida%') AS per_order_text, "
            "count(e.item_external_id) AS with_ad_id, count(s.id) AS linked "
            + base
            + " GROUP BY 1 ORDER BY 2 DESC"
        ),
        {"s": shop},
    )
    by_code = [{**dict(r._mapping), "amount": money(r.amount)} for r in rows]
    rows = await conn.execute(
        text(
            "SELECT left(regexp_replace(coalesce(e.name, '<null>'), '[0-9]', '9', 'g'), 120) AS name, "
            "count(*) AS n, coalesce(sum("
            + _NET
            + "), 0) AS amount "
            + base
            + " GROUP BY 1 ORDER BY 2 DESC LIMIT :n"
        ),
        {"s": shop, "n": SAMPLE},
    )
    names = [{**dict(r._mapping), "amount": money(r.amount)} for r in rows]
    charged, ordered, issued = _day("e.created_on"), _day("s.ordered_at"), _day("s.issued_at")
    ad_date = (
        "substring(e.raw ->> 'externalId' from 'AD#[0-9]+-[0-9]+-([0-9]{4}-[0-9]{2}-[0-9]{2})')"
    )
    rows = await conn.execute(
        text(
            "SELECT upper(trim(s.status)) AS status, count(*) AS n, coalesce(sum("
            + _NET
            + "), 0) AS amount, "
            f"count(*) FILTER (WHERE {charged} - {ordered} = 0) AS after_order_0, "
            f"count(*) FILTER (WHERE {charged} - {ordered} BETWEEN 1 AND 3) AS after_order_1_3, "
            f"count(*) FILTER (WHERE {charged} - {ordered} BETWEEN 4 AND 7) AS after_order_4_7, "
            f"count(*) FILTER (WHERE {charged} - {ordered} BETWEEN 8 AND 14) AS after_order_8_14, "
            f"count(*) FILTER (WHERE {charged} - {ordered} > 14) AS after_order_15_plus, "
            "count(*) FILTER (WHERE s.issued_at IS NULL) AS not_issued, "
            f"count(*) FILTER (WHERE {charged} = {issued}) AS on_issue_day, "
            f"count(*) FILTER (WHERE {charged} > {issued}) AS after_issue_day, "
            f"count(*) FILTER (WHERE {charged} < {issued}) AS before_issue_day, "
            f"count(*) FILTER (WHERE {ad_date} = to_char({ordered}, 'YYYY-MM-DD')) AS ad_date_is_order, "
            f"count(*) FILTER (WHERE {ad_date} = to_char({issued}, 'YYYY-MM-DD')) AS ad_date_is_issue, "
            f"count(*) FILTER (WHERE {ad_date} = to_char({charged}, 'YYYY-MM-DD')) AS ad_date_is_charge "
            + base
            + " AND s.id IS NOT NULL GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop},
    )
    linked = [{**dict(r._mapping), "amount": money(r.amount)} for r in rows]
    return {"by_code": by_code, "name_patterns": names, "linked_by_status": linked}


async def expense_dates_check(conn: AsyncConnection, shop: UUID, now: datetime) -> dict[str, Any]:
    """Xarajat sanasi (P&L kuni — ``dateCreated``) va ``dateService`` farqi (kun) toifa bo'yicha, oxirgi 60 kunda
    yechilgan kunlar soni (saqlash har kuni yechiladimi yoki bir necha kun birga). ``gap`` = yechilgan kun − xizmat
    kuni (Toshkent)."""
    service = "to_timestamp((raw ->> 'dateService')::bigint / 1000.0)"
    gap = f"CASE WHEN (raw ->> 'dateService') ~ '^[0-9]+$' THEN {_day('created_on')} - {_day(service)} END"
    rows = await conn.execute(
        text(
            "SELECT category, count(*) AS n, count(gap) AS with_service, "
            "count(*) FILTER (WHERE gap = 0) AS gap_0, count(*) FILTER (WHERE gap = 1) AS gap_1, "
            "count(*) FILTER (WHERE gap BETWEEN 2 AND 7) AS gap_2_7, count(*) FILTER (WHERE gap > 7) AS gap_8_plus, "
            "count(*) FILTER (WHERE gap < 0) AS gap_negative, "
            "count(*) FILTER (WHERE created_on >= :since) AS rows_60d, "
            f"count(DISTINCT {_day('created_on')}) FILTER (WHERE created_on >= :since) AS days_60d "
            f"FROM (SELECT category, created_on, {gap} AS gap FROM mp_expenses "
            "WHERE shop_id = :s AND excluded IS DISTINCT FROM 'status') t GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop, "since": now - timedelta(days=RECENT_DAYS)},
    )
    return {"by_category": [dict(r._mapping) for r in rows]}


async def expense_refs_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """ADR-039 keyingi qadami: reklama va logistikadan boshqa xarajatlar (saqlash, qaytim saqlash, jarima,
    kompensatsiya ...) qaysi SKU yoki sotuvga tegishli ekanini aniqlash — toifa bo'yicha matn va ``externalId``
    ko'rinishlari (raqamlar ``9``), buyurtma raqami (``№``) sotuv buyurtmasiga, ``externalId`` raqami sotuv qatori /
    SKU / mahsulot id'siga mos kelishi, qatordagi ``amount`` (dona) qiymatlari."""
    rows = await conn.execute(
        text(
            "SELECT e.category, count(*) AS n, "
            "count(e.order_external_id) AS with_order_no, "
            "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM sale_items s WHERE s.shop_id = e.shop_id "
            "AND s.order_id = e.order_external_id)) AS order_no_is_sale, "
            "count(*) FILTER (WHERE (e.raw ->> 'externalId') ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM sale_items s "
            "WHERE s.shop_id = e.shop_id AND s.external_id = (e.raw ->> 'externalId')::bigint)) AS ext_is_sale_line, "
            "count(*) FILTER (WHERE (e.raw ->> 'externalId') ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM mp_skus k "
            "WHERE k.shop_id = e.shop_id AND k.external_id = (e.raw ->> 'externalId')::bigint)) AS ext_is_sku, "
            "count(*) FILTER (WHERE (e.raw ->> 'externalId') ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM mp_products p "
            "WHERE p.shop_id = e.shop_id AND p.external_id = (e.raw ->> 'externalId')::bigint)) AS ext_is_product, "
            "count(*) FILTER (WHERE (e.raw ->> 'amount') ~ '^[0-9]+$' AND (e.raw ->> 'amount')::int > 1) AS qty_over_1 "
            "FROM mp_expenses e WHERE e.shop_id = :s AND e.category NOT IN ('advertising', 'logistics') "
            "GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop},
    )
    by_category = [dict(r._mapping) for r in rows]
    rows = await conn.execute(
        text(
            "SELECT category, left(regexp_replace(coalesce(name, '<null>'), '[0-9]', '9', 'g'), 120) AS name, "
            "left(regexp_replace(coalesce(raw ->> 'externalId', '<null>'), '[0-9]', '9', 'g'), 40) AS external_id, "
            "count(*) AS n, coalesce(sum(amount), 0) AS amount FROM mp_expenses "
            "WHERE shop_id = :s AND category NOT IN ('advertising', 'logistics') "
            "GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT :n"
        ),
        {"s": shop, "n": SAMPLE},
    )
    patterns = [{**dict(r._mapping), "amount": money(r.amount)} for r in rows]
    return {"by_category": by_category, "patterns": patterns}


async def logistics_differ_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """B4.20 natijasi: sotuv qatoridagi logistika va Uzum yechgani (bog'langan chiqimlar) farq qiladigan qatorlar
    namunalari — qaysi biri haqiqiy yechilgan pulni ko'rsatishini aniqlash uchun (buyurtma va topshirilgan kun, dona,
    qatordagi logistika, yechilgan chiqimlar va ularning soni). Qaytim (``logistics_refund``) qatorlari sotuvga
    bog'lanmaydi — ular uchun ``externalId`` va matn ko'rinishi."""
    charged, ordered, issued = _day("x.first_at"), _day("s.ordered_at"), _day("s.issued_at")
    rows = await conn.execute(
        text(
            "WITH x AS (SELECT e.sale_item_id AS id, sum(e.amount) AS charged, count(*) AS n, min(e.created_on) AS first_at "
            "FROM mp_expenses e WHERE e.shop_id = :s AND e.sale_item_id IS NOT NULL AND e.category = 'logistics' "
            "AND e.type = 'OUTCOME' GROUP BY 1) "
            f"SELECT upper(trim(s.status)) AS status, {ordered} AS ordered, {issued} AS issued, {charged} AS charged_on, "
            "s.amount, s.amount_returns, s.logistics_fee AS line_fee, coalesce(x.charged, 0) AS charged, "
            "coalesce(x.n, 0) AS charges FROM sale_items s LEFT JOIN x ON x.id = s.id "
            "WHERE s.shop_id = :s AND upper(trim(s.status)) <> 'CANCELED' "
            "AND abs(coalesce(x.charged, 0) - s.logistics_fee) > 1 ORDER BY s.ordered_at DESC LIMIT :n"
        ),
        {"s": shop, "n": SAMPLE},
    )
    samples = [
        {**dict(r._mapping), "line_fee": money(r.line_fee), "charged": money(r.charged)}
        for r in rows
    ]
    rows = await conn.execute(
        text(
            "SELECT left(regexp_replace(coalesce(raw ->> 'externalId', '<null>'), '[0-9]', '9', 'g'), 40) AS external_id, "
            "left(regexp_replace(coalesce(name, '<null>'), '[0-9]', '9', 'g'), 120) AS name, count(*) AS n "
            "FROM mp_expenses WHERE shop_id = :s AND category = 'logistics_refund' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 5"
        ),
        {"s": shop},
    )
    return {"samples": samples, "refund_patterns": [dict(r._mapping) for r in rows]}


STORAGE_DAYS = (30, 60, 90, 120)  # B4.22: saqlash qoidasi farazlari (kun)


async def storage_rule_check(conn: AsyncConnection, shop: UUID, now: datetime) -> dict[str, Any]:
    """B4.22: Uzum saqlashni qaysi tovar uchun oladi — oxirgi 3 xizmat kunining o'rtacha yechilgan summasi va joriy
    qoldiq bo'yicha farazlar (``qty_active`` × ``paidStoragePriceItem``): hammasi; aylanma — qoldiqning ``N`` kunlik
    sotuvdan (``avgdsales``) ortig'i yoki shunday SKU butunligicha; yosh — ``N`` kundan oldin yaratilgan postavkalardan
    qolgan dona (oxirgi ``N`` kun postavkalari bepul deb). Qaysi model yechilgan summaga yaqin — qoida shu."""
    service = _day("to_timestamp((e.raw ->> 'dateService')::bigint / 1000.0)")
    charged_rows = list(
        await conn.execute(
            text(
                f"SELECT {service} AS day, sum(e.amount) AS charged FROM mp_expenses e WHERE e.shop_id = :s "
                "AND e.category = 'storage' AND e.excluded IS NULL AND (e.raw ->> 'dateService') ~ '^[0-9]+$' "
                "GROUP BY 1 ORDER BY 1 DESC LIMIT 3"
            ),
            {"s": shop},
        )
    )
    skus = list(
        await conn.execute(
            text(
                "SELECT id, coalesce(qty_active, 0) AS qty, coalesce(avg_daily_sales, 0) AS speed, storage_price "
                "FROM mp_skus WHERE shop_id = :s AND coalesce(qty_active, 0) > 0"
            ),
            {"s": shop},
        )
    )
    arrivals: dict[UUID, list[tuple[datetime, int]]] = defaultdict(list)
    for r in await conn.execute(
        text(
            "SELECT i.sku_id, v.created_on, i.quantity_accepted FROM fbo_invoice_items i "
            "JOIN fbo_invoices v ON v.id = i.invoice_id WHERE v.shop_id = :s AND i.sku_id IS NOT NULL "
            "AND upper(coalesce(v.status, '')) = 'ACCEPTED' AND v.created_on IS NOT NULL"
        ),
        {"s": shop},
    ):
        arrivals[r.sku_id].append((r.created_on, int(r.quantity_accepted or 0)))
    prices = [Decimal(r.storage_price) for r in skus if r.storage_price]
    models: dict[str, Decimal] = {"all": Decimal(0)}
    for r in skus:
        price = Decimal(r.storage_price or 0)
        qty, speed = int(r.qty), Decimal(r.speed)
        models["all"] += qty * price
        for n in STORAGE_DAYS:
            excess = max(Decimal(0), qty - speed * n)
            models[f"turnover_excess_{n}"] = (
                models.get(f"turnover_excess_{n}", Decimal(0)) + excess * price
            )
            slow = qty if speed == 0 or qty / speed > n else 0
            models[f"turnover_whole_{n}"] = (
                models.get(f"turnover_whole_{n}", Decimal(0)) + slow * price
            )
            fresh = sum(q for at, q in arrivals.get(r.id, []) if at >= now - timedelta(days=n))
            models[f"age_{n}"] = models.get(f"age_{n}", Decimal(0)) + max(0, qty - fresh) * price
    charged = (
        sum((Decimal(r.charged) for r in charged_rows), Decimal(0)) / len(charged_rows)
        if charged_rows
        else None
    )
    # ADR-040: dasturdagi Uzum qoidasi (aylanma > 60 kun, yangi SKU emas) bo'yicha oxirgi yechilgan kunning modeli.
    rule: dict[str, Decimal] = {}
    if charged_rows:
        rule = (await storage_split(conn, {(shop, charged_rows[0].day)})).get(
            (shop, charged_rows[0].day), {}
        )
    models["uzum_rule"] = sum(rule.values(), Decimal(0))
    return {
        "rule_skus": len(rule),
        "charged_last": money(Decimal(charged_rows[0].charged)) if charged_rows else None,
        "charged_days": [r.day for r in charged_rows],
        "charged_avg": None if charged is None else money(round(charged, 2)),
        "skus_in_stock": len(skus),
        "price_min": money(min(prices)) if prices else None,
        "price_max": money(max(prices)) if prices else None,
        "models": {k: money(round(v, 2)) for k, v in models.items()},
    }


async def expense_links_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """B4.22: jarima ("№ ... yuk xati", qabul farqi) postavkaga, qaytim saqlash ("N - sonli yukxat") qaytarishga
    bog'lanadimi — raqam qaysi ustunga mos (``fbo_invoices`` id / raqami, ``mp_returns`` id / xom raqamlari), shu
    postavkada farqi bor SKU'lar soni."""
    fines = await _scalar_row(
        conn,
        "SELECT count(*) AS fines, "
        "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM fbo_invoices v WHERE v.shop_id = e.shop_id "
        "AND v.number = e.order_external_id)) AS number_is_invoice_number, "
        "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM fbo_invoices v WHERE v.shop_id = e.shop_id "
        "AND v.external_id = e.order_external_id)) AS number_is_invoice_id, "
        "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM fbo_invoices v JOIN fbo_invoice_items i ON i.invoice_id = v.id "
        "WHERE v.shop_id = e.shop_id AND (v.number = e.order_external_id OR v.external_id = e.order_external_id) "
        "AND i.quantity_to_stock <> i.quantity_accepted)) AS invoice_has_diff_sku "
        "FROM mp_expenses e WHERE e.shop_id = :s AND e.category = 'fine'",
        shop,
    )
    num = "nullif(substring(coalesce(e.name, '') from '^([0-9]+)'), '')::bigint"
    returns = await _scalar_row(
        conn,
        f"SELECT count(*) AS rows, count({num}) AS with_number, "
        f"count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mp_returns r WHERE r.shop_id = e.shop_id AND r.external_id = {num})) "
        "AS number_is_return_id, "
        f"count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mp_returns r WHERE r.shop_id = e.shop_id AND r.raw::text LIKE "
        f"'%' || {num}::text || '%')) AS number_in_return_raw "
        "FROM mp_expenses e WHERE e.shop_id = :s AND e.category = 'return_storage'",
        shop,
    )
    return {"fines": fines, "return_storage": returns}


async def logistics_payout_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """B4.22: qatordagi logistika va Uzum yechgani farq qilgan Yakunlangan qatorlarda Uzum aslida qancha to'lagan —
    ``withdrawnProfit`` (yechib olingan) / ``sellerProfit`` ↔ tushum − komissiya − qatordagi yoki yechilgan logistika."""
    return await _scalar_row(
        conn,
        "WITH x AS (SELECT e.sale_item_id AS id, sum(e.amount) AS charged FROM mp_expenses e WHERE e.shop_id = :s "
        "AND e.sale_item_id IS NOT NULL AND e.category = 'logistics' AND e.type = 'OUTCOME' GROUP BY 1), "
        "l AS (SELECT s.sell_price * s.amount - s.commission AS net, s.logistics_fee AS fee, coalesce(x.charged, 0) AS charged, "
        "nullif(s.raw ->> 'withdrawnProfit', '')::numeric AS withdrawn, nullif(s.raw ->> 'sellerProfit', '')::numeric AS profit "
        "FROM sale_items s JOIN x ON x.id = s.id WHERE s.shop_id = :s AND upper(trim(s.status)) = 'TO_WITHDRAW' "
        "AND abs(x.charged - s.logistics_fee) > 1) "
        "SELECT count(*) AS lines, coalesce(sum(fee), 0) AS line_fee, coalesce(sum(charged), 0) AS charged, "
        "count(*) FILTER (WHERE abs(withdrawn - (net - fee)) <= 1) AS withdrawn_is_minus_line_fee, "
        "count(*) FILTER (WHERE abs(withdrawn - (net - charged)) <= 1) AS withdrawn_is_minus_charged, "
        "count(*) FILTER (WHERE withdrawn = 0) AS withdrawn_zero, "
        "count(*) FILTER (WHERE abs(profit - (net - fee)) <= 1) AS profit_is_minus_line_fee, "
        "count(*) FILTER (WHERE abs(profit - (net - charged)) <= 1) AS profit_is_minus_charged FROM l",
        shop,
    )


async def storage_model_check(conn: AsyncConnection, shop: UUID, now: datetime) -> dict[str, Any]:
    """F43 tekshiruvi (oxirgi 30 kun): Uzum yechgan saqlash (xizmat kuni bo'yicha) ↔ shu kungi qoldiq snapshoti ×
    SKU saqlash narxi (``paidStoragePriceItem``) yig'indisi. Nisbat ~1 bo'lsa narx "dona/kun" va og'irlik to'g'ri."""
    service = _day("to_timestamp((e.raw ->> 'dateService')::bigint / 1000.0)")
    rows = await conn.execute(
        text(
            f"WITH c AS (SELECT {service} AS day, sum(e.amount) AS charged FROM mp_expenses e "
            "WHERE e.shop_id = :s AND e.category = 'storage' AND e.excluded IS NULL "
            "AND (e.raw ->> 'dateService') ~ '^[0-9]+$' AND e.created_on >= :since GROUP BY 1), "
            "m AS (SELECT d.day, sum(d.qty_active * coalesce(k.storage_price, 0)) AS model, "
            "sum(d.qty_active) AS qty, count(*) FILTER (WHERE d.qty_active > 0 AND k.storage_price IS NULL) AS no_price "
            "FROM sku_daily d JOIN mp_skus k ON k.id = d.sku_id WHERE k.shop_id = :s AND d.day >= :since_day GROUP BY 1) "
            "SELECT c.day, c.charged, m.model, m.qty, m.no_price FROM c LEFT JOIN m ON m.day = c.day ORDER BY 1"
        ),
        {
            "s": shop,
            "since": now - timedelta(days=30),
            "since_day": (now - timedelta(days=31)).date(),
        },
    )
    days = [
        {
            "day": r.day,
            "charged": money(r.charged),
            "model": None if r.model is None else money(r.model),
            "qty": r.qty,
            "skus_without_price": r.no_price,
        }
        for r in rows
    ]
    return {"days": days}


async def expenses_check(conn: AsyncConnection, shop: UUID) -> dict[str, Any]:
    """Toifalar (P&L'dan chiqarilganlari sababi bilan), holatlar va "boshqa" toifasiga tushgan kodlar."""
    rows = await conn.execute(
        text(
            "SELECT category, type, coalesce(excluded, '') AS excluded, count(*) AS n, sum(amount) AS amount "
            "FROM mp_expenses WHERE shop_id = :s GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
        ),
        {"s": shop},
    )
    by_category = [
        {**dict(r._mapping), "amount": money(r.amount), "excluded": r.excluded or None}
        for r in rows
    ]
    rows = await conn.execute(
        text(
            "SELECT coalesce(status, '<null>'), count(*) FROM mp_expenses WHERE shop_id = :s "
            "GROUP BY 1 ORDER BY 2 DESC"
        ),
        {"s": shop},
    )
    statuses = {r[0]: r[1] for r in rows}
    rows = await conn.execute(
        text(
            "SELECT coalesce(raw_code, '<null>') AS code, raw ->> 'source' AS source, count(*) AS n, "
            "sum(amount) AS amount FROM mp_expenses WHERE shop_id = :s AND category = 'other' "
            "GROUP BY 1, 2 ORDER BY 3 DESC LIMIT :n"
        ),
        {"s": shop, "n": SAMPLE},
    )
    other = [{**dict(r._mapping), "amount": money(r.amount)} for r in rows]
    return {"by_category": by_category, "statuses": statuses, "other_codes": other}


# --- Sinxron holati -----------------------------------------------------------------------------


# Uzum SKU qoldiq maydonlari (``/v1/product/shop``): ma'nosi to'liq hujjatlanmagan — real ma'lumotda yig'indilar.
STOCK_FIELDS = (
    "quantityActive",
    "quantityFbs",
    "quantityAvailable",
    "quantityReserved",
    "quantityPending",
    "quantityDefected",
    "quantityOnPhotoStudio",
    "quantityAdditional",
    "quantityArchived",
    "quantityCreated",
    "quantityMissing",
    "quantitySold",
    "quantityReturned",
)
RECENT_DAYS = 60


def _num(raw: dict[str, Any], name: str) -> int:
    value = raw.get(name)
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


async def stock_check(conn: AsyncConnection, shop: UUID, now: datetime) -> dict[str, Any]:
    """ADR-034: qoldiq joylari maydonlari ma'nosi uchun yig'indilar (faqat sonlar, nomlarsiz)."""
    skus = (
        await conn.execute(
            text(
                "SELECT k.raw AS raw, coalesce(p.raw -> 'status' ->> 'value', '<null>') AS product_status "
                "FROM mp_skus k LEFT JOIN mp_products p ON p.id = k.product_id WHERE k.shop_id = :s"
            ),
            {"s": shop},
        )
    ).all()
    fields: dict[str, dict[str, int]] = {}
    by_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    extra_keys: Counter[str] = Counter()
    by_stock_type: Counter[str] = Counter()
    mismatches: Counter[str] = Counter()
    for r in skus:
        raw = r.raw or {}
        sku_status = raw.get("status")
        status = (
            sku_status.get("value") if isinstance(sku_status, dict) else sku_status
        ) or "<null>"
        key = f"{r.product_status} / {status}"
        by_status[key]["skus"] += 1

        for name in STOCK_FIELDS:
            v = _num(raw, name)
            f = fields.setdefault(name, {"sum": 0, "nonzero": 0, "missing": 0})
            f["sum"] += v
            f["nonzero"] += v != 0
            f["missing"] += name not in raw
            if v:
                by_status[key][name] += v
        extra_keys.update(
            k
            for k in raw
            if k.startswith("quantity")
            and k not in STOCK_FIELDS
            and k != "quantityAvailableByStockType"
        )
        typed = raw.get("quantityAvailableByStockType")
        if isinstance(typed, dict):
            by_stock_type.update(f"{k}: {pattern(v)}" for k, v in typed.items())
        elif typed is not None:
            by_stock_type[pattern(typed)] += 1
        # Munosabatlar: qaysi maydon qaysining yig'indisi ekanini aniqlash uchun (mos kelmagan SKU'lar soni).
        if _num(raw, "quantityAvailable") != _num(raw, "quantityActive") + _num(raw, "quantityFbs"):
            mismatches["available != active + fbs"] += 1
        if _num(raw, "quantityAvailable") != _num(raw, "quantityActive"):
            mismatches["available != active"] += 1
        if _num(raw, "quantityReserved") > _num(raw, "quantityActive") + _num(raw, "quantityFbs"):
            mismatches["reserved > active + fbs"] += 1
    invoices = await conn.execute(
        text(
            "SELECT coalesce(status, '<null>') AS status, count(*) AS n, coalesce(sum(to_stock), 0) AS to_stock, "
            "coalesce(sum(accepted), 0) AS accepted, "
            "count(*) FILTER (WHERE raw -> 'dateAccepted' IS NOT NULL AND raw ->> 'dateAccepted' <> 'null') "
            "AS with_date_accepted, max(created_on) AS last FROM fbo_invoices WHERE shop_id = :s "
            "GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop},
    )
    returns = await conn.execute(
        text(
            "SELECT r.type, coalesce(r.status, '<null>') AS status, count(DISTINCT r.id) AS n, "
            "coalesce(sum(i.quantity), 0) AS units, max(r.created_on) AS last "
            "FROM mp_returns r LEFT JOIN mp_return_items i ON i.return_id = r.id WHERE r.shop_id = :s "
            "GROUP BY 1, 2 ORDER BY 1, 2"
        ),
        {"s": shop},
    )
    sales = await conn.execute(
        text(
            "SELECT status, count(*) AS lines, coalesce(sum(amount), 0) AS amount, "
            "coalesce(sum(amount_returns), 0) AS amount_returns FROM sale_items "
            "WHERE shop_id = :s AND ordered_at >= :since GROUP BY 1 ORDER BY 1"
        ),
        {"s": shop, "since": now - timedelta(days=RECENT_DAYS)},
    )
    return {
        "skus": len(skus),
        "fields": fields,
        "by_status": {k: dict(v) for k, v in sorted(by_status.items())},
        "extra_quantity_keys": dict(extra_keys.most_common(SAMPLE)),
        "available_by_stock_type": dict(by_stock_type.most_common(SAMPLE)),
        "mismatches": dict(mismatches),
        "invoices_by_status": [dict(r._mapping) for r in invoices],
        "returns_by_type_status": [dict(r._mapping) for r in returns],
        f"sales_last_{RECENT_DAYS}d_by_status": [dict(r._mapping) for r in sales],
    }


async def sync_check(conn: AsyncConnection, shop: UUID, since: datetime) -> dict[str, Any]:
    rows = await conn.execute(
        text(
            "SELECT kind, last_status, last_success_at, last_attempt_at, failures, last_error "
            "FROM sync_state WHERE shop_id = :s ORDER BY kind"
        ),
        {"s": shop},
    )
    state = {r.kind: {k: v for k, v in r._mapping.items() if k != "kind"} for r in rows}
    rows = await conn.execute(
        text(
            "SELECT kind, status, count(*) FROM sync_runs WHERE shop_id = :s AND started_at >= :t "
            "GROUP BY 1, 2 ORDER BY 1, 2"
        ),
        {"s": shop, "t": since},
    )
    runs: dict[str, dict[str, int]] = defaultdict(dict)
    for kind, status, n in rows:
        runs[kind][status] = n
    rows = await conn.execute(
        text(
            "SELECT kind, status, mode, error, http_status, started_at FROM sync_runs "
            "WHERE shop_id = :s AND started_at >= :t AND status IN ('error', 'warning') "
            "ORDER BY started_at DESC LIMIT :n"
        ),
        {"s": shop, "t": since, "n": SAMPLE},
    )
    problems = [dict(r._mapping) for r in rows]
    errors = sum(n for by in runs.values() for status, n in by.items() if status == "error")
    return {"state": state, "runs_24h": dict(runs), "errors_24h": errors, "problems": problems}


# --- Yig'ish -------------------------------------------------------------------------------------


async def org_ids(engine: AsyncEngine) -> list[UUID]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT DISTINCT org_id FROM sync_accounts() ORDER BY 1"))
        return [r[0] for r in rows]


async def shop_report(
    conn: AsyncConnection, shop: Any, since: datetime, now: datetime
) -> dict[str, Any]:
    sales = await _sales(conn, shop.id)
    return {
        "external_id": shop.external_id,
        "name": shop.name,
        "active": shop.active,
        "history_status": shop.history_status,
        "first_sale_on": shop.first_sale_on,
        "sales": sales_report(sales),
        "checks": {
            "invoices": await invoices_check(conn, shop.id),
            "returns": await returns_check(conn, shop.id),
            "logistics": await logistics_check(conn, shop.id),
            "processing_logistics": await processing_logistics_check(conn, shop.id),
            "logistics_reconcile": await logistics_reconcile_check(conn, shop.id),
            "ads": await ads_check(conn, shop.id),
            "expense_dates": await expense_dates_check(conn, shop.id, now),
            "expense_refs": await expense_refs_check(conn, shop.id),
            "logistics_differ": await logistics_differ_check(conn, shop.id),
            "storage_model": await storage_model_check(conn, shop.id, now),
            "storage_rule": await storage_rule_check(conn, shop.id, now),
            "expense_links": await expense_links_check(conn, shop.id),
            "logistics_payout": await logistics_payout_check(conn, shop.id),
            "expenses": await expenses_check(conn, shop.id),
            "stock": await stock_check(conn, shop.id, now),
        },
        "sync": await sync_check(conn, shop.id, since),
    }


async def build(
    engine: AsyncEngine, orgs: Iterable[UUID] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=24)
    out: dict[str, Any] = {"format": FORMAT, "generated_at": now, "orgs": []}
    for org in orgs if orgs is not None else await org_ids(engine):
        async with org_transaction(engine, org) as conn:
            name = await conn.scalar(text("SELECT name FROM orgs WHERE id = :o"), {"o": org})
            shops = await conn.execute(
                text(
                    "SELECT id, external_id, name, active, history_status, first_sale_on FROM shops "
                    "ORDER BY external_id"
                )
            )
            out["orgs"].append(
                {
                    "id": org,
                    "name": name,
                    "shops": [await shop_report(conn, s, since, now) for s in shops.all()],
                }
            )
    return out


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return money(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _storage_ratio(days: list[dict[str, Any]]) -> str:
    """F43: Uzum yechgan saqlash / qoldiq × narx modeli (snapshot bor kunlar bo'yicha)."""
    pairs = [(Decimal(d["charged"]), Decimal(d["model"])) for d in days if d["model"] is not None]
    model = sum((m for _, m in pairs), Decimal(0))
    if not pairs or model == 0:
        return "taqqoslab bo'lmadi"
    return f"{len(pairs)} kunda nisbat {sum((c for c, _ in pairs), Decimal(0)) / model:.2f}"


def summary(report: dict[str, Any]) -> list[str]:
    """Odam o'qiydigan qisqa xulosa (stderr): har do'kon bo'yicha asosiy raqamlar."""
    out = []
    for org in report["orgs"]:
        for shop in org["shops"]:
            sales, checks, sync = shop["sales"], shop["checks"], shop["sync"]
            inv, ret, lg = checks["invoices"], checks["returns"], checks["logistics"]
            pl = checks["processing_logistics"]
            ads = checks["ads"]["by_code"]
            rec = checks["logistics_reconcile"]["by_status"]
            canceled = next((r for r in rec if r["status"] == "CANCELED"), None)
            storage = next(
                (r for r in checks["expense_dates"]["by_category"] if r["category"] == "storage"),
                None,
            )
            out.append(
                f"{shop['name']} ({shop['external_id']}): tarix={shop['history_status']}, "
                f"sotuv qatorlari={len(sales['lines'])}, oylar={len(sales['months'])}; "
                f"postavka tarkibi {inv['items_linked']}/{inv['items']} SKU'ga bog'langan; "
                f"qaytarishlar {ret['returns']}; logistika {lg['linked']}/{lg['expenses']} sotuvga "
                f"bog'langan; jarayonda {pl['processing']} qator (topshirilmagan va logistika 0: "
                f"{pl['not_issued_zero']}, topshirilgan va 0: {pl['issued_zero']}); "
                f"logistika qator ↔ yechilgan farqi: {sum(r['differ'] for r in rec)} qator, bekor "
                f"qatorlarda yechilgan {canceled['expense_net'] if canceled else '0'} so'm; "
                f"reklama {sum(r['n'] for r in ads)} qator, shundan buyurtmaga bog'liq matn "
                f"{sum(r['per_order_text'] for r in ads)}, sotuvga bog'langan {sum(r['linked'] for r in ads)}; "
                f"saqlash 60 kunda {storage['days_60d'] if storage else 0} kun yechilgan, model bilan "
                f"{_storage_ratio(checks['storage_model']['days'])}; "
                f"24 soatda xato ishlar: {sync['errors_24h']}; "
                f"qoldiq maydonlari: {checks['stock']['skus']} SKU, postavka holatlari "
                f"{len(checks['stock']['invoices_by_status'])}, qaytarish holatlari "
                f"{len(checks['stock']['returns_by_type_status'])}"
            )
    return out


async def run(settings: Settings, stream: TextIO, orgs: Iterable[UUID] | None = None) -> int:
    engine = make_engine(settings.database_url)
    try:
        report = await build(engine, orgs)
    finally:
        await engine.dispose()
    json.dump(report, stream, ensure_ascii=False, default=_json)
    stream.write("\n")
    for line in summary(report) or ["Ulangan do'kon yo'q — avval kalitni kiriting."]:
        print(line, file=sys.stderr)
    return 0 if report["orgs"] else 1


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — jarayon kirish nuqtasi
    parser = argparse.ArgumentParser(description="B2.11 real sinov hisoboti (JSON → stdout)")
    parser.add_argument("--org", action="append", type=UUID, help="faqat shu tashkilot(lar)")
    args = parser.parse_args(argv)
    return asyncio.run(run(get_settings(), sys.stdout, args.org))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
