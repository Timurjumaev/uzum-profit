"""``/accounts``, ``/shops``: marketplace kalitini ulash, tekshirish, almashtirish, uzish; do'konlarni tanlash
(M2 1–2-qadam, B2.4). Ruxsat: kalit — faqat egasi (03 §10); do'konlar ro'yxati — har a'zo.

Kalit faqat shifrlangan holda saqlanadi (:mod:`upapi.crypto`) va API javobida, logda, xato matnida, audit
jurnalida bo'lmaydi — faqat oxirgi 4 belgisi (``key_hint``). Uzum'ga so'rov paytida DB tranzaksiyasi ochiq
turmaydi: ruxsat qisqa tranzaksiyada tekshiriladi, keyin tekshiruv, keyin yozish — yana ruxsat bilan.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy import Row, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.auth.deps import (
    CurrentUser,
    OrgContext,
    current_user,
    get_engine,
    get_settings,
    open_org,
    org_context,
    require,
)
from upapi.auth.permissions import Permission
from upapi.crypto import CipherError, TokenCipher, account_aad
from upapi.db import models as m
from upapi.errors import AppError
from upapi.logs import get_logger
from upapi.settings import Settings
from upapi.uzum.client import (
    NO_RETRY,
    AuthError,
    BurstLimited,
    QuotaExhausted,
    UpstreamError,
    UzumClient,
    UzumError,
    UzumShop,
    WafBlocked,
    normalize_token,
)
from upapi.uzum.limiter import Priority

router = APIRouter(tags=["accounts"])
log = get_logger("upapi.accounts")

User = Annotated[CurrentUser, Depends(current_user)]
Engine = Annotated[AsyncEngine, Depends(get_engine)]
Config = Annotated[Settings, Depends(get_settings)]
Member = Annotated[OrgContext, Depends(org_context, scope="function")]
Owner = Annotated[OrgContext, Depends(require(Permission.MANAGE_ACCOUNTS))]

MANAGE = Permission.MANAGE_ACCOUNTS
PROVIDER = "uzum"


def get_cipher(request: Request) -> TokenCipher:
    cipher: TokenCipher = request.app.state.cipher
    return cipher


Cipher = Annotated[TokenCipher, Depends(get_cipher)]


class TokenIn(BaseModel):
    """Uzum seller kabinetidagi API kalit. Javobda va xatoda qaytarilmaydi."""

    token: SecretStr

    @field_validator("token")
    @classmethod
    def _clean(cls, value: SecretStr) -> SecretStr:
        token = normalize_token(value.get_secret_value())
        # Xato matnida qiymat yo'q (validatsiya javobi ``input`` ni ham chiqarmaydi — errors.py).
        if not 8 <= len(token) <= 1024 or any(c.isspace() or not c.isprintable() for c in token):
            raise ValueError("kalit formati noto'g'ri")
        return SecretStr(token)


class ShopOut(BaseModel):
    id: UUID
    account_id: UUID
    external_id: int
    name: str
    alias: str | None
    color: str | None
    active: bool
    history_status: str | None
    first_sale_on: date | None


class ShopUpdate(BaseModel):
    active: bool | None = None
    alias: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class AccountOut(BaseModel):
    id: UUID
    provider: str
    status: str
    key_hint: str | None  # "…abcd" — faqat oxirgi 4 belgi; uzilgan akkauntda None
    checked_at: datetime | None
    quota_remaining: int | None
    created_at: datetime
    shops: list[ShopOut]


# --- Yordamchilar --------------------------------------------------------------------------------

_MP_ERRORS: dict[type[UzumError], tuple[str, int]] = {
    AuthError: ("mp_token_invalid", 422),
    WafBlocked: ("mp_waf_blocked", 503),
    BurstLimited: ("mp_rate_limited", 503),
    QuotaExhausted: ("mp_quota_exhausted", 503),
    UpstreamError: ("mp_unavailable", 502),
}
# Tekshiruvda akkaunt holatini o'zgartiradigan xatolar; qolganlari (tarmoq, sekundlik limit) — vaqtinchalik.
_STATUS_ON_ERROR: dict[type[UzumError], str] = {
    AuthError: "invalid",
    WafBlocked: "waf_blocked",
    QuotaExhausted: "quota_exhausted",
}


def _mp_error(exc: UzumError) -> AppError:
    code, status_code = _MP_ERRORS.get(type(exc), ("mp_unexpected_response", 502))
    return AppError(code, status_code)


def _hint(last4: str | None) -> str | None:
    return f"…{last4}" if last4 else None


async def _verify(
    request: Request, settings: Settings, token: SecretStr, account_id: UUID | None = None
) -> tuple[list[UzumShop], int | None]:
    """Kalitni Uzum'da tekshirish (``/v1/shops``). Xato — :class:`UzumError` (matnida kalit va javob tanasi yo'q).

    Foydalanuvchi kutib turibdi: ustuvor navbat, qayta urinishsiz (natija darhol; kerak bo'lsa qayta bosadi)."""
    transport: httpx.AsyncBaseTransport | None = request.app.state.uzum_transport
    async with UzumClient(
        token,
        base_url=settings.uzum_base_url,
        timeout=settings.uzum_timeout_seconds,
        transport=transport,
        limiter=request.app.state.uzum_limiter if account_id else None,
        key_id=str(account_id or ""),
        priority=Priority.USER,
        retry=NO_RETRY,
    ) as uzum:
        try:
            shops = await uzum.shops()
        except UzumError as exc:
            log.warning("mp_verify_failed", error_code=exc.kind, http_status=exc.status)
            raise
        return shops, uzum.quota_remaining


async def _check_failures(engine: AsyncEngine, org_id: UUID, user: CurrentUser, limit: int) -> None:
    """Yaroqsiz kalit urinishlari cheklovi: serverimiz kalit tanlash (brute force) vositasiga aylanmasin."""
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        failures = await ctx.conn.scalar(
            select(func.count())
            .select_from(m.audit_log)
            .where(
                m.audit_log.c.action == "account.verify_failed",
                m.audit_log.c.created_at > func.now() - text("interval '1 hour'"),
            )
        )
    if (failures or 0) >= limit:
        raise AppError(
            "mp_verify_limited", 429, detail="Juda ko'p urinish, bir soatdan keyin qayta urining"
        )


async def _verify_or_fail(
    request: Request,
    engine: AsyncEngine,
    settings: Settings,
    org_id: UUID,
    user: CurrentUser,
    token: SecretStr,
    account_id: UUID | None = None,
) -> tuple[list[UzumShop], int | None]:
    await _check_failures(engine, org_id, user, settings.mp_verify_failures_per_hour)
    try:
        shops, quota = await _verify(request, settings, token)
    except AuthError:
        async with open_org(engine, org_id, user, MANAGE) as ctx:
            await ctx.audit(
                "account.verify_failed", "mp_account", account_id, after={"error_code": "auth"}
            )
        raise AppError("mp_token_invalid", 422) from None
    except UzumError as exc:
        raise _mp_error(exc) from None
    if not shops:
        raise AppError("mp_no_shops", 422, detail="Kalitga birorta ham do'kon biriktirilmagan")
    return shops, quota


async def _account_row(conn: AsyncConnection, account_id: UUID) -> Row[Any]:
    row = (
        await conn.execute(select(m.mp_accounts).where(m.mp_accounts.c.id == account_id))
    ).first()
    if row is None:
        raise AppError("account_not_found", 404)
    return row


async def _shops(conn: AsyncConnection, account_id: UUID | None = None) -> list[ShopOut]:
    query = select(m.shops).order_by(m.shops.c.created_at, m.shops.c.external_id)
    if account_id is not None:
        query = query.where(m.shops.c.account_id == account_id)
    return [ShopOut.model_validate(r._asdict()) for r in await conn.execute(query)]


async def _account_out(conn: AsyncConnection, row: Row[Any]) -> AccountOut:
    return AccountOut(
        id=row.id,
        provider=row.provider,
        status=row.status,
        key_hint=_hint(row.token_last4),
        checked_at=row.checked_at,
        quota_remaining=row.quota_remaining,
        created_at=row.created_at,
        shops=await _shops(conn, row.id),
    )


async def _taken_elsewhere(conn: AsyncConnection, account_id: UUID, shops: list[UzumShop]) -> bool:
    """Shu tashkilotda bu do'konlardan biri boshqa akkauntga ulanganmi (bitta do'kon ikki marta sinxron bo'lmasin)."""
    return bool(
        await conn.scalar(
            select(func.count())
            .select_from(m.shops)
            .where(
                m.shops.c.account_id != account_id,
                m.shops.c.external_id.in_([s.external_id for s in shops]),
            )
        )
    )


async def _upsert_shops(
    conn: AsyncConnection, org_id: UUID, account_id: UUID, shops: list[UzumShop]
) -> None:
    """Uzum bergan do'konlar: yangisi faol holda qo'shiladi (M2: hammasi belgilangan), borining nomi yangilanadi.
    Sotuvchi kiritgani (taxallus, rang, faollik) o'zgarmaydi; Uzum ro'yxatidan yo'qolgan do'kon o'chirilmaydi."""
    stmt = pg_insert(m.shops).values(
        [
            {
                "org_id": org_id,
                "account_id": account_id,
                "external_id": s.external_id,
                "name": s.name,
            }
            for s in shops
        ]
    )
    await conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["org_id", "account_id", "external_id"],
            set_={"name": stmt.excluded.name, "updated_at": func.now()},
        )
    )


def _token_values(
    cipher: TokenCipher, org_id: UUID, account_id: UUID, token: SecretStr
) -> dict[str, object]:
    blob, version = cipher.encrypt(token, account_aad(org_id, account_id))
    return {
        "token_encrypted": blob,
        "key_version": version,
        "token_last4": token.get_secret_value()[-4:],
    }


# --- Akkauntlar ----------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/accounts", response_model=list[AccountOut])
async def list_accounts(ctx: Owner) -> list[AccountOut]:
    rows = await ctx.conn.execute(select(m.mp_accounts).order_by(m.mp_accounts.c.created_at))
    return [await _account_out(ctx.conn, r) for r in rows.all()]


@router.post(
    "/orgs/{org_id}/accounts", status_code=status.HTTP_201_CREATED, response_model=AccountOut
)
async def connect_account(
    org_id: UUID,
    body: TokenIn,
    request: Request,
    user: User,
    engine: Engine,
    settings: Config,
    cipher: Cipher,
) -> AccountOut:
    """Kalitni ulash: Uzum'da tekshiriladi (``/v1/shops``), shifrlab saqlanadi, do'konlar faol holda qo'shiladi."""
    shops, quota = await _verify_or_fail(request, engine, settings, org_id, user, body.token)
    account_id = uuid4()
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        if await _taken_elsewhere(ctx.conn, account_id, shops):
            raise AppError(
                "mp_shops_already_connected",
                409,
                detail="Bu do'konlar allaqachon ulangan — kalitni almashtirish uchun PUT /accounts/{id}/token",
            )
        await ctx.conn.execute(
            insert(m.mp_accounts).values(
                id=account_id,
                org_id=org_id,
                provider=PROVIDER,
                status="active",
                quota_remaining=quota,
                checked_at=func.now(),
                **_token_values(cipher, org_id, account_id, body.token),
            )
        )
        await _upsert_shops(ctx.conn, org_id, account_id, shops)
        row = await _account_row(ctx.conn, account_id)
        await ctx.audit(
            "account.connect",
            "mp_account",
            account_id,
            after={
                "provider": PROVIDER,
                "key_hint": _hint(row.token_last4),
                "shops": [s.external_id for s in shops],
            },
        )
        await ctx.conn.execute(
            insert(m.events).values(
                org_id=org_id,
                user_id=user.user_id,
                name="mp_account_connected",
                props={"shops": len(shops)},
            )
        )
        return await _account_out(ctx.conn, row)


@router.post("/orgs/{org_id}/accounts/{account_id}/check", response_model=AccountOut)
async def check_account(
    org_id: UUID,
    account_id: UUID,
    request: Request,
    user: User,
    engine: Engine,
    settings: Config,
    cipher: Cipher,
) -> AccountOut:
    """Saqlangan kalitni qayta tekshirish: holat (faol / yaroqsiz / kvota / WAF), yangi do'konlar, nomlar.
    Eski versiyali shifr shu yerda joriy kalit bilan qayta shifrlanadi (rotatsiya)."""
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        row = await _account_row(ctx.conn, account_id)
        if row.token_encrypted is None:
            raise AppError("account_disconnected", 409, detail="Kalit uzilgan — yangisini kiriting")
        try:
            token = cipher.decrypt(
                row.token_encrypted, row.key_version, account_aad(org_id, account_id)
            )
        except CipherError as exc:
            log.error(
                "mp_token_unreadable",
                account_id=str(account_id),
                error_code="cipher",
                reason=str(exc),
            )
            raise AppError("mp_token_unreadable", 409, detail="Kalitni qayta kiriting") from None
    try:
        shops, quota = await _verify(request, settings, token, account_id)
        new_status, error = "active", None
    except UzumError as exc:
        if type(exc) not in _STATUS_ON_ERROR:
            raise _mp_error(exc) from None
        shops, quota, new_status, error = [], exc.quota_remaining, _STATUS_ON_ERROR[type(exc)], exc
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        row = await _account_row(ctx.conn, account_id)
        values: dict[str, object] = {
            "status": new_status,
            "checked_at": func.now(),
            "updated_at": func.now(),
        }
        if quota is not None:
            values["quota_remaining"] = quota
        if row.token_encrypted is not None and cipher.needs_rotation(row.key_version):
            values.update(_token_values(cipher, org_id, account_id, token))
        if row.token_encrypted is not None:  # parallel uzilgan bo'lsa — holat o'zgarmaydi
            await ctx.conn.execute(
                update(m.mp_accounts).where(m.mp_accounts.c.id == account_id).values(**values)
            )
        if shops:
            await _upsert_shops(ctx.conn, org_id, account_id, shops)
        if row.status != new_status:
            await ctx.audit(
                "account.check",
                "mp_account",
                account_id,
                before={"status": row.status},
                after={"status": new_status, "error_code": error.kind if error else None},
            )
        return await _account_out(ctx.conn, await _account_row(ctx.conn, account_id))


@router.put("/orgs/{org_id}/accounts/{account_id}/token", response_model=AccountOut)
async def replace_token(
    org_id: UUID,
    account_id: UUID,
    body: TokenIn,
    request: Request,
    user: User,
    engine: Engine,
    settings: Config,
    cipher: Cipher,
) -> AccountOut:
    """Kalitni almashtirish (Uzum'da yangisi yaratilgan) yoki uzilgan akkauntni qayta ulash. Yangi kalit shu
    sotuvchiniki bo'lishi shart: do'konlaridan kamida bittasi akkauntdagi do'konlar bilan mos kelishi kerak."""
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        await _account_row(ctx.conn, account_id)
    shops, quota = await _verify_or_fail(
        request, engine, settings, org_id, user, body.token, account_id
    )
    async with open_org(engine, org_id, user, MANAGE) as ctx:
        row = await _account_row(ctx.conn, account_id)
        known = {s.external_id for s in await _shops(ctx.conn, account_id)}
        if known and not known & {s.external_id for s in shops}:
            raise AppError(
                "mp_account_mismatch", 409, detail="Yangi kalit boshqa sotuvchiga tegishli"
            )
        if await _taken_elsewhere(ctx.conn, account_id, shops):
            raise AppError("mp_shops_already_connected", 409)
        await ctx.conn.execute(
            update(m.mp_accounts)
            .where(m.mp_accounts.c.id == account_id)
            .values(
                status="active",
                quota_remaining=quota,
                checked_at=func.now(),
                updated_at=func.now(),
                **_token_values(cipher, org_id, account_id, body.token),
            )
        )
        await _upsert_shops(ctx.conn, org_id, account_id, shops)
        fresh = await _account_row(ctx.conn, account_id)
        await ctx.audit(
            "account.token_replace",
            "mp_account",
            account_id,
            before={"status": row.status, "key_hint": _hint(row.token_last4)},
            after={"status": "active", "key_hint": _hint(fresh.token_last4)},
        )
        return await _account_out(ctx.conn, fresh)


@router.delete("/orgs/{org_id}/accounts/{account_id}/token", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_account(account_id: UUID, ctx: Owner) -> None:
    """Kalitni uzish: shifrlangan kalit bazadan o'chiriladi, sinxron to'xtaydi. Do'konlar va ma'lumotlar qoladi
    (03 tamoyil 7); qayta ulash — ``PUT .../token``."""
    row = await _account_row(ctx.conn, account_id)
    if row.token_encrypted is None:
        return
    await ctx.conn.execute(
        update(m.mp_accounts)
        .where(m.mp_accounts.c.id == account_id)
        .values(
            status="disconnected",
            token_encrypted=None,
            key_version=None,
            token_last4=None,
            quota_remaining=None,
            updated_at=func.now(),
        )
    )
    await ctx.audit(
        "account.disconnect",
        "mp_account",
        account_id,
        before={"status": row.status, "key_hint": _hint(row.token_last4)},
    )


# --- Do'konlar -----------------------------------------------------------------------------------


@router.get("/orgs/{org_id}/shops", response_model=list[ShopOut])
async def list_shops(ctx: Member) -> list[ShopOut]:
    return await _shops(ctx.conn)


@router.patch("/orgs/{org_id}/shops/{shop_id}", response_model=ShopOut)
async def update_shop(shop_id: UUID, body: ShopUpdate, ctx: Owner) -> ShopOut:
    """Do'konni tanlash (sinxronga kiradimi), qisqa nom va rang belgisi (M2 2-qadam)."""
    values = body.model_dump(exclude_unset=True)
    if values.get("active", False) is None:
        del values["active"]  # faollik NULL bo'lmaydi; taxallus va rang NULL bilan tozalanadi
    row = (await ctx.conn.execute(select(m.shops).where(m.shops.c.id == shop_id))).first()
    if row is None:
        raise AppError("shop_not_found", 404)
    if values:
        before = {k: getattr(row, k) for k in values}
        await ctx.conn.execute(
            update(m.shops).where(m.shops.c.id == shop_id).values(**values, updated_at=func.now())
        )
        await ctx.audit("shop.update", "shop", shop_id, before=before, after=values)
        row = (await ctx.conn.execute(select(m.shops).where(m.shops.c.id == shop_id))).one()
    return ShopOut.model_validate(row._asdict())
