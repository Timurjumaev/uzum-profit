"""``/ads``: reklama tahlili (B5.5, F19, F42, F58). Ruxsat — ``view_finance``.

Open API'da kampaniya, ko'rish va klik yo'q — faqat Uzum yechgan summa (``Y000119`` / ``Y000120`` / ``Y000050``), shuning
uchun ROMI va CTR bu yerda yo'q (va'da qilinmaydi). Reklama turlari — Uzum kodi va uning o'z matni bo'yicha (kodlar ma'nosi
taxmin qilinmaydi); kunlik DRR trendi (F19); SKU bo'yicha ACOS (F19) va "reklama foydasini yeb qo'ygan SKU" (F58).
Reklama summasi hisob varag'idagi bilan bir xil: Uzum yechgani va hali yechilmagan Jarayondagi sotuvga F42 taxmini
(``estimated``).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import ExpenseCategory, signed_amount
from upcore.metrics import ads_eat_profit, drr, ratio
from upcore.money import Currency, Money
from upcore.pnl import Statement

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.costs import day_start
from upapi.db import models as m
from upapi.reports import cells as rc
from upapi.reports.common import Filters, Heavy, Meta, filters, meta, sku_catalog

router = APIRouter(tags=["reports"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
Filter = Annotated[Filters, Depends(filters)]
KINDS = ["orders", "expenses"]
UZS = Currency.UZS
ZERO = Money.zero(UZS)
TOP_SKUS = 50


class AdsTypeOut(BaseModel):
    code: str | None  # Uzum xarajat kodi (``Y000120`` ...); null — kodsiz qator
    name: str | None  # Uzumning o'z matni (eng ko'p uchragani)
    amount: Decimal  # davrda Uzum yechgan (kompensatsiya ayirilgan)
    share: Decimal | None  # yechilgan reklama ichidagi ulush


class AdsDayOut(BaseModel):
    day: date
    ads: Decimal
    revenue: Decimal  # F3
    drr: Decimal | None  # F19


class AdsSkuOut(BaseModel):
    sku_id: UUID
    shop_id: UUID | None
    title: str | None
    revenue: Decimal  # F3
    ads: Decimal  # bog'langan + taqsimlangan (F19)
    acos: Decimal | None  # F19
    net_profit: Decimal  # F12
    eats_profit: bool  # F58


class AdsOut(BaseModel):
    meta: Meta
    total: Decimal  # F9 reklama (yechilgan + taxminiy)
    estimated: Decimal  # shundan F42 taxmini (Uzum hali yechmagan)
    revenue: Decimal  # F3
    drr: Decimal | None  # F19
    by_type: list[AdsTypeOut]
    daily: list[AdsDayOut]
    skus: list[AdsSkuOut]  # reklamasi eng ko'p SKU'lar (ACOS)
    eaten: list[AdsSkuOut]  # F58: reklama foydasini yeb qo'ygan SKU'lar
    eaten_total: int  # F58 bo'yicha jami SKU soni (ro'yxat TOP_SKUS bilan kesilgan bo'lishi mumkin)
    skipped: int  # F58 uchun tekshirib bo'lmadigan (tannarxsiz qismli) reklamali SKU'lar


def _ads(s: Statement) -> Money:
    return s.uzum_expenses.get(ExpenseCategory.ADVERTISING, ZERO)


async def _by_type(conn: AsyncConnection, f: Filters) -> list[AdsTypeOut]:
    e = m.mp_expenses
    query = select(e.c.code, e.c.name, e.c.type, e.c.amount).where(
        e.c.category == ExpenseCategory.ADVERTISING.value,
        e.c.excluded.is_(None),
        e.c.created_on >= day_start(f.period.start),
        e.c.created_on < day_start(f.period.end + timedelta(days=1)),
    )
    if f.shops:
        query = query.where(e.c.shop_id.in_(f.shops))
    sums: dict[str | None, Money] = {}
    names: dict[str | None, dict[str, int]] = {}
    for row in await conn.execute(query):
        amount = signed_amount(Money(row.amount, UZS), row.type)
        sums[row.code] = sums.get(row.code, ZERO) + amount
        if row.name:
            seen = names.setdefault(row.code, {})
            seen[row.name] = seen.get(row.name, 0) + 1
    whole = sum((v.amount for v in sums.values()), Decimal(0))
    out = []
    for code, amount in sorted(sums.items(), key=lambda kv: (-kv[1].amount, str(kv[0]))):
        label = max(names[code], key=lambda n: (names[code][n], n)) if code in names else None
        out.append(
            AdsTypeOut(
                code=code, name=label, amount=amount.amount, share=ratio(amount.amount, whole)
            )
        )
    return out


@router.get("/orgs/{org_id}/ads", response_model=AdsOut)
async def ads(ctx: Finance, f: Filter, _: Heavy) -> AdsOut:
    conn = ctx.conn
    book = await rc.load_book(conn, f.period, f.today)
    cur = book.scoped(f, f.period)
    by_day, whole = cur.by_and_total(lambda k: k.day)
    by_sku = {k: v for k, v in cur.by_sku().items() if k is not None and k != rc.UNLINKED}

    daily = []
    for i in range(f.period.days):
        day = f.period.start + timedelta(days=i)
        st = by_day.get(day)
        spent, revenue = (_ads(st), st.revenue) if st is not None else (ZERO, ZERO)
        daily.append(
            AdsDayOut(day=day, ads=spent.amount, revenue=revenue.amount, drr=drr(spent, revenue))
        )

    rows = []
    skipped = 0
    for key, st in by_sku.items():
        spent = _ads(st)
        if spent.amount <= 0:
            continue
        costed = st.uncovered_lines == 0
        skipped += 0 if costed else 1
        rows.append((key, st, spent, ads_eat_profit(st.net_profit, spent, fully_costed=costed)))
    catalog = await sku_catalog(conn, ids=[UUID(k) for k, *_rest in rows]) if rows else {}

    def out(item: tuple[str, Statement, Money, bool]) -> AdsSkuOut:
        key, st, spent, eats = item
        info = catalog.get(UUID(key))
        return AdsSkuOut(
            sku_id=UUID(key),
            shop_id=info.shop_id if info else None,
            title=(info.title or info.product_title) if info else None,
            revenue=st.revenue.amount,
            ads=spent.amount,
            acos=ratio(spent.amount, st.revenue.amount),
            net_profit=st.net_profit.amount,
            eats_profit=eats,
        )

    by_ads = sorted(rows, key=lambda r: (-r[2].amount, r[0]))
    eaten = [r for r in by_ads if r[3]]
    estimated = whole.uzum_estimated.get(ExpenseCategory.ADVERTISING, ZERO)
    return AdsOut(
        meta=await meta(conn, f, KINDS),
        total=_ads(whole).amount,
        estimated=estimated.amount,
        revenue=whole.revenue.amount,
        drr=drr(_ads(whole), whole.revenue),
        by_type=await _by_type(conn, f),
        daily=daily,
        skus=[out(r) for r in by_ads[:TOP_SKUS]],
        eaten=[out(r) for r in eaten[:TOP_SKUS]],
        eaten_total=len(eaten),
        skipped=skipped,
    )
