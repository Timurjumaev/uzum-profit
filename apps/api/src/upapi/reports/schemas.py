"""Javob modellari (03 §8): pul — so'm, satr ("123456.00"); nisbat — kasr satr ("0.125000" = 12,5%); sana ISO.

Maydon nomlari ``upcore`` dagi nomlar bilan bir xil; UI matni frontendda i18n'dan (``code`` bo'yicha).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
from upcore.money import Money
from upcore.pnl import CompareRow, Statement


def amount(value: Money | None) -> Decimal | None:
    return None if value is None else value.amount


class UncoveredOut(BaseModel):
    """F15 "tannarxsiz qism" (sariq banner: "N ta sotuv (X so'm) tannarxsiz — foydaga kirmadi")."""

    lines: int
    revenue: Decimal
    payout: Decimal
    expenses: Decimal
    share: Decimal  # 1 − F15


class StatementOut(BaseModel):
    """Hisob varag'i (F3–F15) bitta kesim uchun — ``upcore.pnl.Statement``."""

    revenue: Decimal  # F3
    commission: Decimal  # F4
    logistics: Decimal  # F5
    payout: Decimal  # F6
    cogs: Decimal  # F7
    gross_profit: Decimal  # F8
    uzum_expenses: dict[str, Decimal]  # F9 turlari
    uzum_total: Decimal  # F9 jami (sharshara qadami)
    own_expenses: dict[str, Decimal]  # F10 toifalari
    own_total: Decimal  # F10 jami
    tax: Decimal  # F11
    expenses_deducted: Decimal  # F15 bo'yicha ayrilgan
    net_profit: Decimal  # F12
    coverage: Decimal  # F15
    margin: Decimal | None  # F13 (ADR-024)
    roi: Decimal | None  # F14
    units: int
    covered_units: int
    lines: int
    # ADR-036: sotuvlar Yakunlangan + Jarayonda; shundan Jarayondagi (yakuniy emas) qism.
    units_processing: int
    revenue_processing: Decimal
    # ADR-037: sof foyda ikki qismda — yakunlangan + kutilayotgan (Jarayonda, F16) = ``net_profit``.
    net_profit_done: Decimal
    net_profit_processing: Decimal
    revenue_done: Decimal
    units_done: int
    lines_processing: int
    # F5 (ADR-037): logistikaning taxminiy qismi (Uzum hali yozmagan, F40 × dona) va tarifi noma'lum qatorlar.
    logistics_estimated: Decimal
    logistics_estimated_units: int
    logistics_estimated_lines: int
    logistics_missing_lines: int
    # ADR-039: Uzum xarajatlarining taxminiy qismi turlar bo'yicha (F42 kutilayotgan reklama, "≈").
    uzum_estimated: dict[str, Decimal]
    # B4.22: sotuvsiz kataklar xarajati (yakunlangan qismda): sotilmagan tovar saqlashi, sotuvsiz kun xarajatlari.
    idle_expenses: Decimal
    uncovered: UncoveredOut
    direct_total: Decimal  # ADR-026
    allocated_total: Decimal
    uzum_allocated: dict[str, Decimal]
    own_allocated: dict[str, Decimal]
    uzum_direct: Decimal  # ADR-026: F9 to'g'ridan-to'g'ri / taqsimlangan (jami)
    uzum_allocated_total: Decimal
    own_direct: Decimal  # F10 to'g'ridan-to'g'ri / taqsimlangan (jami)
    own_allocated_total: Decimal

    @classmethod
    def of(cls, s: Statement) -> StatementOut:
        return cls(
            revenue=s.revenue.amount,
            commission=s.commission.amount,
            logistics=s.logistics.amount,
            payout=s.payout.amount,
            cogs=s.cogs.amount,
            gross_profit=s.gross_profit.amount,
            uzum_expenses={c.value: a.amount for c, a in sorted(s.uzum_expenses.items())},
            uzum_total=s.uzum_total.amount,
            own_expenses={c: a.amount for c, a in sorted(s.own_expenses.items())},
            own_total=s.own_total.amount,
            tax=s.tax.amount,
            expenses_deducted=s.expenses_deducted.amount,
            net_profit=s.net_profit.amount,
            coverage=s.coverage,
            margin=s.margin,
            roi=s.roi,
            units=s.units,
            covered_units=s.covered_units,
            lines=s.lines,
            units_processing=s.units_processing,
            revenue_processing=s.revenue_processing.amount,
            net_profit_done=s.net_profit_done.amount,
            net_profit_processing=s.net_profit_processing.amount,
            revenue_done=s.revenue_done.amount,
            units_done=s.units_done,
            lines_processing=s.lines_processing,
            logistics_estimated=s.logistics_estimated.amount,
            logistics_estimated_units=s.logistics_estimated_units,
            logistics_estimated_lines=s.logistics_estimated_lines,
            logistics_missing_lines=s.logistics_missing_lines,
            uzum_estimated={c.value: a.amount for c, a in sorted(s.uzum_estimated.items())},
            idle_expenses=s.idle_expenses.amount,
            uncovered=UncoveredOut(
                lines=s.uncovered_lines,
                revenue=s.uncovered_revenue.amount,
                payout=s.uncovered_payout.amount,
                expenses=s.uncovered_expenses.amount,
                share=s.uncovered_share,
            ),
            direct_total=s.direct_total.amount,
            allocated_total=s.allocated_total.amount,
            uzum_allocated={c.value: a.amount for c, a in sorted(s.uzum_allocated.items())},
            own_allocated={c: a.amount for c, a in sorted(s.own_allocated.items())},
            uzum_direct=s.uzum_direct.amount,
            uzum_allocated_total=s.uzum_allocated_total.amount,
            own_direct=s.own_direct.amount,
            own_allocated_total=s.own_allocated_total.amount,
        )


class RowOut(BaseModel):
    """M5 hisob varag'i qatori: ``code`` (``revenue``, ``uzum:fine``, ``own:ijara``, ``net_profit`` ...), joriy summa
    (jami), shundan yakunlangan va kutilayotgan (ADR-037), tushumga nisbatan, oldingi davr, farq va o'zgarish ulushi
    (``upcore.pnl.compare``)."""

    code: str
    amount: Decimal
    done: Decimal  # yakunlangan qism (Yakunlangan sotuvlar)
    processing: Decimal  # kutilayotgan qism (Jarayondagi sotuvlar)
    share_of_revenue: Decimal | None
    previous: Decimal
    diff: Decimal
    change: Decimal | None  # farq / |oldingi|; oldingi 0 bo'lsa yo'q

    @classmethod
    def of(cls, r: CompareRow) -> RowOut:
        return cls(
            code=r.code,
            amount=r.current.amount,
            done=r.done.amount,
            processing=r.processing.amount,
            share_of_revenue=r.share_of_revenue,
            previous=r.previous.amount,
            diff=r.diff.amount,
            change=r.change,
        )


class ExpectedOut(BaseModel):
    """F16 (ADR-037): kutilayotgan sof foyda — Jarayondagi sotuvlar qismi (mijoz hali olmagan yoki qaytarish muddati
    tugamagan): tushumdan komissiya, logistika (Uzum hali yozmagani — F40 bo'yicha taxminiy), tannarx, o'z reklamasi
    (yechilgani va hali topshirilmaganlarga F42 taxmini) va katak xarajatlarining tushum ulushidagi qismi ayrilgan. ``rate`` — fakt (oxirgi 90 kunda yakuniy holatga yetganlarning
    Yakunlangan ulushi), summaga ko'paytirilmaydi; ma'lumot kam bo'lsa ``None``."""

    units: int
    lines: int
    revenue: Decimal
    commission: Decimal
    logistics: Decimal
    cogs: Decimal
    expenses: Decimal  # ayrilgan xarajat ulushi: (F9 + F10 + F11) × qamrov
    net_profit: Decimal
    uncovered_lines: int  # tannarxsiz — kutilayotgan foydaga kirmagan
    logistics_estimated: Decimal
    logistics_estimated_units: int
    logistics_missing_lines: int
    uzum_estimated: dict[str, Decimal]  # ADR-039: F42 kutilayotgan reklama (taxminiy)
    rate: Decimal | None

    @classmethod
    def of(cls, s: Statement, rate: Decimal | None) -> ExpectedOut:
        p = s.processing
        if p is None:
            zero = Decimal(0)
            return cls(
                units=0,
                lines=0,
                revenue=zero,
                commission=zero,
                logistics=zero,
                cogs=zero,
                expenses=zero,
                net_profit=zero,
                uncovered_lines=0,
                logistics_estimated=zero,
                logistics_estimated_units=0,
                logistics_missing_lines=0,
                uzum_estimated={},
                rate=rate,
            )
        return cls(
            units=p.units,
            lines=p.lines,
            revenue=p.revenue.amount,
            commission=p.commission.amount,
            logistics=p.logistics.amount,
            cogs=p.cogs.amount,
            expenses=p.expenses_deducted.amount,
            net_profit=p.net_profit.amount,
            uncovered_lines=p.uncovered_lines,
            logistics_estimated=p.logistics_estimated.amount,
            logistics_estimated_units=p.logistics_estimated_units,
            logistics_missing_lines=p.logistics_missing_lines,
            uzum_estimated={c.value: a.amount for c, a in sorted(p.uzum_estimated.items())},
            rate=rate,
        )
