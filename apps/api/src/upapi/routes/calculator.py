"""``/calculator``: xariddan oldingi kalkulyator (M13, B5.9; F35–F37). Ruxsat — ``view_finance``.

Kiritish: 1688 narxi (CNY), Xitoy ichki yetkazish, dona, dona vazni va o'lchami, kargo narxi ($/kg yoki $/m³), qo'shimcha
xarajat, Uzum toifasi komissiyasi, mo'ljallangan narx. Natija: birlik tannarx (kurs — CBU, yoki qo'lda), Uzum logistikasi
(F37, o'lchamdan), komissiya, soliq, foyda, marja, ROI, zararsizlik narxi (F35), maqsadli marja narxi (F36). Soliq % —
soliq profilidan taklif (foizli, tushumga qo'llanadigan qatorlar; to'lovga qo'llanadigan qator bo'lsa belgilanadi).
Formulalar — ``upcore`` da (tamoyil 4); bu yerda faqat kiritishni yig'ish va ma'lumotnomalarni o'qish.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection
from upcore.fx import FxError
from upcore.money import Currency, Money
from upcore.pnl import TaxBase
from upcore.tariffs import (
    SEED_LOGISTICS,
    LogisticsTariff,
    TariffError,
    liters,
    logistics_fee,
    tariff_on,
)
from upcore.tax import percent_rules
from upcore.unit import CargoBasis, landed_unit_cost, unit_calc

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.calc.lots import Rates
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports import cells as rc
from upapi.reports.common import today
from upapi.routes.skus import UnitCalcOut, unit_calc_out

router = APIRouter(tags=["calculator"])
Finance = Annotated[OrgContext, Depends(require(Permission.VIEW_FINANCE))]
UZS = Currency.UZS

Sum = Annotated[Decimal, Query(ge=0, le=Decimal("1e12"))]
Percent = Annotated[Decimal, Query(ge=0, le=100)]
Dim = Annotated[Decimal, Query(gt=0, le=Decimal("100000"))]


class RateOut(BaseModel):
    cny: Decimal | None  # 1 CNY necha so'm
    usd: Decimal | None
    day: date | None
    source: str | None  # ``cbu`` / ``market`` (zaxira, rasmiy emas) / ``manual``


class TariffOut(BaseModel):
    valid_from: date
    base_fee: Decimal  # ≤ 1 l
    per_liter: Decimal
    max_fee: Decimal
    no_dims_fee: Decimal  # o'lcham kiritilmaganda


class CalculatorDefaultsOut(BaseModel):
    """Kalkulyator boshlang'ich qiymatlari: kurslar (CBU), soliq taklifi va F37 tarifi."""

    rates: RateOut
    tax_pct: (
        Decimal | None
    )  # soliq profilidagi foizli, tushumga qo'llanadigan qatorlar yig'indisi; profil yo'q — null
    tax_on_payout: bool  # profilda to'lovga (F6) qo'llanadigan foizli qator ham bor — kalkulyator uni hisobga olmaydi
    tariff: TariffOut | None


class LandedOut(BaseModel):
    goods: Decimal  # 1688 narxi × kurs
    china: Decimal  # Xitoy ichki yetkazish / dona
    cargo: Decimal
    extra: Decimal
    unit_cost: Decimal
    cargo_basis: CargoBasis | None  # kargo qaysi usulda: vazn yoki hajm; hisoblanmagan — null


class LogisticsOut(BaseModel):
    fee: Decimal  # F37
    liters: int | None  # o'lcham kiritilgan bo'lsa
    source: str  # ``dims`` — o'lchamdan; ``no_dims`` — o'lcham yo'q, tarifdagi "o'lchamsiz" narx


class CalculatorOut(BaseModel):
    rates: RateOut
    landed: LandedOut
    logistics: LogisticsOut
    tax_pct: Decimal  # hisobda ishlatilgan
    unit: UnitCalcOut


class CargoSuggestionOut(BaseModel):
    """O'xshash (oldingi) xaridlardagi haqiqiy kargo xarajatidan o'rtacha (ADR-061: tarif kiritilmaydi)."""

    purchases: int  # hisobga olingan xaridlar soni (kargo xarajati va vazni/donasi ma'lum)
    usd_per_kg: Decimal | None  # vazni ma'lum xaridlar bo'yicha o'rtacha (jami $ / jami kg)
    weighed: int  # shundan vazni ma'lum xaridlar
    uzs_per_unit: Decimal | None  # jami so'm / jami dona (kurs — to'langan kuni CBU)
    since: date | None  # eng eski hisobga olingan xarid kuni


SUGGEST_LIMIT = 20


async def _cargo_suggestion(conn: AsyncConnection, day: date) -> CargoSuggestionOut:
    cargo = (
        select(
            m.cost_components.c.purchase_id,
            m.cost_components.c.amount,
            m.cost_components.c.currency,
            m.cost_components.c.paid_on,
            m.cost_components.c.weight_kg,
        )
        .where(m.cost_components.c.kind == "cargo", m.cost_components.c.purchase_id.is_not(None))
        .subquery()
    )
    units = (
        select(
            m.purchase_lines.c.purchase_id,
            func.sum(
                func.coalesce(m.purchase_lines.c.received_qty, m.purchase_lines.c.ordered_qty)
            ).label("qty"),
            func.sum(
                m.purchase_lines.c.unit_weight
                * func.coalesce(m.purchase_lines.c.received_qty, m.purchase_lines.c.ordered_qty)
            ).label("kg"),
        )
        .group_by(m.purchase_lines.c.purchase_id)
        .subquery()
    )
    rows = (
        await conn.execute(
            select(cargo, units.c.qty, units.c.kg, m.purchases.c.ordered_on)
            .join(units, units.c.purchase_id == cargo.c.purchase_id)
            .join(m.purchases, m.purchases.c.id == cargo.c.purchase_id)
            .where(cargo.c.amount > 0)
            .order_by(func.coalesce(cargo.c.paid_on, m.purchases.c.ordered_on).desc().nulls_last())
            .limit(SUGGEST_LIMIT)
        )
    ).all()
    rates = Rates(conn, day)
    await rates.load([Currency.USD, Currency.CNY])
    usd_sum = kg_sum = uzs_sum = qty_sum = Decimal(0)
    n = weighed = 0
    since: date | None = None
    for r in rows:
        when = r.paid_on or r.ordered_on
        try:
            ccy = Currency(r.currency)
            uzs = r.amount if ccy is UZS else r.amount * rates.cbu(ccy, when).rate
            usd_rate = rates.cbu(Currency.USD, when).rate
        except (FxError, ValueError):
            continue  # kursi yo'q xarid — taxmin qilinmaydi, o'rtachaga kirmaydi
        qty = Decimal(r.qty or 0)
        if qty <= 0:
            continue
        n += 1
        uzs_sum += uzs
        qty_sum += qty
        if when is not None and (since is None or when < since):
            since = when
        kg = r.weight_kg if r.weight_kg else r.kg
        if kg and kg > 0:
            weighed += 1
            kg_sum += kg
            usd_sum += uzs / usd_rate
    return CargoSuggestionOut(
        purchases=n,
        usd_per_kg=(usd_sum / kg_sum).quantize(Decimal("0.01")) if kg_sum > 0 else None,
        weighed=weighed,
        uzs_per_unit=(uzs_sum / qty_sum).quantize(Decimal("1")) if qty_sum > 0 else None,
        since=since,
    )


@router.get("/orgs/{org_id}/calculator/cargo-suggestion", response_model=CargoSuggestionOut)
async def cargo_suggestion(ctx: Finance) -> CargoSuggestionOut:
    return await _cargo_suggestion(ctx.conn, today())


async def logistics_tariffs(conn: AsyncConnection) -> list[LogisticsTariff]:
    """F37 tariflari ma'lumotnomadan (sanasi bilan); bazada yo'q bo'lsa — boshlang'ich (``SEED_LOGISTICS``)."""
    out = []
    for r in await conn.execute(select(m.ref_logistics_tariffs)):
        rules = r.rules

        def money(key: str, rules: dict[str, Any] = rules) -> Money:
            return Money(Decimal(str(rules[key]["amount"])), UZS)

        out.append(
            LogisticsTariff(
                valid_from=r.valid_from,
                base_fee=money("base_fee"),
                per_liter=money("per_liter"),
                max_fee=money("max_fee"),
                no_dims_fee=money("no_dims_fee"),
                sim_fee=money("sim_fee"),
                base_liters=int(rules.get("base_liters", 1)),
            )
        )
    return out or list(SEED_LOGISTICS)


async def _rates(conn: AsyncConnection, day: date) -> RateOut:
    book = Rates(conn, day)
    await book.load([Currency.CNY, Currency.USD])
    values: dict[str, tuple[Decimal, date, str]] = {}
    for ccy in (Currency.CNY, Currency.USD):
        try:
            r = book.cbu(ccy, day)
        except FxError:
            continue  # kurs yo'q — taxmin qilinmaydi, maydon bo'sh
        values[ccy.value] = (r.rate, r.day, r.source.value)
    cny, usd = values.get("CNY"), values.get("USD")
    days = [v[1] for v in values.values()]
    sources = {v[2] for v in values.values()}
    return RateOut(
        cny=cny[0] if cny else None,
        usd=usd[0] if usd else None,
        day=min(days) if days else None,
        source=("market" if "market" in sources else "cbu") if sources else None,
    )


async def _tax(conn: AsyncConnection, day: date) -> tuple[Decimal | None, bool]:
    rules = percent_rules(await rc.tax_profiles(conn), day)
    if not rules:
        return None, False
    on_revenue = sum((r.rate_pct for _, r in rules if r.base is TaxBase.REVENUE), Decimal(0))
    return on_revenue, any(r.base is TaxBase.PAYOUT for _, r in rules)


@router.get("/orgs/{org_id}/calculator/defaults", response_model=CalculatorDefaultsOut)
async def calculator_defaults(ctx: Finance) -> CalculatorDefaultsOut:
    day = today()
    tax, on_payout = await _tax(ctx.conn, day)
    try:
        t = tariff_on(await logistics_tariffs(ctx.conn), day)
        tariff: TariffOut | None = TariffOut(
            valid_from=t.valid_from,
            base_fee=t.base_fee.amount,
            per_liter=t.per_liter.amount,
            max_fee=t.max_fee.amount,
            no_dims_fee=t.no_dims_fee.amount,
        )
    except TariffError:
        tariff = None
    return CalculatorDefaultsOut(
        rates=await _rates(ctx.conn, day), tax_pct=tax, tax_on_payout=on_payout, tariff=tariff
    )


@router.get("/orgs/{org_id}/calculator", response_model=CalculatorOut)
async def calculator(
    ctx: Finance,
    price_cny: Sum,
    price: Sum,
    commission_pct: Percent,
    qty: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    china_cny_total: Sum = Decimal(0),
    weight_kg: Annotated[Decimal | None, Query(gt=0, le=Decimal("100000"))] = None,
    length_cm: Dim | None = None,
    width_cm: Dim | None = None,
    height_cm: Dim | None = None,
    cargo_usd_per_kg: Annotated[Decimal | None, Query(ge=0, le=Decimal("1e6"))] = None,
    cargo_usd_per_m3: Annotated[Decimal | None, Query(ge=0, le=Decimal("1e6"))] = None,
    extra_uzs: Sum = Decimal(0),
    packaging_uzs: Sum = Decimal(0),
    tax_pct: Percent | None = None,
    ads_pct: Percent = Decimal(0),
    target_margin_pct: Annotated[Decimal | None, Query(ge=0, le=100)] = None,
    cny_rate: Annotated[Decimal | None, Query(gt=0, le=Decimal("1e6"))] = None,
    usd_rate: Annotated[Decimal | None, Query(gt=0, le=Decimal("1e6"))] = None,
) -> CalculatorOut:
    day = today()
    rates = await _rates(ctx.conn, day)
    manual = cny_rate is not None or usd_rate is not None
    cny = cny_rate if cny_rate is not None else rates.cny
    usd = usd_rate if usd_rate is not None else rates.usd
    if cny is None:
        raise AppError("fx_rate_missing", 422, detail="CNY kursi yo'q — kursni qo'lda kiriting")
    dims = (length_cm, width_cm, height_cm)
    has_dims = all(d is not None for d in dims)
    volume_m3 = length_cm * width_cm * height_cm / Decimal(1_000_000) if has_dims else None  # type: ignore[operator]
    landed = landed_unit_cost(
        price_cny=price_cny,
        qty=qty,
        cny_rate=cny,
        china_cny_total=china_cny_total,
        weight_kg=weight_kg,
        volume_m3=volume_m3,
        cargo_usd_per_kg=cargo_usd_per_kg,
        cargo_usd_per_m3=cargo_usd_per_m3,
        usd_rate=usd,
        extra_uzs=extra_uzs,
    )
    try:
        tariff = tariff_on(await logistics_tariffs(ctx.conn), day)
    except TariffError:
        raise AppError(
            "tariff_missing", 422, detail="Logistika tarifi ma'lumotnomada yo'q"
        ) from None
    dims_mm = (
        tuple(int(d * 10) for d in dims) if has_dims else None  # type: ignore[operator]
    )
    fee = logistics_fee(tariff, dims_mm)  # type: ignore[arg-type]
    if tax_pct is None:
        suggested, _ = await _tax(ctx.conn, day)
        tax_pct = suggested if suggested is not None else Decimal(0)
    unit = unit_calc(
        Money(price, UZS),
        landed.unit_cost,
        fee,
        Money(packaging_uzs, UZS),
        commission_pct,
        tax_pct,
        ads_pct,
        target_margin_pct,
    )
    return CalculatorOut(
        rates=RateOut(
            cny=cny,
            usd=usd,
            day=rates.day,
            source="manual" if manual else rates.source,
        ),
        landed=LandedOut(
            goods=landed.goods.amount,
            china=landed.china.amount,
            cargo=landed.cargo.amount,
            extra=landed.extra.amount,
            unit_cost=landed.unit_cost.amount,
            cargo_basis=landed.cargo_basis,
        ),
        logistics=LogisticsOut(
            fee=fee.amount,
            liters=liters(*dims_mm) if dims_mm else None,
            source="dims" if dims_mm else "no_dims",
        ),
        tax_pct=tax_pct,
        unit=unit_calc_out(unit),
    )


# --- Saqlangan ssenariylar (B5.9-3): faqat kiritish; natija har ochilganda joriy kurs va tarif bilan qayta hisoblanadi ---

SCENARIO_FIELDS = frozenset(
    {
        "price_cny", "qty", "china_cny_total", "weight_kg", "length_cm", "width_cm", "height_cm",
        "cargo_usd_per_kg", "cargo_usd_per_m3", "extra_uzs", "packaging_uzs", "price", "commission_pct",
        "tax_pct", "ads_pct", "target_margin_pct", "cny_rate", "usd_rate",
    }
)  # fmt: skip
MAX_SCENARIOS = 100


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    inputs: dict[str, str]


class ScenarioOut(BaseModel):
    id: UUID
    name: str
    inputs: dict[str, str]
    updated_at: datetime


def _scenario_out(r: Any) -> ScenarioOut:
    return ScenarioOut(id=r.id, name=r.name, inputs=r.inputs, updated_at=r.updated_at)


def _clean_inputs(inputs: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in inputs.items():
        if key not in SCENARIO_FIELDS:
            raise AppError("scenario_invalid", 422, detail=f"noma'lum maydon: {key}")
        try:
            number = Decimal(value)
        except ArithmeticError:
            raise AppError("scenario_invalid", 422, detail=f"{key}: son emas") from None
        if not number.is_finite() or abs(number) > Decimal("1e12"):
            raise AppError("scenario_invalid", 422, detail=f"{key}: noto'g'ri qiymat")
        out[key] = value.strip()
    return out


@router.get("/orgs/{org_id}/calculator/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(ctx: Finance) -> list[ScenarioOut]:
    t = m.calculator_scenarios
    rows = await ctx.conn.execute(select(t).order_by(t.c.updated_at.desc(), t.c.id))
    return [_scenario_out(r) for r in rows]


@router.post("/orgs/{org_id}/calculator/scenarios", response_model=ScenarioOut)
async def save_scenario(body: ScenarioIn, ctx: Finance, response: Response) -> ScenarioOut:
    """Shu nomli ssenariy bor bo'lsa — kiritishi yangilanadi (201 — yangi, 200 — yangilandi)."""
    t = m.calculator_scenarios
    name = body.name.strip()
    if not name:
        raise AppError("scenario_invalid", 422, detail="nom bo'sh")
    inputs = _clean_inputs(body.inputs)
    existing = await ctx.conn.scalar(select(t.c.id).where(t.c.name == name))
    if (
        existing is None
        and (await ctx.conn.scalar(select(func.count()).select_from(t)) or 0) >= MAX_SCENARIOS
    ):
        raise AppError("scenario_limit", 422, detail=f"ko'pi bilan {MAX_SCENARIOS} ta ssenariy")
    stmt = pg_insert(t).values(org_id=ctx.org_id, name=name, inputs=inputs)
    row = (
        await ctx.conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[t.c.org_id, t.c.name],
                set_={"inputs": stmt.excluded.inputs, "updated_at": func.now()},
            ).returning(t)
        )
    ).one()
    await ctx.audit("calculator_scenario.save", "calculator_scenario", row.id, after={"name": name})
    response.status_code = 200 if existing is not None else 201
    return _scenario_out(row)


@router.delete("/orgs/{org_id}/calculator/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(scenario_id: UUID, ctx: Finance) -> None:
    t = m.calculator_scenarios
    row = (
        await ctx.conn.execute(delete(t).where(t.c.id == scenario_id).returning(t.c.id, t.c.name))
    ).first()
    if row is None:
        raise AppError("scenario_not_found", 404, detail="ssenariy topilmadi")
    await ctx.audit(
        "calculator_scenario.delete", "calculator_scenario", row.id, before={"name": row.name}
    )
