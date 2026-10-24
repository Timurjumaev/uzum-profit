"""``/orgs``: tashkilot, xodimlar, takliflar, audit jurnali (M1). Ruxsatlar — 03-arxitektura.md §10."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from upapi.auth.deps import (
    CurrentUser,
    OrgContext,
    current_user,
    get_engine,
    get_settings,
    org_context,
    require,
)
from upapi.auth.permissions import MATRIX, Permission, Role
from upapi.auth.tokens import InvalidPhone, mask_phone, new_token, normalize_phone, token_hash
from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.errors import AppError
from upapi.routes.auth import OrgSummary, user_orgs
from upapi.settings import Settings

router = APIRouter(tags=["orgs"])

User = Annotated[CurrentUser, Depends(current_user)]
Engine = Annotated[AsyncEngine, Depends(get_engine)]
Config = Annotated[Settings, Depends(get_settings)]
Member = Annotated[OrgContext, Depends(org_context, scope="function")]
Members = Annotated[OrgContext, Depends(require(Permission.MANAGE_MEMBERS))]
SettingsAdmin = Annotated[OrgContext, Depends(require(Permission.MANAGE_SETTINGS))]
Auditor = Annotated[OrgContext, Depends(require(Permission.VIEW_AUDIT))]


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    inn: str | None = Field(default=None, pattern=r"^\d{9}$")


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    inn: str | None = Field(default=None, pattern=r"^\d{9}$")
    language: str | None = Field(default=None, pattern=r"^(uz-Latn|uz-Cyrl|ru)$")
    timezone: str | None = Field(default=None, max_length=64)


class OrgOut(BaseModel):
    id: UUID
    name: str
    inn: str | None
    language: str
    timezone: str
    cost_method: str
    role: Role
    permissions: list[Permission]


class MemberOut(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    role: Role
    joined_at: datetime


class RoleChange(BaseModel):
    role: Role


class InviteCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=32)
    role: Role


class InviteOut(BaseModel):
    id: UUID
    phone: str
    role: Role
    expires_at: datetime


class InviteCreated(InviteOut):
    url: str  # token faqat shu javobda; bazada xeshi


class InviteAccept(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class AuditOut(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    action: str
    entity: str
    entity_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


async def _org_out(ctx: OrgContext) -> OrgOut:
    row = (await ctx.conn.execute(select(m.orgs).where(m.orgs.c.id == ctx.org_id))).one()
    return OrgOut(
        id=row.id,
        name=row.name,
        inn=row.inn,
        language=row.language,
        timezone=row.timezone,
        cost_method=row.cost_method,
        role=ctx.role,
        permissions=sorted(MATRIX[ctx.role]),
    )


@router.post("/orgs", status_code=status.HTTP_201_CREATED, response_model=OrgOut)
async def create_org(body: OrgCreate, user: User, engine: Engine) -> OrgOut:
    """Yangi tashkilot; yaratgan foydalanuvchi — egasi."""
    org_id = uuid4()
    async with org_transaction(engine, org_id, user.user_id) as conn:
        await conn.execute(insert(m.orgs).values(id=org_id, name=body.name, inn=body.inn))
        await conn.execute(
            insert(m.memberships).values(org_id=org_id, user_id=user.user_id, role=Role.OWNER)
        )
        ctx = OrgContext(org_id, user, Role.OWNER, conn)
        await ctx.audit("org.create", "org", org_id, after=body.model_dump(exclude_none=True))
        return await _org_out(ctx)


@router.get("/orgs", response_model=list[OrgSummary])
async def list_orgs(user: User, engine: Engine) -> list[OrgSummary]:
    async with engine.begin() as conn:
        return await user_orgs(conn, user.token_hash)


@router.get("/orgs/{org_id}", response_model=OrgOut)
async def get_org(ctx: Member) -> OrgOut:
    return await _org_out(ctx)


@router.patch("/orgs/{org_id}", response_model=OrgOut)
async def update_org(body: OrgUpdate, ctx: SettingsAdmin) -> OrgOut:
    values = body.model_dump(exclude_none=True)
    if values:
        before = (
            (
                await ctx.conn.execute(
                    select(*(m.orgs.c[k] for k in values)).where(m.orgs.c.id == ctx.org_id)
                )
            )
            .one()
            ._asdict()
        )
        await ctx.conn.execute(update(m.orgs).where(m.orgs.c.id == ctx.org_id).values(**values))
        await ctx.audit("org.update", "org", ctx.org_id, before=before, after=values)
    return await _org_out(ctx)


# --- Xodimlar ------------------------------------------------------------------------------------


async def _owners(ctx: OrgContext) -> int:
    return int(
        await ctx.conn.scalar(
            select(func.count())
            .select_from(m.memberships)
            .where(m.memberships.c.role == Role.OWNER)
        )
        or 0
    )


async def _member_role(ctx: OrgContext, user_id: UUID) -> Role:
    role = await ctx.conn.scalar(
        select(m.memberships.c.role).where(m.memberships.c.user_id == user_id)
    )
    if role is None:
        raise AppError("member_not_found", 404)
    return Role(role)


@router.get("/orgs/{org_id}/members", response_model=list[MemberOut])
async def list_members(ctx: Members) -> list[MemberOut]:
    rows = await ctx.conn.execute(
        select(
            m.memberships.c.user_id,
            m.users.c.phone,
            m.users.c.name,
            m.memberships.c.role,
            m.memberships.c.created_at,
        )
        .join(m.users, m.users.c.id == m.memberships.c.user_id)
        .order_by(m.memberships.c.created_at)
    )
    return [
        MemberOut(user_id=r[0], phone=r[1], name=r[2], role=Role(r[3]), joined_at=r[4])
        for r in rows
    ]


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=MemberOut)
async def change_role(user_id: UUID, body: RoleChange, ctx: Members) -> MemberOut:
    old = await _member_role(ctx, user_id)
    if old is Role.OWNER and body.role is not Role.OWNER and await _owners(ctx) == 1:
        raise AppError("last_owner", 409, detail="Tashkilotda kamida bitta egasi qolishi kerak")
    await ctx.conn.execute(
        update(m.memberships)
        .where(m.memberships.c.user_id == user_id)
        .values(role=body.role, updated_at=func.now())
    )
    await ctx.audit(
        "member.role", "membership", user_id, before={"role": old}, after={"role": body.role}
    )
    return next(r for r in await list_members(ctx) if r.user_id == user_id)


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(user_id: UUID, ctx: Members) -> None:
    old = await _member_role(ctx, user_id)
    if old is Role.OWNER and await _owners(ctx) == 1:
        raise AppError("last_owner", 409, detail="Tashkilotda kamida bitta egasi qolishi kerak")
    await ctx.conn.execute(delete(m.memberships).where(m.memberships.c.user_id == user_id))
    await ctx.audit("member.remove", "membership", user_id, before={"role": old})


# --- Takliflar -----------------------------------------------------------------------------------


@router.post(
    "/orgs/{org_id}/invites", status_code=status.HTTP_201_CREATED, response_model=InviteCreated
)
async def create_invite(body: InviteCreate, ctx: Members, settings: Config) -> InviteCreated:
    """Telefon raqam bo'yicha taklif havolasi (``invite_days`` kun). Faqat shu raqamli foydalanuvchi qabul qiladi."""
    try:
        phone = normalize_phone(body.phone)
    except InvalidPhone:
        raise AppError("invalid_phone", 422) from None
    token = new_token()
    expires = datetime.now(UTC) + timedelta(days=settings.invite_days)
    invite_id = await ctx.conn.scalar(
        insert(m.invites)
        .values(
            org_id=ctx.org_id,
            phone=phone,
            role=body.role,
            token_hash=token_hash(token),
            invited_by=ctx.user.user_id,
            expires_at=expires,
        )
        .returning(m.invites.c.id)
    )
    await ctx.audit(
        "invite.create", "invite", invite_id, after={"phone": mask_phone(phone), "role": body.role}
    )
    return InviteCreated(
        id=invite_id,
        phone=phone,
        role=body.role,
        expires_at=expires,
        url=f"{settings.web_url.rstrip('/')}/invite/{token}",
    )


_PENDING = and_(m.invites.c.accepted_at.is_(None), m.invites.c.expires_at > func.now())


@router.get("/orgs/{org_id}/invites", response_model=list[InviteOut])
async def list_invites(ctx: Members) -> list[InviteOut]:
    rows = await ctx.conn.execute(
        select(m.invites.c.id, m.invites.c.phone, m.invites.c.role, m.invites.c.expires_at)
        .where(_PENDING)
        .order_by(m.invites.c.created_at)
    )
    return [InviteOut(id=r[0], phone=r[1], role=Role(r[2]), expires_at=r[3]) for r in rows]


@router.delete("/orgs/{org_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: UUID, ctx: Members) -> None:
    result = await ctx.conn.execute(delete(m.invites).where(m.invites.c.id == invite_id, _PENDING))
    if not result.rowcount:
        raise AppError("invite_not_found", 404)
    await ctx.audit("invite.revoke", "invite", invite_id)


_ACCEPT_ERRORS = {
    "not_found": ("invite_not_found", 404),
    "used": ("invite_used", 409),
    "expired": ("invite_expired", 410),
    "phone_mismatch": ("invite_phone_mismatch", 403),
    "unauthenticated": ("unauthenticated", 401),
}


@router.post("/invites/accept", response_model=OrgOut)
async def accept_invite(body: InviteAccept, user: User, engine: Engine) -> OrgOut:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT * FROM auth_invite_accept(:t, :i)"),
                {"t": user.token_hash, "i": token_hash(body.token)},
            )
        ).one()
    if row.status != "ok":
        raise AppError(*_ACCEPT_ERRORS[row.status])
    async with org_transaction(engine, row.org_id, user.user_id) as conn:
        ctx = OrgContext(row.org_id, user, Role(row.role), conn)
        await ctx.audit("member.join", "membership", user.user_id, after={"role": row.role})
        return await _org_out(ctx)


# --- Audit ---------------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/audit", response_model=list[AuditOut])
async def audit_log(ctx: Auditor, limit: int = Query(default=50, ge=1, le=200)) -> list[AuditOut]:
    rows = await ctx.conn.execute(
        select(m.audit_log).order_by(m.audit_log.c.created_at.desc(), m.audit_log.c.id).limit(limit)
    )
    return [AuditOut.model_validate(r._asdict()) for r in rows]
