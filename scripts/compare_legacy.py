#!/usr/bin/env python3
"""B1.9: legacy ilova va yangi yadro (``packages/core``) natijalarini Temurning real ma'lumotida solishtirish.

Faqat standart kutubxona (Python 3.12+; Temurning Mac'ida python3 3.15) — hech narsa o'rnatish shart emas.
Ma'lumot repozitoriyga chiqmaydi: skript lokal ishlaydi va faqat yig'ma raqamlar hisobotini yozadi.

Ishga tushirish (loyiha papkasida):

    python3 scripts/compare_legacy.py --db uzum.db --history uzum_history.json
    python3 scripts/compare_legacy.py --db uzum.db --from 2026-09-01 --to 2026-10-31 --out farqlar.md

``--history`` berilsa xarajatlar xom qatorlardan (status, source bilan) yangi klassifikator orqali o'tadi;
berilmasa ``uzum.db`` dagi qayta ishlangan qatorlardan tiklanadi (izohda aytiladi).
Chiqish kodi: 0 — majburiy tekshiruvlar o'tdi, 1 — mos kelmagan joy bor (hisobotda ✗).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

if sys.version_info < (3, 12):  # noqa: UP036 - eski Python'da tushunarli xabar uchun
    sys.exit("Python 3.12 yoki yangisi kerak (Mac'da: python3 --version).")

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages" / "core" / "src"), str(ROOT)]

from upcore.costing import CostMethod, Sale, compute_costs, lots_from_purchase  # noqa: E402
from upcore.expenses import ExpenseCategory, classify_expenses  # noqa: E402
from upcore.fx import manual_rate  # noqa: E402
from upcore.metrics import Period, SaleLine, StatusGroup, status_group  # noqa: E402
from upcore.money import Money  # noqa: E402
from upcore.pnl import ExpenseItem, build_cells, expense_items  # noqa: E402
from upcore.purchasing import (  # noqa: E402
    ComponentKind,
    CostComponent,
    Purchase,
    PurchaseLine,
    compute_lots,
    residual_goods,
)

from uzum_profit import costs as legacy_costs  # noqa: E402
from uzum_profit import report as legacy_report  # noqa: E402
from uzum_profit.db import connect  # noqa: E402
from uzum_profit.util import load_env  # noqa: E402

TZ = timezone(timedelta(hours=5))
D = Decimal
TOL = D("1")  # so'm: majburiy tekshiruvlar uchun ruxsat
C = ExpenseCategory
LEGACY_KIND = {  # legacy expense_totals toifalari → yangi toifalar
    "ad": (C.ADVERTISING,),
    "storage": (C.STORAGE, C.RETURN_STORAGE),
    "fine": (C.FINE,),
    "compensation": (C.COMPENSATION,),
}


def d(x: object) -> Decimal:
    """Legacy float/int → Decimal (float ikkilik xatosisiz, matn orqali)."""
    return D(str(x if x is not None else 0))


def ms_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, TZ).date()


def fmt(x: Decimal | float | int | None) -> str:
    if x is None:
        return "—"
    q = d(x).quantize(D("1"))
    if q == 0:
        q = D(0)  # "-0" ko'rinmasin
    return f"{q:,}".replace(",", " ")


def months(start: date, end: date) -> list[Period]:
    out, cur = [], start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append(Period(max(cur, start), min(nxt - timedelta(days=1), end)))
        cur = nxt
    return out


# --- Partiyalar (F20) -----------------------------------------------------------------------


def legacy_as_purchase(batch: dict) -> Purchase:
    """Legacy partiyasi → yangi model (B4.9 ko'chirish qoidasi bilan bir xil):
    tovar — narxli qatorlar o'z narxida, qolgani narxsiz qatorlarga dona bo'yicha; kargo va qo'shimchalar —
    dona bo'yicha; kurslar — partiyadagi qo'lda kurs. Sotuvga tayyor sana: kargo sanasi; kargo kiritilgan,
    sanasi yo'q — buyurtma sanasi (legacy ``effective_date``); kargo kiritilmagan — "yo'lda"."""
    day = date.fromisoformat(batch["date"])
    cny = manual_rate(day, "CNY", d(batch.get("cny_rate") or 0) or D(1))
    usd = manual_rate(day, "USD", d(batch.get("usd_rate") or 0) or D(1))
    lines = tuple(
        PurchaseLine(
            str(i),
            int(ln["qty"]),
            int(ln["qty"]),
            None if ln["cny_unit"] is None else Money.of(d(ln["cny_unit"]), "CNY"),
        )
        for i, ln in enumerate(batch["lines"])
    )
    comps: list[CostComponent] = []
    if batch.get("cny_rate"):
        rest, unpriced = residual_goods(Money.of(d(batch.get("goods_cny")), "CNY"), lines)
        comps += [
            CostComponent(ComponentKind.GOODS, ln.unit_price * ln.qty, cny, line_ids=(ln.id,))
            for ln in lines
            if ln.unit_price is not None and ln.qty > 0
        ]
        if unpriced and not rest.is_zero():
            comps.append(CostComponent(ComponentKind.GOODS, rest, cny, line_ids=unpriced))
    if batch.get("cargo_usd") is not None and batch.get("usd_rate"):
        comps.append(
            CostComponent(ComponentKind.CARGO, Money.of(d(batch["cargo_usd"]), "USD"), usd)
        )
    comps += [
        CostComponent(ComponentKind.OTHER, Money.of(d(e["amount"]), "UZS")) for e in batch["extras"]
    ]
    cargo_day = batch.get("cargo_date")
    ready = (
        date.fromisoformat(cargo_day)
        if cargo_day
        else (day if batch.get("cargo_usd") is not None else None)
    )
    return Purchase(f"B{batch['id']}", lines, tuple(comps), order_date=day, cargo_paid_date=ready)


def compare_batches(batches: list[dict]) -> tuple[list[str], bool]:
    rows = [
        "| Partiya | Sana | Qatorlar | Legacy o'rtacha | Yangi o'rtacha | Eng katta farq/dona | |",
        "|---|---|---|---|---|---|---|",
    ]
    ok = True
    for b in batches:
        old = legacy_costs.compute_batch(b)
        if not old:
            continue
        new = compute_lots(legacy_as_purchase(b))
        worst = max(
            (
                abs(n.unit_cost.amount - d(o["unit_cost"]))
                for o, n in zip(old, new, strict=True)
                if n.unit_cost
            ),
            default=D(0),
        )
        units = sum(o["qty"] for o in old)
        old_avg = sum(d(o["qty"]) * d(o["unit_cost"]) for o in old) / units if units else None
        new_avg = sum(n.total.amount for n in new) / units if units else None
        good = worst <= D("0.01")
        ok &= good
        title = (b.get("title") or "").replace("|", "/")[:30]
        rows.append(
            f"| #{b['id']} {title} | {b['date']} | {len(old)} | {fmt(old_avg)} | {fmt(new_avg)} | "
            f"{worst.quantize(D('0.01'))} | {'✓' if good else '✗'} |"
        )
    return rows, ok


# --- Sotuvlar ---------------------------------------------------------------------------------


def sale_lines(conn, shop_id: int) -> list[tuple[int, SaleLine]]:
    out = []
    for r in conn.execute(
        "SELECT * FROM order_items WHERE shop_id=? ORDER BY created_ms, id", (shop_id,)
    ):
        out.append(
            (
                r["id"],
                SaleLine(
                    sku=(r["sku"] or "").lower(),
                    order_date=ms_date(r["created_ms"]),
                    status=r["status"] or "",
                    sell_price=d(r["sell_price"]),
                    amount=int(r["amount"] or 0),
                    commission=d(r["commission"]),
                    logistics=d(r["logistics_fee"]),
                    seller_profit=None if r["seller_profit"] is None else d(r["seller_profit"]),
                    amount_returns=int(r["amount_returns"] or 0),
                    shop=str(shop_id),
                ),
            )
        )
    return out


def with_costs(
    conn, shop_id: int, lines: list[tuple[int, SaleLine]], method: CostMethod
) -> list[SaleLine]:
    """Yangi lot dvigateli (F21) bilan har sotuvga birlik tannarx."""
    lots: dict[str, list] = defaultdict(list)
    for b in legacy_costs.load_batches(conn, shop_id):
        if not legacy_costs.compute_batch(b):  # donasiz partiya — legacy ham hisobga olmaydi
            continue
        p = legacy_as_purchase(b)
        item_of = {
            str(i): (ln["sku"] or "").lower() for i, ln in enumerate(b["lines"]) if ln.get("sku")
        }
        for sku, items in lots_from_purchase(p, compute_lots(p), item_of).items():
            lots[sku] += items
    events: dict[str, list[Sale]] = defaultdict(list)
    for rid, line in lines:
        if line.group in (StatusGroup.COMPLETED, StatusGroup.PROCESSING) and line.amount > 0:
            events[line.sku].append(Sale(str(rid), line.order_date, line.amount))
    unit: dict[str, Decimal] = {}
    for sku, evs in events.items():
        result = compute_costs(lots.get(sku, []), evs, method)
        for sid, out in result.sales.items():
            if out.cost is not None:
                unit[sid] = out.cost.amount / out.qty
    return [replace(line, unit_cost=unit.get(str(rid))) for rid, line in lines]


# --- Xarajatlar -------------------------------------------------------------------------------


def new_expenses(conn, shop_id: int, history: dict | None) -> tuple[list[ExpenseItem], str]:
    raw = None
    if history is not None:
        blk = (history.get("per_shop") or {}).get(str(shop_id)) or {}
        raw = blk.get("expenses", {}).get("rows")
    if raw is not None:
        return expense_items(
            classify_expenses(raw), str(shop_id)
        ), "xom qatorlar (uzum_history.json)"
    rows = [
        {
            "id": r["id"],
            "dateCreated": r["created_ms"],
            "code": r["code"],
            "name": r["name"],
            "type": r["type"] or "OUTCOME",
            "paymentPrice": str(r["price"]),
        }
        for r in conn.execute("SELECT * FROM expenses WHERE shop_id=?", (shop_id,))
    ]
    return expense_items(
        classify_expenses(rows), str(shop_id)
    ), "uzum.db dan tiklangan (status, source yo'q)"


# --- Hisobot ----------------------------------------------------------------------------------


def shop_section(
    conn, shop_id: int, name: str, period: Period, history: dict | None
) -> tuple[list[str], bool]:
    f, t = period.start.isoformat(), period.end.isoformat()
    lines = sale_lines(conn, shop_id)
    plain = [x for _, x in lines]
    fifo = with_costs(conn, shop_id, lines, CostMethod.FIFO)
    avg = with_costs(conn, shop_id, lines, CostMethod.AVERAGE)
    exp, exp_source = new_expenses(conn, shop_id, history)
    old = legacy_report.build_report(conn, [shop_id], f, t)
    done = old["done"]

    in_p = [x for x in plain if x.order_date in period]
    strict = [x for x in in_p if x.status == "TO_WITHDRAW"]  # legacy faqat TO_WITHDRAW ni oladi
    partial = [x for x in in_p if x.status == "PARTIALLY_CANCELLED"]
    unknown = sorted({x.status for x in in_p if status_group(x.status) is StatusGroup.UNKNOWN})

    def tot(items, attr):
        return sum((getattr(x, attr) for x in items), D(0))

    checks = [
        ("Dona", d(done["units"]), D(sum(x.amount for x in strict))),
        ("Tushum (F3)", d(done["revenue"]), tot(strict, "revenue")),
        ("Komissiya (F4)", d(done["commission"]), tot(strict, "commission")),
        ("Logistika (F5)", d(done["logistics"]), tot(strict, "logistics")),
        ("Uzum to'lovi (F6)", d(done["seller_profit"]), tot(strict, "payout")),
    ]
    ok = True
    out = [f"## {name} ({shop_id})", "", f"Davr: {f} — {t}. Xarajatlar manbai: {exp_source}.", ""]
    out += ["| Ko'rsatkich (TO_WITHDRAW) | Legacy | Yangi | Farq | |", "|---|---|---|---|---|"]
    for label, a, b in checks:
        diff = b - a
        good = abs(diff) <= TOL
        if label.startswith("Uzum to'lovi"):
            good = True  # legacy Uzum bergan sellerProfit'ni oladi, yangi — F3 − F4 − F5 (F6 tekshiruvi pastda)
        ok &= good
        out.append(f"| {label} | {fmt(a)} | {fmt(b)} | {fmt(diff)} | {'✓' if good else '✗'} |")
    mism = [
        x for x in strict if x.seller_profit is not None and abs(x.seller_profit - x.payout) > TOL
    ]
    out += [
        "",
        f"- `sellerProfit` ≠ F3 − F4 − F5 (1 so'mdan ko'p): **{len(mism)}** qator "
        f"(farq jami {fmt(sum((x.seller_profit - x.payout for x in mism), D(0)))} so'm) — F6 tekshiruvi, log uchun.",
        f"- `PARTIALLY_CANCELLED`: **{len(partial)}** qator, tushum {fmt(tot(partial, 'revenue'))} — legacy hisobga "
        "olmaydi, yangi yakunlangan sifatida oladi (F2; B2.11 da tasdiqlanadi).",
    ]
    if unknown:
        out.append(f"- Noma'lum holatlar (hech qaysi hisobga kirmaydi): {', '.join(unknown)}")

    # Oylar bo'yicha (majburiy tekshiruv)
    out += [
        "",
        "| Oy | Tushum farqi | Komissiya farqi | Logistika farqi | Dona farqi |",
        "|---|---|---|---|---|",
    ]
    for m in months(period.start, period.end):
        mo = legacy_report.build_report(conn, [shop_id], m.start.isoformat(), m.end.isoformat())[
            "done"
        ]
        ms = [x for x in strict if x.order_date in m]
        diffs = [
            tot(ms, "revenue") - d(mo["revenue"]),
            tot(ms, "commission") - d(mo["commission"]),
            tot(ms, "logistics") - d(mo["logistics"]),
            D(sum(x.amount for x in ms)) - d(mo["units"]),
        ]
        ok &= all(abs(x) <= TOL for x in diffs)
        out.append(f"| {m.start:%Y-%m} | " + " | ".join(fmt(x) for x in diffs) + " |")

    # Xarajatlar
    cells = build_cells(period, fifo, exp)
    st = cells.statement()
    ex = old["ex"]
    out += ["", "| Xarajat toifasi | Legacy | Yangi | Farq | |", "|---|---|---|---|---|"]
    for kind, cats in LEGACY_KIND.items():
        new_v = sum((st.uzum_expenses.get(c, Money.of(0, "UZS")).amount for c in cats), D(0))
        legacy_v = d(ex[kind]) * (-1 if kind == "compensation" else 1)
        same = abs(new_v - legacy_v) <= TOL
        out.append(
            f"| {kind} | {fmt(legacy_v)} | {fmt(new_v)} | {fmt(new_v - legacy_v)} | {'✓' if same else '≈'} |"
        )
    extra = {
        c: a for c, a in st.uzum_expenses.items() if not any(c in cs for cs in LEGACY_KIND.values())
    }
    for c, a in sorted(extra.items()):
        out.append(f"| {c.value} (legacy'da yo'q) | — | {fmt(a.amount)} | {fmt(a.amount)} | + |")
    out.append(
        f"| **Jami (legacy extras → F9)** | {fmt(old['extras'])} | {fmt(st.uzum_total.amount)} | "
        f"{fmt(st.uzum_total.amount - d(old['extras']))} | |"
    )
    out += [
        "",
        "≈ — sabablari: yangi klassifikator kodning hamma variantlarini taniydi (Y000119, Y000050 reklama; "
        "C000004 qaytim saqlash), CANCELED/REFUNDED va `BALANCE_CORRECTION` ni chiqaradi, dublikatlarni "
        "olib tashlaydi (B1.3). Xom qatorlarsiz (`--history` yo'q) `source` ma'lumoti yo'qoladi.",
    ]

    # Tannarx va foyda: avval legacy bilan bir xil qatorlar (TO_WITHDRAW), keyin to'liq yangi hisob.
    def only_strict(items: list[SaleLine]) -> list[SaleLine]:
        return [x for x in items if x.status != "PARTIALLY_CANCELLED"]

    av = build_cells(period, only_strict(avg), exp).statement()
    ff = build_cells(period, only_strict(fifo), exp).statement()
    cols = [av, ff, st]

    def row(label: str, legacy: str, get) -> str:
        return f"| {label} | {legacy} | " + " | ".join(get(s) for s in cols) + " |"

    out += [
        "",
        "| Tannarx va foyda | Legacy (kumulyativ o'rtacha) | Yangi: o'rtacha | Yangi: FIFO | Yangi: FIFO + PARTIALLY_CANCELLED |",
        "|---|---|---|---|---|",
        row("Sotuv tannarxi (F7)", fmt(done["cogs"]), lambda s: fmt(s.cogs.amount)),
        row(
            "Tannarxi ma'lum qatorlar",
            f"{done['k_n']} / {done['n']}",
            lambda s: f"{s.lines - s.uncovered_lines} / {s.lines}",
        ),
        row(
            "Yalpi foyda (F8)",
            fmt(old["profit_before_extras"]),
            lambda s: fmt(s.gross_profit.amount),
        ),
        row("Uzum xarajatlari (F9)", fmt(old["extras"]), lambda s: fmt(s.uzum_total.amount)),
        row("Tannarxsiz qism xarajatlari", "—", lambda s: fmt(s.uncovered_expenses.amount)),
        row("Sof foyda (F12)", fmt(old["profit"]), lambda s: fmt(s.net_profit.amount)),
        "",
        "Farq sabablari (kutilgan, xato emas): (1) tannarx usuli — legacy sanagacha kelgan hamma partiyalar "
        "o'rtachasi, yangi — FIFO (ADR-025) yoki harakatlanuvchi o'rtacha; (2) tannarxsiz qism bo'lsa xarajatlar "
        "qamrov ulushida ayriladi (F15, ADR-026), legacy hammasini ayiradi; (3) F9 ga legacy'da yo'q toifalar "
        "kiradi (yuqoridagi jadval); (4) yalpi foyda Uzum `sellerProfit` o'rniga F3 − F4 − F5; (5) oxirgi ustunda "
        "`PARTIALLY_CANCELLED` yakunlangan sifatida qo'shilgan.",
        "",
    ]
    return out, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Legacy va yangi yadro natijalarini solishtirish (B1.9)"
    )
    ap.add_argument(
        "--db",
        default=str(ROOT / "uzum.db"),
        help="legacy baza (standart: loyiha papkasidagi uzum.db)",
    )
    ap.add_argument(
        "--history", help="uzum_history.json (xarajatlarning xom qatorlari uchun, ixtiyoriy)"
    )
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD (standart: eng birinchi sotuv)")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (standart: oxirgi sotuv)")
    ap.add_argument("--out", default="legacy_farqlari.md", help="hisobot fayli (Markdown)")
    args = ap.parse_args(argv)

    if not Path(args.db).exists():
        print(f"Baza topilmadi: {args.db}", file=sys.stderr)
        return 2
    load_env()  # legacy sozlamalari (.env: bepul logistika davri va h.k.) xuddi ilovadagidek
    conn = connect(args.db)
    try:
        return _run(conn, args)
    finally:
        conn.close()


def _run(conn, args: argparse.Namespace) -> int:
    history = None
    if args.history:
        with open(args.history, encoding="utf-8") as fh:
            history = json.load(fh)

    lo, hi = conn.execute("SELECT MIN(created_ms), MAX(created_ms) FROM order_items").fetchone()
    if lo is None:
        print("Bazada sotuv yo'q.", file=sys.stderr)
        return 2
    period = Period(
        date.fromisoformat(args.date_from) if args.date_from else ms_date(lo),
        date.fromisoformat(args.date_to) if args.date_to else ms_date(hi),
    )
    shops = conn.execute("SELECT id, name FROM shops ORDER BY id").fetchall()

    report = [
        "# Legacy va yangi yadro: solishtirish (B1.9)",
        "",
        f"Yaratildi: {datetime.now(TZ):%Y-%m-%d %H:%M} · Python {sys.version.split()[0]} · davr {period.start} — {period.end}",
        "",
        "Majburiy tekshiruvlar (✓ bo'lishi shart): partiyalar birlik tannarxi (1 tiyingacha), TO_WITHDRAW bo'yicha "
        "dona, tushum, komissiya, logistika (1 so'mgacha, oylar bo'yicha ham). Qolganlari — sababi bilan farqlar.",
        "",
        "## Partiyalar (F20)",
        "",
    ]
    ok = True
    for s in shops:
        batches = legacy_costs.load_batches(conn, s["id"])
        if batches:
            rows, good = compare_batches(batches)
            ok &= good
            report += [f"**{s['name']}**", "", *rows, ""]
    for s in shops:
        section, good = shop_section(conn, s["id"], s["name"] or str(s["id"]), period, history)
        ok &= good
        report += section
    report += [
        "## Xulosa",
        "",
        "✓ Majburiy tekshiruvlar o'tdi."
        if ok
        else "✗ Mos kelmagan joy bor — jadvaldagi ✗ qatorlarni ko'ring.",
        "",
    ]

    text = "\n".join(report)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nHisobot saqlandi: {args.out}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
