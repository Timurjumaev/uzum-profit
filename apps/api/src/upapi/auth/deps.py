"""FastAPI bog'liqliklari: joriy foydalanuvchi (sessiya cookie), tashkilot konteksti va ruxsat tekshiruvi."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request, Response
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.auth.permissions import Permission, Role, allowed
from upapi.auth.tokens import new_token, token_hash
from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.errors import AppError
from upapi.settings import Settings

COOKIE = "up_session"


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE, httponly=True, secure=settings.secure_cookies, samesite="lax", path="/"
    )


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UUID
    session_id: UUID
    phone: str
    name: str | None
    language: str
    token_hash: bytes


async def current_user(
    request: Request,
    response: Response,
    engine: Annotated[AsyncEngine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """Sessiya cookie → foydalanuvchi. Token har ``session_rotate_hours`` da yangilanadi (eski token
    ``session_grace_seconds`` davomida ishlaydi — parallel so'rovlar chiqib ketmaydi)."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise AppError("unauthenticated", 401)
    digest = token_hash(token)
    async with engine.begin() as conn:
        row = (await conn.execute(text("SELECT * FROM auth_session(:t)"), {"t": digest})).first()
        if row is None:
            raise AppError("unauthenticated", 401)
        due = datetime.now(UTC) - timedelta(hours=settings.session_rotate_hours)
        if row.is_current and row.rotated_at < due:
            fresh = new_token()
            rotated = await conn.scalar(
                text("SELECT auth_session_rotate(:old, :new, :secs, :grace)"),
                {
                    "old": digest,
                    "new": token_hash(fresh),
                    "secs": settings.session_days * 86400,
                    "grace": settings.session_grace_seconds,
                },
            )
            if rotated:
                set_session_cookie(response, fresh, settings)
                digest = token_hash(fresh)
    return CurrentUser(row.user_id, row.session_id, row.phone, row.name, row.language, digest)


@dataclass(frozen=True, slots=True)
class OrgContext:
    """Tashkilot doirasidagi so'rov: ``conn`` — ``app.org_id`` o'rnatilgan tranzaksiya (RLS)."""

    org_id: UUID
    user: CurrentUser
    role: Role
    conn: AsyncConnection

    async def audit(
        self,
        action: str,
        entity: str,
        entity_id: UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        """Audit jurnali (M1): kim, qachon, nimani o'zgartirdi. Faqat qo'shiladi (RLS + huquqlar)."""
        await self.conn.execute(
            insert(m.audit_log).values(
                org_id=self.org_id,
                actor_user_id=self.user.user_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                before=before,
                after=after,
            )
        )


async def org_context(
    org_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncIterator[OrgContext]:
    """A'zo bo'lmagan (yoki o'chirilgan) tashkilot — 404: borligi ham bilinmaydi.

    Har doim ``Depends(org_context, scope="function")`` bilan: tranzaksiya javob yuborilishidan **oldin** commit
    bo'ladi (standart "request" doirasida commit javobdan keyin — xato mijozga bilinmay qolardi)."""
    async with org_transaction(engine, org_id, user.user_id) as conn:
        role = await conn.scalar(
            text(
                "SELECT m.role FROM memberships m JOIN orgs o ON o.id = m.org_id "
                "WHERE m.user_id = :u AND o.deleted_at IS NULL"
            ),
            {"u": user.user_id},
        )
        if role is None:
            raise AppError("org_not_found", 404)
        yield OrgContext(org_id, user, Role(role), conn)


def require(permission: Permission) -> Callable[..., Coroutine[Any, Any, OrgContext]]:
    """``ctx: OrgContext = Depends(require(Permission.VIEW_FINANCE))`` — rol ruxsati server tomonda."""

    async def dependency(
        ctx: Annotated[OrgContext, Depends(org_context, scope="function")],
    ) -> OrgContext:
        if not allowed(ctx.role, permission):
            raise AppError("forbidden", 403, detail=permission.value)
        return ctx

    return dependency
