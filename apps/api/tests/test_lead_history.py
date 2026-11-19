"""F25 tarixi (B5.1, haqiqiy PostgreSQL): har bo'lak ("transit", "handover") uchun tovar → yetkazib beruvchi → tashkilot →
standart tartibi, manba va namuna soni; topshirish muddati — jo'natma Excel'i → postavka savdoga chiqqan kun (ADR-056)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import test_purchases as tp
from psycopg.types.json import Jsonb
from test_reports import World
from upapi.reports.purchases import LeadHistory, lead_history

db = tp.db
world = tp.world

D = Decimal


def history(w: World) -> LeadHistory:
    return w.a.run(lambda conn: lead_history(conn))  # type: ignore[no-any-return]


def purchase_for(w: World, item: Any, supplier: Any, **dates: date | None) -> Any:
    a = w.a
    received = dates.pop("received_on", None)
    p = a.purchase(received, supplier_id=supplier, **dates)
    a.line(p, item, 10)
    return p


def test_lead_tiers_item_supplier_org_default_and_dispatch(world: World) -> None:
    w, a = world, world.a
    item, item2 = w.ids["item"], w.ids["item2"]
    supplier = a.insert("suppliers", name="Yiwu Toys")
    # Tovar 1: yo'l 20 kun (1.10 → 21.10), topshirish 2 kun (qabul 21.10 → yuborildi 23.10); yetkazib beruvchi bilan.
    purchase_for(
        w,
        item,
        supplier,
        ordered_on=date(2026, 10, 1),
        received_on=date(2026, 10, 21),
        sent_to_uzum_on=date(2026, 10, 23),
    )
    # Tovar 2: faqat buyurtma (yo'lda) — o'z tarixi yo'q, lekin shu yetkazib beruvchining xaridi.
    purchase_for(w, item2, supplier, ordered_on=date(2026, 10, 5))
    h = history(w)
    assert h.item[item] == {"transit": [20], "handover": [2]}
    assert item2 not in h.item  # tarix yo'q
    assert h.supplier[supplier] == {"transit": [20], "handover": [2]}
    assert h.org["transit"] == [20] and h.org["handover"] == [2]
    assert h.item_supplier[item] == supplier and h.item_supplier[item2] == supplier

    # 1) tovarning o'z tarixi: manba "item".
    own = h.learn(item, {"transit": 99, "handover": 99})
    assert own.stages == {"transit": D(20), "handover": D(2)}
    assert own.sources == {"transit": "item", "handover": "item"} and own.samples == {
        "transit": 1,
        "handover": 1,
    }
    # 2) tovarda tarix yo'q, yetkazib beruvchi bor: manba "supplier".
    sup = h.learn(item2, {})
    assert sup.sources == {"transit": "supplier", "handover": "supplier"}
    # 3) tovar ham, yetkazib beruvchi ham yo'q: tashkilot medianasi.
    org = h.learn(None, {})
    assert org.sources == {"transit": "org", "handover": "org"} and org.stages["transit"] == D(20)
    # 4) tarix yo'q (bo'sh) — Sozlamalardagi standart; standart ham yo'q bo'lak — noma'lum.
    empty = LeadHistory().learn(item, {"transit": 30})
    assert empty.stages == {"transit": D(30)} and empty.sources == {"transit": "default"}

    # Jo'natma → postavka savdoga chiqqan kun (``dateAccepted``): Excel 10.11 chiqarilgan, 16.11 savdoga chiqqan — 6 kun.
    sku = w.ids["sku"]
    invoice = a.insert(
        "fbo_invoices",
        shop_id=a.shop_id,
        external_id=880_001,
        status="ACCEPTED",
        created_on=datetime(2026, 11, 12, 9, 0, tzinfo=UTC),
        raw=Jsonb(
            {"dateAccepted": int(datetime(2026, 11, 16, 8, 0, tzinfo=UTC).timestamp() * 1000)}
        ),
    )
    dispatch = a.insert(
        "fbo_dispatches",
        shop_id=a.shop_id,
        status="linked",
        exported_at=datetime(2026, 11, 10, 8, 0, tzinfo=UTC),
        invoice_id=invoice,
    )
    a.insert("fbo_dispatch_items", dispatch_id=dispatch, sku_id=sku, qty=5)
    after = history(w)
    assert after.item[item]["handover"] == [
        2,
        6,
    ]  # eski xarid (2) + jo'natma (6) — eng eskisidan yangisiga
    assert after.org["handover"] == [2, 6]
    assert after.learn(item, {}).stages["handover"] == D(4)  # median(2, 6)


def test_late_cargo_only_in_transit_past_expected_plus_grace(world: World) -> None:
    """B5.1: "Yo'lda" xarid kutilgan keldi sanasi (buyurtma + F25 "yo'l") + imtiyoz kunidan o'tsa kechikkan; "Keldi"
    belgilangan, yangi (muddat ichida) va muddati noma'lum xarid — kechikmagan."""
    from upapi.reports.purchases import late_cargo, org_lead

    w, a = world, world.a
    item = w.ids["item"]
    old = purchase_for(w, item, None, ordered_on=date(2026, 9, 1), title="Kechikkan partiya")
    purchase_for(w, item, None, ordered_on=date(2026, 11, 28), title="Yangi partiya")
    arrived = a.purchase(
        None, ordered_on=date(2026, 9, 2), arrived_on=date(2026, 10, 1), arrival_marked=True
    )
    a.line(arrived, item, 5)
    today = date(2026, 11, 30)
    lead = w.a.run(lambda conn: org_lead(conn))[
        "transit"
    ]  # tashkilot medianasi (umumiy bazadagi hamma xarid)
    found = {x.id: x for x in w.a.run(lambda conn: late_cargo(conn, today, 5))}
    expected = date(2026, 9, 1).toordinal() + math.ceil(lead)
    assert old in found and arrived not in found
    assert found[old].expected.toordinal() == expected
    assert found[old].days_late == today.toordinal() - expected
    assert not [x for x in found.values() if x.title == "Yangi partiya"]
    # Imtiyoz kunlari uzun — hech kim kechikmagan.
    assert w.a.run(lambda conn: late_cargo(conn, today, 365)) == []
