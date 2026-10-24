"""Sintetik seed (B2.2): ma'lumotnomalar (core seed'laridan) va bitta demo tashkilot.

Faqat dev/test uchun, real ma'lumot yo'q. Ishga tushirish (superuser URL — ``users`` ga yozish ilova roliga
berilmagan): ``uv run python -m upapi.db.seed postgresql://uzum:uzum@localhost:5432/uzum`` yoki
``UP_MIGRATION_DATABASE_URL`` bilan argumentsiz.
Takror ishga tushirish xavfsiz: ma'lumotnomalar ``ON CONFLICT DO NOTHING``, demo tashkilot bor bo'lsa o'tkaziladi.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.expenses import SEED_CODEBOOK
from upcore.tariffs import SEED_LOGISTICS
from upcore.tax import SEED_RATES

from upapi.db import models as m
from upapi.db.session import make_engine

DEMO_ORG = UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER = UUID("00000000-0000-4000-8000-000000000002")
DAYS = 60
PLANS = [
    {"code": "trial", "name": "Sinov", "price_uzs": Decimal(0)},
    {"code": "basic", "name": "Asosiy", "price_uzs": Decimal(199_000)},
]


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


async def _upsert(conn: AsyncConnection, table: Table, rows: list[dict[str, Any]]) -> None:
    await conn.execute(insert(table).on_conflict_do_nothing(), rows)


async def seed_reference(conn: AsyncConnection) -> None:
    """Global ma'lumotnomalar — ``upcore`` dagi boshlang'ich qiymatlar (ADR-015)."""
    book = SEED_CODEBOOK
    await _upsert(
        conn,
        m.expense_codes,
        [{"code": c, "category": cat.value, "in_pnl": cat.in_pnl} for c, cat in book.codes.items()]
        + [
            {"code": p, "category": cat.value, "in_pnl": cat.in_pnl, "match": "prefix"}
            for p, cat in book.prefixes
        ],
    )
    await _upsert(conn, m.ref_tax_rates, [asdict(r) for r in SEED_RATES])
    await _upsert(
        conn,
        m.ref_logistics_tariffs,
        [{"valid_from": t.valid_from, "rules": _json(asdict(t))} for t in SEED_LOGISTICS],
    )
    await _upsert(conn, m.plans, PLANS)


async def seed_demo(conn: AsyncConnection, rng: random.Random, today: date) -> bool:
    """Demo tashkilot: 2 do'kon, 6 SKU, ``DAYS`` kunlik sotuv va xarajatlar. Bor bo'lsa — ``False``."""
    if (await conn.execute(select(m.orgs.c.id).where(m.orgs.c.id == DEMO_ORG))).first():
        return False
    org = {"org_id": DEMO_ORG}
    await conn.execute(m.orgs.insert(), {"id": DEMO_ORG, "name": "Demo doʼkon"})
    await conn.execute(
        m.users.insert(), {"id": DEMO_USER, "phone": "+998900000001", "name": "Demo egasi"}
    )
    await conn.execute(m.memberships.insert(), {**org, "user_id": DEMO_USER, "role": "owner"})
    plan = (await conn.execute(select(m.plans.c.id).where(m.plans.c.code == "trial"))).scalar_one()
    await conn.execute(
        m.subscriptions.insert(),
        {**org, "plan_id": plan, "status": "trial", "trial_until": today + timedelta(days=14)},
    )
    account = (
        await conn.execute(
            m.mp_accounts.insert().returning(m.mp_accounts.c.id),
            # Sintetik: shifrlangan kalit o'rnida tasodifiy baytlar.
            {**org, "token_encrypted": rng.randbytes(32), "key_version": 1, "token_last4": "demo"},
        )
    ).scalar_one()
    start = today - timedelta(days=DAYS)
    for n, shop_name in enumerate(["Demo A", "Demo B"], start=1):
        shop = (
            await conn.execute(
                m.shops.insert().returning(m.shops.c.id),
                {
                    **org,
                    "account_id": account,
                    "external_id": 900_000 + n,
                    "name": shop_name,
                    "first_sale_on": start,
                },
            )
        ).scalar_one()
        skus = []
        for k in range(3):
            price = Decimal(rng.choice([39_000, 59_000, 89_000, 129_000]))
            item = (
                await conn.execute(
                    m.items.insert().returning(m.items.c.id),
                    {
                        **org,
                        "name": f"Mahsulot {n}-{k + 1}",
                        "length_mm": 200,
                        "width_mm": 150,
                        "height_mm": 50,
                    },
                )
            ).scalar_one()
            sku = (
                await conn.execute(
                    m.mp_skus.insert().returning(m.mp_skus.c.id),
                    {
                        **org,
                        "shop_id": shop,
                        "item_id": item,
                        "external_id": n * 1000 + k,
                        "sku_code": f"D{n}-{k + 1}",
                        "price": price,
                        "commission_pct": Decimal(20),
                        "qty_active": rng.randint(5, 80),
                    },
                )
            ).scalar_one()
            skus.append((sku, price))
        sales: list[dict[str, Any]] = []
        expenses: list[dict[str, Any]] = []
        for d in range(DAYS):
            day = datetime.combine(start + timedelta(days=d), datetime.min.time(), UTC)
            for _ in range(rng.randint(0, 6)):
                sku, price = rng.choice(skus)
                amount = rng.choice([1, 1, 1, 2])
                revenue = price * amount
                commission = revenue * Decimal("0.2")
                logistics = Decimal(5250 * amount)
                sales.append(
                    {
                        **org,
                        "shop_id": shop,
                        "sku_id": sku,
                        "external_id": len(sales) + 1,
                        "order_id": 10_000 * n + len(sales),
                        "status": rng.choice(["TO_WITHDRAW"] * 8 + ["PROCESSING", "CANCELED"]),
                        "ordered_at": day + timedelta(hours=rng.randint(8, 22)),
                        "sell_price": price,
                        "amount": amount,
                        "commission": commission,
                        "logistics_fee": logistics,
                        "seller_profit": revenue - commission - logistics,
                    }
                )
            if d % 7 == 0:
                expenses += [
                    {
                        **org,
                        "shop_id": shop,
                        "external_id": len(expenses) + 1 + i,
                        "raw_code": code,
                        "code": code,
                        "category": SEED_CODEBOOK.codes[code].value,
                        "type": "OUTCOME",
                        "amount": Decimal(rng.randint(5, 60) * 1000),
                        "created_on": day,
                    }
                    for i, code in enumerate(["Y000120", "C000003"])
                ]
        await conn.execute(m.sale_items.insert(), sales)
        await conn.execute(m.mp_expenses.insert(), expenses)
    return True


async def run(url: str, seed: int = 1, today: date | None = None) -> bool:
    engine = make_engine(url)
    try:
        async with engine.begin() as conn:
            await seed_reference(conn)
            return await seed_demo(conn, random.Random(seed), today or date.today())
    finally:
        await engine.dispose()


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else os.environ.get("UP_MIGRATION_DATABASE_URL", "")
    if not url:
        print("URL bering: python -m upapi.db.seed postgresql://...", file=sys.stderr)
        return 2
    created = asyncio.run(run(url))
    print("Demo tashkilot yaratildi." if created else "Demo tashkilot allaqachon bor.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
