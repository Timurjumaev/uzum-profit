#!/usr/bin/env python3
"""B2.11: staging (yangi tizim, real Uzum sinxroni) va legacy ``uzum.db`` raqamlarini solishtirish.

Faqat standart kutubxona (Python 3.12+; Temurning Mac'ida python3 3.15). Staging tomoni — serverdagi
``python -m upapi.realcheck`` chiqargan JSON (``infra/staging/realcheck.sh``), legacy tomoni — ``uzum.db``.

Ishga tushirish (loyiha papkasida, legacy ``sync`` dan keyin — ikki tomon bir vaqtdagi holatni ko'rsin):

    python3 -m uzum_profit sync
    python3 scripts/compare_staging.py --staging ~/realcheck.json --db uzum.db

Majburiy (B2 chiqish mezoni): har do'kon va oy bo'yicha TO_WITHDRAW dona, tushum, komissiya, logistika 1 so'mgacha
bir xil; do'kon tarixi to'liq; 24 soatda xato ish yo'q. Qolgani — B2.6/B2.8 taxminlari tekshiruvi
(``skuForInvoiceDtoList[].id``, faktura ``dateCreated``, ``/v1/return``, logistika ``externalId``, ``amount`` va
``amountReturns`` semantikasi). Chiqish kodi: 0 — hammasi ✓, 1 — ✗ bor, 2 — fayl yo'q.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

if sys.version_info < (3, 12):  # noqa: UP036 - eski Python'da tushunarli xabar uchun
    sys.exit("Python 3.12 yoki yangisi kerak (Mac'da: python3 --version).")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uzum_profit import report as legacy_report  # noqa: E402
from uzum_profit.db import connect  # noqa: E402
from uzum_profit.util import load_env  # noqa: E402

TZ = timezone(timedelta(hours=5))
D = Decimal
TOL = D("1")  # so'm
STATUS = "TO_WITHDRAW"  # legacy "yakunlangan" — faqat shu holat (docs/legacy-farqlari.md)
EXAMPLES = 10
FIELDS = ("units", "revenue", "commission", "logistics")
LABELS = {"units": "Dona", "revenue": "Tushum", "commission": "Komissiya", "logistics": "Logistika"}


def d(x: object) -> Decimal:
    return D(str(x if x is not None else 0))


def fmt(x: Decimal | int | None) -> str:
    if x is None:
        return "—"
    q = d(x).quantize(D("1")) + 0
    return f"{q:,}".replace(",", " ")


def mark(ok: bool | None) -> str:
    return {True: "✓", False: "✗", None: "≈"}[ok]


def months(start: date, end: date) -> list[tuple[date, date]]:
    out, cur = [], start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(cur, start), min(nxt - timedelta(days=1), end)))
        cur = nxt
    return out


# --- Qatorlar -------------------------------------------------------------------------------------


class Line:
    """Sotuv qatori (ikkala tomonda bir xil ko'rinish): Toshkent sanasi, holat, dona va pul maydonlari."""

    __slots__ = ("amount", "commission", "day", "id", "logistics", "price", "status")

    def __init__(self, ident, day, status, amount, price, commission, logistics) -> None:
        self.id = int(ident)
        self.day = day
        self.status = status or ""
        self.amount = int(amount or 0)
        self.price = d(price)
        self.commission = d(commission)
        self.logistics = d(logistics)

    def values(self) -> dict[str, Decimal]:
        return {
            "units": D(self.amount),
            "revenue": self.price * self.amount,
            "commission": self.commission,
            "logistics": self.logistics,
        }


def staging_lines(shop: dict[str, Any]) -> dict[int, Line]:
    # realcheck: [id, buyurtma, holat, sana, dona, narx, komissiya, logistika, sellerProfit, qaytgan]
    return {
        int(r[0]): Line(r[0], date.fromisoformat(r[3]), r[2], r[4], r[5], r[6], r[7])
        for r in shop["sales"]["lines"]
    }


def legacy_lines(conn, shop_id: int) -> dict[int, Line]:
    out = {}
    for r in conn.execute(
        "SELECT id, created_ms, status, amount, sell_price, commission, logistics_fee "
        "FROM order_items WHERE shop_id=?",
        (shop_id,),
    ):
        day = datetime.fromtimestamp(r["created_ms"] / 1000, TZ).date()
        out[r["id"]] = Line(
            r["id"],
            day,
            r["status"],
            r["amount"],
            r["sell_price"],
            r["commission"],
            r["logistics_fee"],
        )
    return out


def totals(lines: Any, start: date, end: date) -> dict[str, Decimal]:
    out = dict.fromkeys(FIELDS, D(0))
    for line in lines:
        if line.status == STATUS and start <= line.day <= end:
            for k, v in line.values().items():
                out[k] += v
    return out


def line_diff(old: dict[int, Line], new: dict[int, Line], start: date, end: date) -> list[str]:
    """Qator darajasida farq: faqat bir tomonda, holat boshqa, sana yoki summa boshqa (davrdagi qatorlar)."""
    groups: dict[str, list[str]] = {}

    def add(kind: str, text: str) -> None:
        groups.setdefault(kind, []).append(text)

    for ident in sorted(old.keys() | new.keys()):
        a, b = old.get(ident), new.get(ident)
        if not any(x and start <= x.day <= end for x in (a, b)):
            continue
        if a is None and b is not None:
            add("faqat staging'da", f"{ident} {b.day} {b.status}")
        elif b is None and a is not None:
            add("faqat legacy'da", f"{ident} {a.day} {a.status}")
        elif a is not None and b is not None:
            if a.status != b.status:
                add("holat boshqa (legacy → staging)", f"{ident} {a.status} → {b.status}")
            if a.day != b.day:
                add("sana boshqa", f"{ident} {a.day} → {b.day}")
            changed = [k for k, v in a.values().items() if v != b.values()[k]]
            if changed:
                add("summa/dona boshqa", f"{ident} ({', '.join(LABELS[k] for k in changed)})")
    if not groups:
        return ["Davrdagi hamma qatorlar ikkala tomonda bir xil (id, holat, sana, dona, summalar)."]
    out = ["| Qator farqi | Soni | Misollar |", "|---|---|---|"]
    for kind, items in groups.items():
        out.append(f"| {kind} | {len(items)} | {'; '.join(items[:EXAMPLES])} |")
    return out


# --- Taxminlar -----------------------------------------------------------------------------------


def assumptions(shop: dict[str, Any]) -> tuple[list[str], bool]:
    """Realcheck tekshiruvlari → hukm: ✓ taxmin to'g'ri, ✗ noto'g'ri (kodni o'zgartirish kerak), ≈ ma'lumot yetarli
    emas yoki qo'lda ko'rish kerak."""
    c = shop["checks"]
    inv, ret, lg, ex = c["invoices"], c["returns"], c["logistics"], c["expenses"]
    rows: list[tuple[str, str, bool | None]] = []

    if inv["items"] == 0:
        rows.append(("Postavka tarkibi: `skuForInvoiceDtoList[].id` = SKU id", "tarkib yo'q", None))
    else:
        verdict = (
            True
            if inv["items_linked"] == inv["items"]
            else (False if inv["unlinked_match_product"] else None)
        )
        rows.append(
            (
                "Postavka tarkibi: `skuForInvoiceDtoList[].id` = SKU id",
                f"{inv['items_linked']}/{inv['items']} SKU'ga bog'landi; bog'lanmagan id: {inv['unlinked_ids']}, "
                f"shundan mahsulot id'siga mos: {inv['unlinked_match_product']}",
                verdict,
            )
        )
    patterns = ", ".join(f"`{k}` × {v}" for k, v in inv["date_patterns"].items()) or "—"
    rows.append(
        (
            "Faktura `dateCreated` formati",
            f"{inv['date_parsed']}/{inv['invoices']} o'qildi; ko'rinishlar: {patterns}",
            inv["date_parsed"] == inv["invoices"] if inv["invoices"] else None,
        )
    )
    run = ret.get("last_run") or {}

    def val(x: object) -> str:
        return "—" if x is None else str(x)[:10]

    types = ", ".join(f"{k} {v}" for k, v in ret["by_type"].items()) or "—"
    rows.append(
        (
            "`/v1/return`: sahifalash va hajm",
            f"do'kon qaytarishlari {ret['returns']} ({types}), {val(ret['first'])} — {val(ret['last'])}; "
            f"oxirgi ish: {val(run.get('status'))}, olindi {val(run.get('fetched'))}, "
            f"Uzum jami {val(run.get('total'))}, so'rovlar {val(run.get('requests'))}",
            (run.get("status") == "ok") if run else None,
        )
    )
    rows.append(
        (
            "Qaytarish: sana va tarkib SKU'ga",
            f"sana {ret['date_parsed']}/{ret['returns']}, tarkib {ret['items_linked']}/{ret['items']} "
            f"({ret['units']} dona)",
            (ret["date_parsed"] == ret["returns"] and ret["items_linked"] == ret["items"])
            if ret["returns"]
            else None,
        )
    )
    if lg["with_external_id"] == 0:
        verdict = None
    elif lg["linked"] == lg["with_external_id"]:
        verdict = True
    else:
        verdict = False if lg["unlinked_match_order"] else None
    rows.append(
        (
            "Logistika `externalId` = sotuv qatori id",
            f"{lg['linked']}/{lg['with_external_id']} bog'landi (jami {lg['expenses']}, {fmt(d(lg['amount']))} so'm); "
            f"bog'lanmagan: buyurtma id'siga mos {lg['unlinked_match_order']}, sotuv topilmadi {lg['unlinked_no_sale']}",
            verdict,
        )
    )
    other = "; ".join(
        f"`{o['code']}` ({o['source'] or '—'}) × {o['n']} = {fmt(d(o['amount']))}"
        for o in ex["other_codes"]
    )
    rows.append(
        ('"Boshqa" toifasidagi xarajat kodlari', other or "yo'q", True if not other else None)
    )

    out = ["| Taxmin | Natija | |", "|---|---|---|"]
    out += [f"| {name} | {result} | {mark(ok)} |" for name, result, ok in rows]
    return out, all(ok is not False for _, _, ok in rows)


def semantics(shop: dict[str, Any]) -> list[str]:
    """``amount`` / ``amountReturns`` / ``PARTIALLY_CANCELLED``: ``sellerProfit`` qaysi dona bilan F6 ga teng."""
    sem = shop["sales"]["semantics"]
    out = [
        "| Holat | Qatorlar | F6 = `sellerProfit` (amount bilan) | Logistikasiz mos | Qaytgani bor | "
        "… F6 amount bilan | … F6 (amount − amountReturns) bilan |",
        "|---|---|---|---|---|---|---|",
    ]
    for status, s in sem.items():
        with_profit = s["lines"] - s["no_seller_profit"]
        out.append(
            f"| {status} | {s['lines']} | {s['f6_amount']}/{with_profit} | {s['f6_without_logistics']} | "
            f"{s['with_returns']} | {s['returns_f6_amount']} | {s['returns_f6_net']} |"
        )
    notes = []
    pc = sem.get("PARTIALLY_CANCELLED")
    if pc:
        full = pc["lines"] - pc["no_seller_profit"]
        if full and pc["f6_amount"] == full:
            notes.append(
                "✓ `PARTIALLY_CANCELLED`: `sellerProfit` qolgan `amount` bilan to'liq mos — F2 taxmini "
                "(qolgan dona yakunlangan) tasdiqlandi."
            )
        else:
            notes.append(
                f"≈ `PARTIALLY_CANCELLED`: {pc['f6_amount']}/{full} qator mos — misollarni ko'rish kerak (JSON)."
            )
    returned = [s for s in sem.values() if s["with_returns"]]
    if returned:
        net = sum(s["returns_f6_net"] for s in returned)
        gross = sum(s["returns_f6_amount"] for s in returned)
        total = sum(s["with_returns"] for s in returned)
        if net == total and gross < total:
            notes.append(
                "✗ `amountReturns`: `sellerProfit` (amount − amountReturns) bilan mos — `amount` asl dona, "
                "qaytgan dona ayrilishi kerak (F3–F6 ni tuzatish)."
            )
        elif gross == total:
            notes.append(
                "✓ `amountReturns`: `sellerProfit` `amount` bilan mos — `amount` allaqachon sof dona "
                "(hozirgi hisob to'g'ri)."
            )
        else:
            notes.append(
                f"≈ `amountReturns`: {total} qatordan amount bilan {gross}, sof bilan {net} mos — misollar JSON'da."
            )
    else:
        notes.append(
            "≈ `amountReturns` > 0 qator yo'q — semantika real ma'lumotda tekshirib bo'lmadi."
        )
    return [*out, "", *[f"- {n}" for n in notes]]


# --- Hisobot -------------------------------------------------------------------------------------


def shop_section(
    conn,
    shop_id: int,
    name: str,
    staging: dict[str, Any] | None,
    start: date,
    end: date,
) -> tuple[list[str], bool]:
    out = [f"## {name} ({shop_id})", ""]
    if staging is None:
        return [*out, "✗ Staging'da bu do'kon yo'q (kalit ulangan va do'kon faolmi?).", ""], False
    sync = staging["sync"]
    full = staging["history_status"] == "full"
    no_errors = sync["errors_24h"] == 0
    out += [
        f"Davr: {start} — {end}. Staging tarixi: {staging['history_status'] or '—'} {mark(full)}, "
        f"birinchi sotuv {staging['first_sale_on'] or '—'}; 24 soatda xato ishlar: {sync['errors_24h']} {mark(no_errors)}.",
        "",
    ]
    for p in sync["problems"][:EXAMPLES]:
        out.append(
            f"- {p['started_at']} {p['kind']} ({p['mode']}): {p['status']} — {p['error'] or '—'}"
        )
    if sync["problems"]:
        out.append("")

    old, new = legacy_lines(conn, shop_id), staging_lines(staging)
    ok = full and no_errors
    out += [
        f"| Oy | {' | '.join(f'{LABELS[k]}: legacy' for k in FIELDS)} | Farq (dona / tushum / komissiya / logistika) | |",
        "|---|" + "---|" * len(FIELDS) + "---|---|",
    ]
    for m_start, m_end in months(start, end):
        mo = legacy_report.build_report(conn, [shop_id], m_start.isoformat(), m_end.isoformat())[
            "done"
        ]
        legacy = {k: d(mo[k]) for k in FIELDS}
        staging_t = totals(new.values(), m_start, m_end)
        diffs = [staging_t[k] - legacy[k] for k in FIELDS]
        good = all(abs(x) <= TOL for x in diffs)
        ok &= good
        out.append(
            f"| {m_start:%Y-%m} | {' | '.join(fmt(legacy[k]) for k in FIELDS)} | "
            f"{' / '.join(fmt(x) for x in diffs)} | {mark(good)} |"
        )
    out += ["", *line_diff(old, new, start, end), ""]
    rows, good = assumptions(staging)
    out += [
        "### Taxminlar (B2.6, B2.8)",
        "",
        *rows,
        "",
        "### `amount` va `amountReturns`",
        "",
        *semantics(staging),
        "",
    ]
    statuses = Counter(x.status for x in new.values() if start <= x.day <= end)
    out += [
        "Staging holatlari (davrda): " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())),
        "",
    ]
    return out, ok and good


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Staging (realcheck JSON) va legacy uzum.db ni solishtirish (B2.11)"
    )
    ap.add_argument(
        "--staging", required=True, help="realcheck.json (infra/staging/realcheck.sh chiqargan)"
    )
    ap.add_argument(
        "--db",
        default=str(ROOT / "uzum.db"),
        help="legacy baza (standart: loyiha papkasidagi uzum.db)",
    )
    ap.add_argument(
        "--from", dest="date_from", help="YYYY-MM-DD (standart: legacy'dagi birinchi sotuv)"
    )
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (standart: legacy'dagi oxirgi sotuv)")
    ap.add_argument("--out", default="staging_farqlari.md", help="hisobot fayli (Markdown)")
    args = ap.parse_args(argv)

    for path in (args.staging, args.db):
        if not Path(path).exists():
            print(f"Fayl topilmadi: {path}", file=sys.stderr)
            return 2
    try:
        with open(args.staging, encoding="utf-8") as fh:
            staging = json.load(fh)
    except ValueError:
        print(
            f"{args.staging} — JSON emas yoki bo'sh: serverdagi realcheck.sh xato bergan bo'lishi mumkin "
            "(ssh buyrug'i chiqargan xabarni ko'ring).",
            file=sys.stderr,
        )
        return 2
    load_env()
    conn = connect(args.db)
    try:
        return _run(conn, staging, args)
    finally:
        conn.close()


def _run(conn, staging: dict[str, Any], args: argparse.Namespace) -> int:
    lo, hi = conn.execute("SELECT MIN(created_ms), MAX(created_ms) FROM order_items").fetchone()
    if lo is None:
        print("Legacy bazada sotuv yo'q.", file=sys.stderr)
        return 2

    def day(ms: int) -> date:
        return datetime.fromtimestamp(ms / 1000, TZ).date()

    start = date.fromisoformat(args.date_from) if args.date_from else day(lo)
    end = date.fromisoformat(args.date_to) if args.date_to else day(hi)
    by_ext = {s["external_id"]: s for org in staging["orgs"] for s in org["shops"]}
    report = [
        "# Staging va legacy: solishtirish (B2.11)",
        "",
        f"Yaratildi: {datetime.now(TZ):%Y-%m-%d %H:%M} · staging hisoboti {staging.get('generated_at', '—')} · "
        f"davr {start} — {end}",
        "",
        f"Majburiy (✓ bo'lishi shart): {STATUS} bo'yicha dona, tushum, komissiya, logistika har oy 1 so'mgacha; "
        "tarix to'liq; 24 soatda xato yo'q; taxminlarda ✗ yo'q. ≈ — qo'lda ko'rish kerak.",
        "",
    ]
    ok = True
    for s in conn.execute("SELECT id, name FROM shops ORDER BY id").fetchall():
        section, good = shop_section(
            conn, s["id"], s["name"] or str(s["id"]), by_ext.get(s["id"]), start, end
        )
        ok &= good
        report += section
    report += [
        "## Xulosa",
        "",
        "✓ Hammasi mos." if ok else "✗ Mos kelmagan joy bor — ✗ qatorlarni ko'ring.",
        "",
    ]
    text = "\n".join(report)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nHisobot saqlandi: {args.out}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
