"""Javob modellari (03 §8): pul — so'm, satr ("123456.00"); nisbat — kasr satr ("0.125000" = 12,5%); sana ISO.

Maydon nomlari ``upcore`` dagi nomlar bilan bir xil; UI matni frontendda i18n'dan (``code`` bo'yicha).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel
from upcore.metrics import ExpectedProfit
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
    """M5 hisob varag'i qatori: ``code`` (``revenue``, ``uzum:fine``, ``own:ijara``, ``net_profit`` ...), joriy summa,
    tushumga nisbatan, oldingi davr, farq va o'zgarish ulushi (``upcore.pnl.compare``)."""

    code: str
    amount: Decimal
    share_of_revenue: Decimal | None
    previous: Decimal
    diff: Decimal
    change: Decimal | None  # farq / |oldingi|; oldingi 0 bo'lsa yo'q

    @classmethod
    def of(cls, r: CompareRow) -> RowOut:
        return cls(
            code=r.code,
            amount=r.current.amount,
            share_of_revenue=r.share_of_revenue,
            previous=r.previous.amount,
            diff=r.diff.amount,
            change=r.change,
        )


class PendingOut(BaseModel):
    """F16: Jarayondagi sotuvlardan kutilayotgan foyda (R qo'llangan) va R siz summa."""

    amount: Decimal | None
    rate: Decimal | None
    raw: Decimal
    uncovered_lines: int

    @classmethod
    def of(cls, e: ExpectedProfit) -> PendingOut:
        return cls(
            amount=amount(e.amount),
            rate=e.rate,
            raw=e.raw.amount,
            uncovered_lines=e.uncovered_lines,
        )
