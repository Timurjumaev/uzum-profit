"""F26/F27 tovar darajasida (B5.2, haqiqiy PostgreSQL): bir tovar bir necha SKU'da bo'lsa talab va qoldiq — yig'indi, Xitoy /
yo'l / o'z ombor — bir marta (09 §12 B11); tavsiya miqdor SKU'larga talabiga mutanosib bo'linadi."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import test_purchases as tp
from test_reports import World
from upapi import calc
from upapi.reports.stock import load_stock

db = tp.db
world = tp.world

D = Decimal
AS_OF = date(2026, 10, 20)
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def test_two_skus_share_one_plan(world: World) -> None:
    w, a = world, world.a
    item, sku_a = w.ids["item"], w.ids["sku"]
    sku_b = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=9_101,
        sku_code="Mashina koʻk",
        item_id=item,
        qty_active=0,
    )
    a.sql("UPDATE mp_skus SET qty_active = 20 WHERE id = %s", [sku_a])
    a.sql("UPDATE mp_skus SET qty_active = 10 WHERE id = %s", [sku_b])
    a.sql(  # F25: standart muddat (tarix yo'q) — yo'l 20 kun + topshirish 2 kun
        "UPDATE orgs SET settings = jsonb_set(coalesce(settings, '{}'::jsonb), '{lead_days}', "
        '\'{"transit": 20, "handover": 2}\') WHERE id = %s',
        [w.org_id],
    )
    for i in range(14):  # 14 kun: A — kuniga 2, B — kuniga 1; Uzumda doim bor
        day = AS_OF - timedelta(days=13 - i)
        a.sale(sku_a, day, 2)
        a.sale(sku_b, day, 1)
        a.insert("sku_daily", sku_id=sku_a, day=day, qty_active=20, qty_fbs=0)
        a.insert("sku_daily", sku_id=sku_b, day=day, qty_active=10, qty_fbs=0)
    p = a.purchase(None, ordered_on=AS_OF - timedelta(days=3))  # buyurtma qilingan, yo'lda: 40 dona
    a.line(p, item, 40, received=None)
    a.component(p, "goods", 40 * 100_000)
    a.request(calc.Scope.PURCHASE)
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)

    book = w.a.run(lambda conn: load_stock(conn, None, AS_OF))
    xa, xb = book.skus[sku_a], book.skus[sku_b]
    assert xa.road == xb.road == 40  # yo'ldagi dona tovar bo'yicha (SKU'ga ajratilmaydi)
    speed = xa.velocity.value + xb.velocity.value
    assert xa.velocity.value > xb.velocity.value > 0
    # Tovar rejasi: F25 22 kun + A qamrov (60) → talab × 82 − (qoldiq 30 + yo'lda 40) — yo'ldagi bir marta.
    need = speed * 82 - (30 + 40)
    total = xa.reorder.qty + xb.reorder.qty
    assert abs(total - need) <= 1 and total > 0
    assert xa.reorder.qty > xb.reorder.qty  # talabga mutanosib (2 : 1)
    # Holat va buyurtma sanasi — tovarning umumiy zaxirasi bo'yicha (ikkala SKU bir xil).
    assert xa.days_of_stock_all == xb.days_of_stock_all
    assert xa.status == xb.status and xa.order_by == xb.order_by
    a.sql("UPDATE orgs SET settings = settings - 'lead_days' WHERE id = %s", [w.org_id])


def test_batch_rounds_item_plan_up(world: World) -> None:
    w, a = world, world.a
    item = a.insert("items", name="Partiyali tovar")
    sku = a.insert(
        "mp_skus",
        shop_id=a.shop_id,
        external_id=9_202,
        sku_code="Partiya",
        item_id=item,
        qty_active=5,
    )
    a.sql(
        "UPDATE orgs SET settings = jsonb_set(coalesce(settings, '{}'::jsonb), '{lead_days}', "
        '\'{"transit": 20, "handover": 2}\') WHERE id = %s',
        [w.org_id],
    )
    for i in range(14):
        day = AS_OF - timedelta(days=13 - i)
        a.sale(sku, day, 3)
        a.insert("sku_daily", sku_id=sku, day=day, qty_active=5, qty_fbs=0)
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)
    plain = w.a.run(lambda conn: load_stock(conn, None, AS_OF)).skus[sku]
    assert plain.reorder is not None and plain.reorder.qty > 0 and plain.order_batch is None
    a.sql("UPDATE items SET order_batch = 50 WHERE id = %s", [item])
    rounded = w.a.run(lambda conn: load_stock(conn, None, AS_OF)).skus[sku]
    assert rounded.order_batch == 50 and rounded.reorder is not None
    assert rounded.reorder.qty % 50 == 0 and 0 <= rounded.reorder.qty - plain.reorder.qty < 50
    a.sql("UPDATE items SET order_batch = NULL WHERE id = %s", [item])
    a.sql("UPDATE orgs SET settings = settings - 'lead_days' WHERE id = %s", [w.org_id])


def test_ship_plan_follows_target_cover_and_shares_own(world: World) -> None:
    w, a = world, world.a
    item = a.insert("items", name="Yuboriladigan")
    sku1 = a.insert(
        "mp_skus", shop_id=a.shop_id, external_id=9_301, sku_code="Y1", item_id=item, qty_active=10
    )
    sku2 = a.insert(
        "mp_skus", shop_id=a.shop_id, external_id=9_302, sku_code="Y2", item_id=item, qty_active=10
    )
    cfg = '{"transit": 20, "handover": 2}'
    a.sql(
        "UPDATE orgs SET settings = jsonb_set(coalesce(settings, '{}'::jsonb), '{lead_days}', "
        f"'{cfg}'::jsonb) WHERE id = %s",
        [w.org_id],
    )
    for i in range(14):
        day = AS_OF - timedelta(days=13 - i)
        a.sale(sku1, day, 2)
        a.sale(sku2, day, 2)
        a.insert("sku_daily", sku_id=sku1, day=day, qty_active=10, qty_fbs=0)
        a.insert("sku_daily", sku_id=sku2, day=day, qty_active=10, qty_fbs=0)
    p = a.insert(
        "purchases", ordered_on=AS_OF - timedelta(days=40), received_on=AS_OF - timedelta(days=2)
    )
    a.line(p, item, 30, received=30)  # omborimda 30 dona (qabul qilingan)
    a.component(p, "goods", 30 * 100_000)
    a.request(calc.Scope.PURCHASE)
    a.request(calc.Scope.SHOP, a.shop_id)
    a.recalc(NOW)
    # Maqsad qamrov sozlanmagan — reja yo'q (standart o'ylab topilmaydi).
    book = w.a.run(lambda conn: load_stock(conn, None, AS_OF))
    assert book.skus[sku1].ship_plan is None and book.skus[sku2].ship_plan is None
    a.sql(
        "UPDATE orgs SET settings = jsonb_set(settings, '{ship_cover_days}', "
        '\'{"A": 30, "B": 30, "C": 30}\'::jsonb) WHERE id = %s',
        [w.org_id],
    )
    book = w.a.run(lambda conn: load_stock(conn, None, AS_OF))
    p1, p2 = book.skus[sku1].ship_plan, book.skus[sku2].ship_plan
    assert p1 is not None and p2 is not None
    # Har SKU: tezlik 2 × (2 + 30) − 10 = 54 kerak; omborim 30 — SKU'lar orasida bir marta (15 + 15).
    assert (p1.need, p2.need) == (54, 54)
    assert p1.qty + p2.qty == 30 and p1.qty == p2.qty == 15
    a.sql(
        "UPDATE orgs SET settings = (settings - 'ship_cover_days') - 'lead_days' WHERE id = %s",
        [w.org_id],
    )
