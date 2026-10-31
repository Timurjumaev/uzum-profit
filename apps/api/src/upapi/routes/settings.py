"""``/settings``: tashkilot sozlamalari (M16, B4.8) — tannarx usuli, soliq profili (F11), Uzum to'lov jadvali (F38),
standart yetkazish muddatlari (F25) va ABC qamrov kunlari (F27). Uzum bonuslari — :mod:`upapi.routes.waivers`,
do'konlar — :mod:`upapi.routes.accounts`.

O'qish — ``view_settings`` (egasi, menejer, buxgalter); yozish — ``manage_settings`` (egasi, menejer), har o'zgarish
audit jurnaliga yoziladi. Soliq profili va to'lov jadvali sana bo'yicha (``valid_from``): eski davr hisobi o'zgarmaydi,
yangi qator keyingi sanalarga amal qiladi — hisobotlar o'qilganda hisoblanadi, qayta hisob kerak emas. **Tannarx usuli**
(FIFO ↔ o'rtacha) o'tgan sotuvlar tannarxini o'zgartiradi — shu tranzaksiyada hamma tovar/xarid qayta hisob so'rovi,
commitdan keyin ``calc.org`` ishi (P&L'da "qayta hisoblandi"). Sinxron sozlamaga tegmaydi (tamoyil 7).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, insert, select, update
from upcore.cash import SEED_SCHEDULES, ScheduleKind
from upcore.inventory import DEFAULT, AbcClass
from upcore.pnl import TaxBase
from upcore.tax import TaxRegime

from upapi import calc, orgsettings
from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.reports.common import today
from upapi.routes.purchases import _kick

router = APIRouter(tags=["settings"])
Viewer = Annotated[OrgContext, Depends(require(Permission.VIEW_SETTINGS))]
Manager = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=7, decimal_places=3)]


class TaxProfileOut(BaseModel):
    id: UUID
    valid_from: date
    regime: TaxRegime
    rate_pct: Decimal
    base: TaxBase
    vat_pct: Decimal
    profit_pct: Decimal


class TaxRateOut(BaseModel):
    """Ma'lumotnoma (``ref_tax_rates``): joriy stavka — profilni to'ldirishda tavsiya (buxgalter tasdiqlaydi)."""

    code: str
    rate_pct: Decimal
    note: str | None


class PayoutScheduleOut(BaseModel):
    id: UUID
    shop_id: UUID
    kind: ScheduleKind
    valid_from: date


class PayoutTermsOut(BaseModel):
    kind: ScheduleKind
    days_of_month: list[int] | None  # ``null`` — har ish kuni
    fee_pct: Decimal  # pul yechish foizi


class InventorySettingsOut(BaseModel):
    stages: list[str]  # F25 bosqichlari tartib bilan
    lead_days: dict[str, int] | None  # sozlanmagan — ``null`` (muddat xaridlar tarixidan)
    cover_days: dict[str, int]  # ABC qamrov (sozlangan yoki standart)
    cover_defaults: dict[str, int]


class SettingsOut(BaseModel):
    cost_method: Literal["fifo", "average"]
    tax_profiles: list[TaxProfileOut]
    tax_rates: list[TaxRateOut]
    payout_schedules: list[PayoutScheduleOut]
    payout_terms: list[PayoutTermsOut]
    inventory: InventorySettingsOut


class CostMethodIn(BaseModel):
    cost_method: Literal["fifo", "average"]


class TaxProfileIn(BaseModel):
    valid_from: date
    regime: TaxRegime
    rate_pct: Pct = Decimal(0)  # (a) aylanmadan foiz
    base: TaxBase = TaxBase.REVENUE  # (a)
    vat_pct: Pct = Decimal(0)  # (c)
    profit_pct: Pct = Decimal(0)  # (c)


class TaxProfilePatch(BaseModel):
    valid_from: date | None = None
    regime: TaxRegime | None = None
    rate_pct: Pct | None = None
    base: TaxBase | None = None
    vat_pct: Pct | None = None
    profit_pct: Pct | None = None


class PayoutScheduleIn(BaseModel):
    shop_id: UUID
    kind: ScheduleKind
    valid_from: date


class InventorySettingsIn(BaseModel):
    """``lead_days`` — hamma bosqich yoki ``null`` (tozalash); ``cover_days`` — A, B, C yoki ``null`` (standart)."""

    lead_days: dict[str, Annotated[int, Field(ge=0, le=orgsettings.MAX_LEAD_DAYS)]] | None = None
    cover_days: dict[str, Annotated[int, Field(ge=0, le=orgsettings.MAX_COVER_DAYS)]] | None = None


def _plain(values: dict[str, Any]) -> dict[str, Any]:
    """JSONB uchun: sana, Decimal, enum — satr."""
    return {
        k: v if isinstance(v, (str, bool, int, list, dict)) or v is None else str(v)
        for k, v in values.items()
    }


def _normalized(values: dict[str, Any]) -> dict[str, Any]:
    """Rejimga tegishli bo'lmagan maydonlar nolga qaytadi (eski qiymat jim qolib ketmasin)."""
    regime = TaxRegime(values["regime"])
    if regime is not TaxRegime.TURNOVER:
        values["rate_pct"], values["base"] = Decimal(0), TaxBase.REVENUE
    if regime is not TaxRegime.VAT_PROFIT:
        values["vat_pct"] = values["profit_pct"] = Decimal(0)
    if regime is TaxRegime.TURNOVER and values["rate_pct"] <= 0:
        raise AppError("tax_rate_required", 422, detail="aylanma solig'i stavkasi 0 dan katta")
    return values


async def _read(ctx: OrgContext) -> SettingsOut:
    conn = ctx.conn
    org = (await conn.execute(select(m.orgs.c.cost_method, m.orgs.c.settings))).one()
    cfg = orgsettings.parse(org.settings)
    t, ps, rr = m.tax_profiles, m.payout_schedules, m.ref_tax_rates
    taxes = await conn.execute(select(t).order_by(t.c.valid_from.desc()))
    pays = await conn.execute(select(ps).order_by(ps.c.valid_from.desc(), ps.c.created_at))
    latest = (
        select(rr.c.code, func.max(rr.c.valid_from).label("d"))
        .where(rr.c.valid_from <= today())
        .group_by(rr.c.code)
        .subquery()
    )
    rates = await conn.execute(
        select(rr.c.code, rr.c.rate_pct, rr.c.note)
        .join(latest, (latest.c.code == rr.c.code) & (latest.c.d == rr.c.valid_from))
        .order_by(rr.c.code)
    )
    effective = {**DEFAULT.cover_days, **cfg.cover_days}
    return SettingsOut(
        cost_method=org.cost_method,
        tax_profiles=[TaxProfileOut.model_validate(r._asdict()) for r in taxes],
        tax_rates=[TaxRateOut.model_validate(r._asdict()) for r in rates],
        payout_schedules=[PayoutScheduleOut.model_validate(r._asdict()) for r in pays],
        payout_terms=[
            PayoutTermsOut(
                kind=k,
                days_of_month=list(v.days_of_month) if v.days_of_month is not None else None,
                fee_pct=v.fee_pct,
            )
            for k, v in SEED_SCHEDULES.items()
        ],
        inventory=InventorySettingsOut(
            stages=list(orgsettings.STAGES),
            lead_days=dict(cfg.lead_days) or None,
            cover_days={k.value: effective[k] for k in AbcClass},
            cover_defaults={k.value: DEFAULT.cover_days[k] for k in AbcClass},
        ),
    )


@router.get("/orgs/{org_id}/settings", response_model=SettingsOut)
async def get_settings(ctx: Viewer) -> SettingsOut:
    return await _read(ctx)


# --- Tannarx usuli ----------------------------------------------------------------------------


@router.put("/orgs/{org_id}/settings/cost-method", response_model=SettingsOut)
async def set_cost_method(
    body: CostMethodIn, ctx: Manager, request: Request, background: BackgroundTasks
) -> SettingsOut:
    """FIFO ↔ o'rtacha. O'zgarsa — hamma sotuv tannarxi qayta hisoblanadi (navbat orqali)."""
    o = m.orgs
    before = await ctx.conn.scalar(select(o.c.cost_method))
    if before != body.cost_method:
        await ctx.conn.execute(
            update(o).values(cost_method=body.cost_method, updated_at=func.now())
        )
        await ctx.audit(
            "settings.cost_method",
            "org",
            ctx.org_id,
            before={"cost_method": before},
            after={"cost_method": body.cost_method},
        )
        await calc.request_full(ctx.conn, ctx.org_id)
        background.add_task(_kick, request, ctx.org_id)
    return await _read(ctx)


# --- Soliq profili ----------------------------------------------------------------------------


async def _tax_row(ctx: OrgContext, profile_id: UUID) -> Any:
    t = m.tax_profiles
    row = (await ctx.conn.execute(select(t).where(t.c.id == profile_id))).first()
    if row is None:
        raise AppError("tax_profile_not_found", 404)
    return row


async def _tax_free(ctx: OrgContext, valid_from: date, exclude: UUID | None = None) -> None:
    t = m.tax_profiles
    query = select(t.c.id).where(t.c.valid_from == valid_from)
    if exclude is not None:
        query = query.where(t.c.id != exclude)
    if await ctx.conn.scalar(query) is not None:
        raise AppError("tax_profile_exists", 409, detail="shu sanada profil allaqachon bor")


@router.post("/orgs/{org_id}/tax-profiles", response_model=SettingsOut, status_code=201)
async def create_tax_profile(body: TaxProfileIn, ctx: Manager) -> SettingsOut:
    values = _normalized(body.model_dump())
    await _tax_free(ctx, body.valid_from)
    row_id = await ctx.conn.scalar(
        insert(m.tax_profiles).values(org_id=ctx.org_id, **values).returning(m.tax_profiles.c.id)
    )
    await ctx.audit("tax_profile.create", "tax_profile", row_id, after=_plain(values))
    return await _read(ctx)


@router.patch("/orgs/{org_id}/tax-profiles/{profile_id}", response_model=SettingsOut)
async def update_tax_profile(profile_id: UUID, body: TaxProfilePatch, ctx: Manager) -> SettingsOut:
    row = await _tax_row(ctx, profile_id)
    keys = ("valid_from", "regime", "rate_pct", "base", "vat_pct", "profit_pct")
    current = {k: getattr(row, k) for k in keys}
    merged = _normalized({**current, **body.model_dump(exclude_unset=True, exclude_none=True)})
    if merged["valid_from"] != row.valid_from:
        await _tax_free(ctx, merged["valid_from"], exclude=profile_id)
    t = m.tax_profiles
    await ctx.conn.execute(
        update(t).where(t.c.id == profile_id).values(**merged, updated_at=func.now())
    )
    await ctx.audit(
        "tax_profile.update",
        "tax_profile",
        profile_id,
        before=_plain(current),
        after=_plain(merged),
    )
    return await _read(ctx)


@router.delete("/orgs/{org_id}/tax-profiles/{profile_id}", response_model=SettingsOut)
async def delete_tax_profile(profile_id: UUID, ctx: Manager) -> SettingsOut:
    row = await _tax_row(ctx, profile_id)
    await ctx.conn.execute(delete(m.tax_profiles).where(m.tax_profiles.c.id == profile_id))
    await ctx.audit(
        "tax_profile.delete",
        "tax_profile",
        profile_id,
        before=_plain({"valid_from": row.valid_from, "regime": row.regime}),
    )
    return await _read(ctx)


# --- Uzum to'lov jadvali ----------------------------------------------------------------------


@router.post("/orgs/{org_id}/payout-schedules", response_model=SettingsOut, status_code=201)
async def create_payout_schedule(body: PayoutScheduleIn, ctx: Manager) -> SettingsOut:
    ps = m.payout_schedules
    if await ctx.conn.scalar(select(m.shops.c.id).where(m.shops.c.id == body.shop_id)) is None:
        raise AppError("shop_not_found", 404)
    if (
        await ctx.conn.scalar(
            select(ps.c.id).where(ps.c.shop_id == body.shop_id, ps.c.valid_from == body.valid_from)
        )
        is not None
    ):
        raise AppError("payout_schedule_exists", 409, detail="shu sanada jadval allaqachon bor")
    values = body.model_dump()
    row_id = await ctx.conn.scalar(
        insert(ps).values(org_id=ctx.org_id, **values).returning(ps.c.id)
    )
    await ctx.audit("payout_schedule.create", "payout_schedule", row_id, after=_plain(values))
    return await _read(ctx)


@router.delete("/orgs/{org_id}/payout-schedules/{schedule_id}", response_model=SettingsOut)
async def delete_payout_schedule(schedule_id: UUID, ctx: Manager) -> SettingsOut:
    ps = m.payout_schedules
    row = (await ctx.conn.execute(select(ps).where(ps.c.id == schedule_id))).first()
    if row is None:
        raise AppError("payout_schedule_not_found", 404)
    await ctx.conn.execute(delete(ps).where(ps.c.id == schedule_id))
    await ctx.audit(
        "payout_schedule.delete",
        "payout_schedule",
        schedule_id,
        before=_plain({"shop_id": row.shop_id, "kind": row.kind, "valid_from": row.valid_from}),
    )
    return await _read(ctx)


# --- Muddatlar va qamrov ----------------------------------------------------------------------


@router.put("/orgs/{org_id}/settings/inventory", response_model=SettingsOut)
async def set_inventory(body: InventorySettingsIn, ctx: Manager) -> SettingsOut:
    """Standart yetkazish muddatlari (F25; tarix yo'q bosqichda) va ABC qamrov kunlari (F27). Tozalash — ``null``."""
    lead = body.lead_days
    if lead is not None and set(lead) != set(orgsettings.STAGES):
        raise AppError(
            "bad_lead_days", 422, detail="hamma bosqich kerak: " + ", ".join(orgsettings.STAGES)
        )
    cover = body.cover_days
    if cover is not None and set(cover) != set(AbcClass.__members__):
        raise AppError("bad_cover_days", 422, detail="A, B va C kerak")
    o = m.orgs
    before = orgsettings.parse(await ctx.conn.scalar(select(o.c.settings)))
    after = orgsettings.OrgSettings(
        lead_days=dict(lead) if lead else {},
        cover_days={AbcClass(k): v for k, v in cover.items()} if cover else {},
    )
    if after != before:
        await ctx.conn.execute(
            update(o).values(settings=orgsettings.dump(after), updated_at=func.now())
        )
        await ctx.audit(
            "settings.inventory",
            "org",
            ctx.org_id,
            before=orgsettings.dump(before),
            after=orgsettings.dump(after),
        )
    return await _read(ctx)
