"""``/auth``: telefon + bir martalik kod bilan kirish, sessiyalar ("qurilmalarim"), profil (M1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.auth.deps import (
    CurrentUser,
    clear_session_cookie,
    current_user,
    get_engine,
    get_settings,
    set_session_cookie,
)
from upapi.auth.senders import CodeSender, DeliveryError
from upapi.auth.tokens import (
    InvalidPhone,
    code_hash,
    new_code,
    new_token,
    normalize_phone,
    token_hash,
)
from upapi.db import models as m
from upapi.db.session import org_transaction
from upapi.errors import AppError
from upapi.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])

Engine = Annotated[AsyncEngine, Depends(get_engine)]
Config = Annotated[Settings, Depends(get_settings)]
User = Annotated[CurrentUser, Depends(current_user)]


class OtpRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=32, examples=["+998901234567"])


class OtpSent(BaseModel):
    phone: str
    expires_in: int


class LoginRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=32)
    code: str = Field(pattern=r"^\d{6}$")


class OrgSummary(BaseModel):
    id: UUID
    name: str
    role: str


class UserOut(BaseModel):
    id: UUID
    phone: str
    name: str | None
    language: str


class Me(BaseModel):
    user: UserOut
    orgs: list[OrgSummary]


class LoginResult(Me):
    created: bool


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    language: str | None = Field(default=None, pattern=r"^(uz-Latn|uz-Cyrl|ru)$")


class SessionOut(BaseModel):
    id: UUID
    device: str | None
    created_at: datetime
    rotated_at: datetime
    expires_at: datetime
    current: bool


class Revoked(BaseModel):
    revoked: int


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except InvalidPhone:
        raise AppError("invalid_phone", 422, detail="Telefon raqami noto'g'ri") from None


def _sender(request: Request) -> CodeSender:
    sender: CodeSender = request.app.state.sender
    return sender


async def user_orgs(conn: AsyncConnection, digest: bytes) -> list[OrgSummary]:
    rows = await conn.execute(text("SELECT * FROM auth_user_orgs(:t)"), {"t": digest})
    return [OrgSummary(id=r.org_id, name=r.name, role=r.role) for r in rows]


@router.post("/otp", status_code=status.HTTP_202_ACCEPTED, response_model=OtpSent)
async def request_code(
    body: OtpRequest, request: Request, engine: Engine, settings: Config
) -> OtpSent:
    """Kirish kodini Telegram'ga yuborish. Raqam bo'yicha soatiga ``otp_per_hour`` ta; 5 xato → 15 daqiqa blok."""
    phone = _phone(body.phone)
    code = new_code()
    async with engine.begin() as conn:
        result = await conn.scalar(
            text("SELECT auth_otp_issue(:p, :h, :ttl, :hour, :max, :block)"),
            {
                "p": phone,
                "h": code_hash(settings.otp_secret.get_secret_value(), phone, code),
                "ttl": settings.otp_ttl_seconds,
                "hour": settings.otp_per_hour,
                "max": settings.otp_max_attempts,
                "block": settings.otp_block_minutes,
            },
        )
    if result == "blocked":
        raise AppError("otp_blocked", 429)
    if result == "rate_limited":
        raise AppError("otp_rate_limited", 429)
    try:
        await _sender(request).send(phone, code, settings.otp_ttl_seconds)
    except DeliveryError as exc:
        if exc.not_on_telegram:
            raise AppError("telegram_not_found", 400) from None
        raise AppError("otp_delivery_failed", 502) from None
    return OtpSent(phone=phone, expires_in=settings.otp_ttl_seconds)


_LOGIN_ERRORS = {
    "blocked": ("otp_blocked", 429),
    "expired": ("otp_expired", 400),
    "invalid": ("otp_invalid", 400),
}


@router.post("/login", response_model=LoginResult)
async def login(
    body: LoginRequest, request: Request, response: Response, engine: Engine, settings: Config
) -> LoginResult:
    phone = _phone(body.phone)
    token = new_token()
    device = (request.headers.get("user-agent") or "")[:200] or None
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT * FROM auth_login(:p, :h, :t, :d, :secs, :max, :block)"),
                {
                    "p": phone,
                    "h": code_hash(settings.otp_secret.get_secret_value(), phone, body.code),
                    "t": token_hash(token),
                    "d": device,
                    "secs": settings.session_days * 86400,
                    "max": settings.otp_max_attempts,
                    "block": settings.otp_block_minutes,
                },
            )
        ).one()
        if row.status != "ok":
            # Xato urinish bazada sanaladi — tranzaksiya commit bo'lishi kerak, xato undan keyin.
            error = _LOGIN_ERRORS[row.status]
        else:
            error = None
            me = (
                await conn.execute(text("SELECT * FROM auth_session(:t)"), {"t": token_hash(token)})
            ).one()
            orgs = await user_orgs(conn, token_hash(token))
    if error:
        raise AppError(*error)
    set_session_cookie(response, token, settings)
    return LoginResult(
        user=UserOut(id=me.user_id, phone=me.phone, name=me.name, language=me.language),
        orgs=orgs,
        created=row.created,
    )


@router.get("/me", response_model=Me)
async def me(user: User, engine: Engine) -> Me:
    async with engine.begin() as conn:
        orgs = await user_orgs(conn, user.token_hash)
    return Me(
        user=UserOut(id=user.user_id, phone=user.phone, name=user.name, language=user.language),
        orgs=orgs,
    )


@router.patch("/me", response_model=UserOut)
async def update_profile(body: ProfileUpdate, user: User, engine: Engine) -> UserOut:
    values = body.model_dump(exclude_none=True)
    if values:
        async with org_transaction(engine, None, user.user_id) as conn:
            await conn.execute(update(m.users).where(m.users.c.id == user.user_id).values(**values))
    return UserOut(
        id=user.user_id,
        phone=user.phone,
        name=values.get("name", user.name),
        language=values.get("language", user.language),
    )


async def _revoke(
    engine: AsyncEngine, user: CurrentUser, scope: str, session: UUID | None = None
) -> int:
    async with engine.begin() as conn:
        count = await conn.scalar(
            text("SELECT auth_session_revoke(:t, :scope, :sid)"),
            {"t": user.token_hash, "scope": scope, "sid": session},
        )
    return int(count or 0)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User, engine: Engine, settings: Config, response: Response) -> None:
    await _revoke(engine, user, "current")
    clear_session_cookie(response, settings)


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(user: User, engine: Engine) -> list[SessionOut]:
    """ "Qurilmalarim"."""
    async with engine.begin() as conn:
        rows = await conn.execute(text("SELECT * FROM auth_sessions(:t)"), {"t": user.token_hash})
        return [
            SessionOut(
                id=r.id,
                device=r.device,
                created_at=r.created_at,
                rotated_at=r.rotated_at,
                expires_at=r.expires_at,
                current=r.is_current,
            )
            for r in rows
        ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: UUID, user: User, engine: Engine) -> None:
    if not await _revoke(engine, user, "one", session_id):
        raise AppError("session_not_found", 404)


@router.post("/sessions/revoke-others", response_model=Revoked)
async def revoke_others(user: User, engine: Engine) -> Revoked:
    """ "Hamma qurilmalardan chiqish" (joriy qurilma qoladi)."""
    return Revoked(revoked=await _revoke(engine, user, "others"))
