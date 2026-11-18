"""TM9.4 F52 va lot daftari (haqiqiy PostgreSQL, ADR-068 (4)): "Uzum yo'qotdi" kamomadi "Zarar deb yopildi" /
"Kompensatsiya qilindi" bo'lganda yo'qolgan dona partiyadan ham chiqadi (F51 dagi kabi) — keyingi sotuvlar tannarxi
bir partiyaga siljimaydi; "Topildi" yoki qayta ochilsa — qaytadi. Zarar foyda hisobida F52 qatori — bir marta."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import test_purchases as tp
from test_purchases import ok, send
from test_reports import World
from upapi import calc
from upapi.reports.common import today

db = tp.db
world = tp.world


def counted(w: World, sku: str, qty: int, price: int, day: str) -> None:
    ok(
        send(
            w,
            "POST",
            "purchases/quick",
            lines=[{"sku_id": sku, "qty": qty}],
            paid_amount=str(qty * price),
            currency="UZS",
            ordered_on=day,
            on_hand=True,
        ),
        201,
    )


def cogs(w: World, sale_id: object) -> Decimal:
    rows = w.a.sql("SELECT cogs FROM sale_costs WHERE sale_item_id = %s", [sale_id])
    return Decimal(rows[0][0])


def test_lost_units_leave_lots_once(world: World) -> None:
    w, a = world, world.a
    item, sku_id = a.item("Lot-Kamomad")
    sku = str(sku_id)
    a.sql("UPDATE mp_skus SET barcode = '4780000999001' WHERE id = %s", [sku_id])
    counted(w, sku, 10, 10_000, "2026-09-01")  # eski partiya — 10 000
    counted(w, sku, 10, 20_000, "2026-09-10")  # yangi partiya — 20 000
    a.recalc(datetime.now(UTC))
    out = ok(
        send(w, "POST", "dispatches", shop_id=str(a.shop_id), items=[{"sku_id": sku, "qty": 10}]),
        201,
    )
    inv = a.insert(
        "fbo_invoices",
        shop_id=a.shop_id,
        external_id=990_001,
        number=990_001,
        status="CREATED",
        created_on=datetime.now(UTC),
    )
    a.insert(
        "fbo_invoice_items",
        invoice_id=inv,
        sku_external_id=990_001,
        sku_id=sku_id,
        quantity_to_stock=10,
        quantity_accepted=0,
    )
    ok(send(w, "POST", f"dispatches/{out['id']}/link", invoice_id=str(inv)))
    a.sql(
        "UPDATE fbo_invoices SET status = 'ACCEPTED', created_on = now() - interval '9 days' "
        "WHERE id = %s",
        [inv],
    )
    a.sql("UPDATE fbo_invoice_items SET quantity_accepted = 8 WHERE invoice_id = %s", [inv])
    res = ok(send(w, "POST", "receiving/resolve", dispatch_id=out["id"], sku_id=sku, action="lost"))
    shortage = next(x for x in res["shortages"] if x["dispatch_id"] == out["id"])
    # Kamomad ochiq — sotuv (10 dona) eski partiyadan to'liq: 10 × 10 000.
    # Sotuv kamomad yopilgan kundan keyin (bir kunda hodisalar tartibi — sotuv avval).
    # Toshkent sanasi: endpoint `today()` bilan bir xil (UTC 19:00 dan keyin `date.today()` bir kun orqada qoladi).
    sale = a.sale(sku_id, today() + timedelta(days=1), amount=10)
    a.request(calc.Scope.ITEM, item)  # sotuv to'g'ridan-to'g'ri bazaga yozildi (sinxron o'rniga)
    a.recalc(datetime.now(UTC))
    assert cogs(w, sale) == Decimal("100000.00")
    # Zarar deb yopildi — 2 dona eski partiyadan chiqdi: 8 × 10 000 + 2 × 20 000.
    ok(send(w, "PATCH", f"receiving/shortages/{shortage['id']}", status="written_off"))
    assert (
        a.sql(
            "SELECT count(*) FROM recalc_queue WHERE org_id = %s AND ref_id = %s", [a.org_id, item]
        )[0][0]
        >= 1
    )
    a.recalc(datetime.now(UTC))
    assert cogs(w, sale) == Decimal("120000.00")
    # F52 — partiyadan chiqqan qiymatdan (2 × 10 000, FIFO), jo'natmadagi o'rtacha narxdan (15 000) emas: bir marta.
    loss = next(
        x for x in ok(send(w, "GET", "receiving"))["shortages"] if x["id"] == shortage["id"]
    )
    assert Decimal(loss["loss"]) == Decimal("20000.00")
    # "Topildi" — donalar qaytadi.
    ok(send(w, "PATCH", f"receiving/shortages/{shortage['id']}", status="found"))
    a.recalc(datetime.now(UTC))
    assert cogs(w, sale) == Decimal("100000.00")
