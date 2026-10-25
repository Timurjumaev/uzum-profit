"""Uzum ma'lumotini bazaga yozish (03 §6 "Upsert qoidalari", 02 M3 qabul mezonlari).

- **Tabiiy kalit** bo'yicha upsert (``org_id`` bilan boshlanadi): bir xil ma'lumotni qayta olish dublikat yaratmaydi.
- Bir partiyada kalit takrorlansa yozishdan oldin birlashtiriladi (oxirgisi qoladi) — PostgreSQL bitta
  ``INSERT ... ON CONFLICT`` da bir qatorni ikki marta yangilay olmaydi.
- **Faqat Uzum bergan ustunlar** yangilanadi va ``NULL`` bilan ustidan yozilmaydi (``COALESCE``); hosila ustunlar
  (masalan, xarajat toifasi — lug'atdan) va ``raw`` har safar yangidan.
- Qiymati o'zgarmagan qator qayta yozilmaydi (``WHERE ... IS DISTINCT FROM``) — ``written`` haqiqiy o'zgarishlar soni.
- **Sotuvchi kiritgani muqaddas** (tamoyil 7): sinxron ``items``, ``mp_skus.item_id``, do'kon taxallusi/rangi/faolligi
  kabi ustunlarga tegmaydi va hech narsani o'chirmaydi (faqat Uzum'dan kelgan postavka/qaytarish tarkibi almashadi).

Hamma funksiyalar tashkilot tranzaksiyasida (``org_transaction``, RLS) chaqiriladi; qatorlarda ``org_id`` bor.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Table, delete, func, insert, literal, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from upapi.db import models as m

_SKIP = frozenset({"id", "org_id", "created_at", "updated_at"})
_MAX_PARAMS = 30_000  # asyncpg: bitta so'rovda ko'pi bilan 32 767 parametr


@dataclass
class Upserted:
    """``written`` — yangi yoki o'zgargan qatorlar; ``ids`` — ularning kaliti → id."""

    written: int = 0
    ids: dict[tuple[Any, ...], UUID] = field(default_factory=dict)


def dedupe(rows: Iterable[dict[str, Any]], key: Sequence[str]) -> list[dict[str, Any]]:
    """Kalit bo'yicha takrorsiz (oxirgi qiymat qoladi, tartib — birinchi uchragan joyi)."""
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        by_key[tuple(row[k] for k in key)] = row
    return list(by_key.values())


async def upsert(
    conn: AsyncConnection,
    table: Table,
    rows: Iterable[dict[str, Any]],
    key: Sequence[str],
    *,
    exact: frozenset[str] = frozenset(),
) -> Upserted:
    """``rows`` (hammasida bir xil ustunlar) → ``table``. ``key`` — unikal cheklov ustunlari; ``exact`` — ``NULL``
    bo'lsa ham ustidan yoziladigan (hosila) ustunlar; ``raw`` doim yangilanadi."""
    unique = dedupe(rows, key)
    result = Upserted()
    if not unique:
        return result
    columns = [c for c in unique[0] if c not in key and c not in _SKIP]
    chunk = max(1, _MAX_PARAMS // max(1, len(unique[0])))
    for start in range(0, len(unique), chunk):
        stmt = pg_insert(table).values(unique[start : start + chunk])
        new = {
            c: stmt.excluded[c]
            if c in exact or c == "raw"
            else func.coalesce(stmt.excluded[c], table.c[c])
            for c in columns
        }
        if columns:
            stmt = stmt.on_conflict_do_update(
                index_elements=list(key),
                set_={**new, "updated_at": func.now()},
                where=tuple_(*(table.c[c] for c in columns)).is_distinct_from(
                    tuple_(*new.values())
                ),
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(key))
        returned = await conn.execute(stmt.returning(table.c.id, *(table.c[k] for k in key)))
        for row in returned:
            result.ids[tuple(row[1:])] = row[0]
            result.written += 1
    return result


async def ids_by_external(
    conn: AsyncConnection, table: Table, shop_id: UUID, external_ids: Iterable[int]
) -> dict[int, UUID]:
    """Do'kon ichida tashqi id → bizning id (``mp_skus``, ``fbo_invoices``, ``mp_returns`` ...)."""
    wanted = sorted(set(external_ids))
    if not wanted:
        return {}
    rows = await conn.execute(
        select(table.c.external_id, table.c.id).where(
            table.c.shop_id == shop_id, table.c.external_id.in_(wanted)
        )
    )
    return {r.external_id: r.id for r in rows}


async def replace_children(
    conn: AsyncConnection,
    table: Table,
    parent_column: str,
    parent_id: UUID,
    rows: list[dict[str, Any]],
) -> int:
    """Uzum'dan kelgan tarkib (postavka, qaytarish) — eskisi o'chib yangisi yoziladi (sotuvchi ma'lumoti emas)."""
    await conn.execute(delete(table).where(table.c[parent_column] == parent_id))
    if rows:
        await conn.execute(insert(table), rows)
    return len(rows)


async def upsert_shops(
    conn: AsyncConnection, org_id: UUID, account_id: UUID, shops: Iterable[Any]
) -> int:
    """Uzum bergan do'konlar (``external_id``, ``name``): yangisi faol holda qo'shiladi (M2: hammasi belgilangan),
    borining nomi yangilanadi. Sotuvchi kiritgani (taxallus, rang, faollik) o'zgarmaydi; Uzum ro'yxatidan yo'qolgan
    do'kon o'chirilmaydi."""
    rows = [
        {"org_id": org_id, "account_id": account_id, "external_id": s.external_id, "name": s.name}
        for s in shops
    ]
    return (await upsert(conn, m.shops, rows, ("org_id", "account_id", "external_id"))).written


# --- Bog'lanishlar -------------------------------------------------------------------------------


async def link_sales(conn: AsyncConnection, shop_id: UUID) -> tuple[int, datetime | None]:
    """Sotuv qatori → SKU: ``skuTitle`` = ``skuFullTitle`` (legacy kabi), faqat do'kon ichida bir ma'noli kod.
    Bog'langan qator qayta bog'lanmaydi. Qaytadi: bog'langanlar soni va eng erta buyurtma vaqti (qayta hisob uchun)."""
    row = (
        await conn.execute(
            text(
                "WITH linked AS (UPDATE sale_items s SET sku_id = k.id, updated_at = now() FROM mp_skus k "
                "WHERE s.shop_id = :shop AND s.sku_id IS NULL AND k.shop_id = s.shop_id "
                "AND k.sku_code = s.sku_title AND NOT EXISTS (SELECT 1 FROM mp_skus d "
                "WHERE d.shop_id = k.shop_id AND d.sku_code = k.sku_code AND d.id <> k.id) "
                "RETURNING s.ordered_at) SELECT count(*), min(ordered_at) FROM linked"
            ),
            {"shop": shop_id},
        )
    ).one()
    return int(row[0]), row[1]


async def link_expenses(conn: AsyncConnection, shop_id: UUID) -> int:
    """Logistika xarajati → sotuv qatori (``externalId`` = buyurtma qatori id'si, F9 bog'lanishi)."""
    result = await conn.execute(
        text(
            "UPDATE mp_expenses e SET sale_item_id = s.id, updated_at = now() FROM sale_items s "
            "WHERE e.shop_id = :shop AND e.sale_item_id IS NULL AND e.item_external_id IS NOT NULL "
            "AND e.category IN ('logistics', 'logistics_refund') "
            "AND s.shop_id = e.shop_id AND s.external_id = e.item_external_id "
            "AND NOT EXISTS (SELECT 1 FROM sale_items d WHERE d.shop_id = s.shop_id "
            "AND d.external_id = s.external_id AND d.id <> s.id)"
        ),
        {"shop": shop_id},
    )
    return result.rowcount


async def link_children_skus(conn: AsyncConnection, shop_id: UUID) -> int:
    """Postavka va qaytarish tarkibidagi SKU (SKU keyinroq kelgan bo'lsa)."""
    total = 0
    for table, parent, parent_table in (
        ("fbo_invoice_items", "invoice_id", "fbo_invoices"),
        ("mp_return_items", "return_id", "mp_returns"),
    ):
        result = await conn.execute(
            text(
                f"UPDATE {table} c SET sku_id = k.id, updated_at = now() FROM {parent_table} p, mp_skus k "
                f"WHERE c.{parent} = p.id AND p.shop_id = :shop AND c.sku_id IS NULL "
                "AND k.shop_id = p.shop_id AND k.external_id = c.sku_external_id"
            ),
            {"shop": shop_id},
        )
        total += result.rowcount
    return total


async def first_sale_on(conn: AsyncConnection, shop_id: UUID) -> date | None:
    """Do'konning birinchi sotuvi (Toshkent sanasi)."""
    value = await conn.scalar(
        select(func.min(func.timezone("Asia/Tashkent", m.sale_items.c.ordered_at))).where(
            m.sale_items.c.shop_id == shop_id
        )
    )
    return value.date() if value is not None else None


async def snapshot(conn: AsyncConnection, org_id: UUID, shop_id: UUID, day: date) -> int:
    """Kunlik qoldiq snapshot (02 M3): do'kon SKU'larining joriy qoldig'i, narxi, komissiyasi → ``sku_daily``.
    Shu kun uchun qayta ishlasa — yangilanadi."""
    sku = m.mp_skus
    columns = ["qty_active", "qty_fbs", "qty_defected", "qty_pending", "price", "commission_pct"]
    source = select(
        literal(org_id).label("org_id"),
        sku.c.id.label("sku_id"),
        literal(day).label("day"),
        *(sku.c[c] for c in columns),
    ).where(sku.c.shop_id == shop_id)
    stmt = pg_insert(m.sku_daily).from_select(["org_id", "sku_id", "day", *columns], source)
    stmt = stmt.on_conflict_do_update(
        index_elements=["org_id", "sku_id", "day"],
        set_={**{c: stmt.excluded[c] for c in columns}, "updated_at": func.now()},
    )
    return (await conn.execute(stmt)).rowcount
