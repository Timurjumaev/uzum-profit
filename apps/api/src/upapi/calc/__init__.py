"""Hisob ishlari (B2.8; 03 §5 "Hosila jadvallar", §6 "Sinxrondan keyin", §7): lotlar, sotuv tannarxi, kunlik agregat.

Manba jadvallar (Uzum faktlari va sotuvchi kiritgan xaridlar) o'zgarganda shu tranzaksiyada ``recalc_queue`` ga
so'rov yoziladi (:mod:`upapi.calc.queue`). Hisob ishi (:func:`recalc_org`, Procrastinate ``calc.org``, tashkilot
bo'yicha bitta) navbatni o'qiydi va bitta tranzaksiyada:

1. ``purchase`` → lotlar (F20, :mod:`upapi.calc.lots`) → lotlari o'zgargan tovarlar;
2. ``shop`` → shu kundan sotuvi bor tovarlar va bog'lanmagan sotuvlar;
3. tovarlar → ``sale_costs`` (F21, :mod:`upapi.calc.costs`), faqat o'zgargan qatorlar; "qayta hisoblandi" belgisi;
4. o'zgargan kunlar (va ``metrics``) → ``daily_sku_metrics`` (:mod:`upapi.calc.daily`);
5. bajarilgan so'rovlar o'chiriladi.

Hosila jadvallar istalgan payt manbadan qayta qurilishi mumkin: :func:`upapi.calc.queue.request_full`; tungi
``calc.nightly`` ishi shuni har tashkilot uchun qiladi (masalan, CBU arxivi keyin kelib, kurs o'zgargan bo'lsa).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.calc import costs, daily, lots
from upapi.calc.queue import Scope, request, request_full
from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.logs import get_logger

__all__ = ["CalcResult", "Scope", "recalc_org", "request", "request_full"]
_log = get_logger("upapi.calc")


@dataclass
class CalcResult:
    """``status``: ``done`` yoki ``idle`` (navbat bo'sh)."""

    status: str
    requests: int = 0
    lots: int = 0
    costs_written: int = 0
    costs_deleted: int = 0
    metric_rows: int = 0
    errors: dict[str, str] = field(default_factory=dict)  # xarid id → sabab (F20 hisoblanmadi)


def _shop_requests(
    pending: Sequence[Row[Any]], scope: Scope, all_shops: Sequence[UUID]
) -> dict[UUID, date | None]:
    """Do'kon so'rovlari → do'kon → eng erta kun (``ref_id`` NULL — hamma do'konlar)."""
    out: dict[UUID, date | None] = {}
    for r in pending:
        if r.kind != scope.value:
            continue
        for shop_id in all_shops if r.ref_id is None else [r.ref_id]:
            costs.merge_day(out, shop_id, r.since)
    return out


async def recalc_org(engine: AsyncEngine, org_id: UUID, now: datetime) -> CalcResult:
    """Tashkilot navbatidagi qayta hisoblarni bajaradi (bitta tranzaksiya, RLS ichida)."""
    q = m.recalc_queue
    async with org_transaction(engine, org_id) as conn:
        # Bir tashkilotga bitta hisob (Procrastinate qulfidan tashqari chaqiruvlar uchun ham).
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended('calc:' || :org, 0))"),
            {"org": str(org_id)},
        )
        # FOR UPDATE: hisob paytida kelgan so'rov (sinxron upsert'i) shu tranzaksiya tugashini kutadi va
        # o'chirilgan qator o'rniga yangisini yozadi — yo'qolmaydi.
        pending = list(await conn.execute(select(q).with_for_update()))
        if not pending:
            return CalcResult("idle")
        result = CalcResult("done", requests=len(pending))
        today = now.astimezone(costs.TASHKENT).date()
        method = await costs.method_of(conn, org_id)

        def refs(scope: Scope) -> list[UUID | None]:
            return [r.ref_id for r in pending if r.kind == scope.value]

        purchases, items_req = refs(Scope.PURCHASE), refs(Scope.ITEM)
        all_shops = [r.id for r in await conn.execute(select(m.shops.c.id))]
        shops_sales = _shop_requests(pending, Scope.SHOP, all_shops)
        shops_metrics = _shop_requests(pending, Scope.METRICS, all_shops)

        items = None if None in items_req else {i for i in items_req if i is not None}

        if purchases:
            built = await lots.rebuild_lots(
                conn, org_id, None if None in purchases else {p for p in purchases if p}, today
            )
            result.lots = built.written
            result.errors = {str(k): v for k, v in built.errors.items()}
            if items is not None:
                items |= built.items

        changes = costs.Changes()
        for shop_id, since in shops_sales.items():
            costs.merge_day(changes.days, shop_id, since)
            if items is not None:  # hammasi qayta hisoblansa — pastda bir marta
                items |= await costs.items_with_sales(conn, shop_id, since)
                changes.add(
                    await costs.recompute_unlinked(conn, org_id, shop_id, since, method, now)
                )
        if items is None:
            changes.add(await costs.recompute_unlinked(conn, org_id, None, None, method, now))
        if items is None or items:
            changes.add(await costs.recompute_items(conn, org_id, items, method, now))
        result.costs_written, result.costs_deleted = changes.written, changes.deleted

        for shop_id, since in shops_metrics.items():
            costs.merge_day(changes.days, shop_id, since)
        result.metric_rows = await daily.rebuild(conn, org_id, changes.days.items())

        await conn.execute(delete(q).where(q.c.id.in_([r.id for r in pending])))
    _log.info(
        "calc_done",
        org_id=str(org_id),
        requests=result.requests,
        lots=result.lots,
        costs_written=result.costs_written,
        costs_deleted=result.costs_deleted,
        metric_rows=result.metric_rows,
        errors=len(result.errors),
    )
    return result
