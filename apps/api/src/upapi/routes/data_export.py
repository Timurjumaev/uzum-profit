"""``/exports/full``: to'liq eksport (B7.5, ADR-065) — faqat egasi (``export_all``). Tartib: so'rov → fon ishi ZIP yig'adi
(``upapi.export_full``) → bildirishnoma "tayyor" → egasi bir martalik havola oladi (24 soat) → yuklab oladi.

Kuniga bir marta (oxirgi 24 soatda muvaffaqiyatsiz bo'lmagan so'rov bo'lsa — 429). Havola tokeni bazada faqat xesh sifatida,
bir marta ishlaydi; yuklash ham seans (cookie) talab qiladi. Har qadam audit jurnaliga yoziladi. Dev-token faqat o'qiydi,
shuning uchun havola (POST) ola olmaydi.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, update

from upapi.auth.deps import OrgContext, require
from upapi.auth.permissions import Permission
from upapi.db import models as m
from upapi.errors import AppError
from upapi.logs import get_logger

_log = get_logger("upapi.routes.data_export")
router = APIRouter(tags=["exports"])
Owner = Annotated[OrgContext, Depends(require(Permission.EXPORT_ALL))]
LIMIT = 3  # ro'yxatda ko'rsatiladigan oxirgi so'rovlar


class FullExportOut(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    expires_at: datetime | None
    size_bytes: int | None
    tables: dict[str, int] | None
    error: str | None
    downloaded: bool


class FullExportLink(BaseModel):
    url: str
    expires_at: datetime


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _out(row: Any, now: datetime) -> FullExportOut:
    status = row.status
    if status == "ready" and row.expires_at is not None and row.expires_at <= now:
        status = "expired"
    return FullExportOut(
        id=row.id,
        status=status,
        created_at=row.created_at,
        expires_at=row.expires_at,
        size_bytes=row.size_bytes,
        tables=row.tables,
        error=row.error,
        downloaded=bool(row.token_used),
    )


_COLS = (
    "id",
    "status",
    "created_at",
    "expires_at",
    "size_bytes",
    "tables",
    "error",
    "token_used",
)


async def _kick(request: Request, org_id: UUID, export_id: UUID) -> None:
    try:
        await request.app.state.jobs.defer_export(org_id, export_id)
    except Exception as exc:
        _log.warning("export_defer_failed", org_id=str(org_id), error_code=type(exc).__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/orgs/{org_id}/exports/full", response_model=list[FullExportOut])
async def list_full(ctx: Owner) -> list[FullExportOut]:
    t = m.data_exports
    rows = (
        await ctx.conn.execute(
            select(*[t.c[c] for c in _COLS]).order_by(t.c.created_at.desc()).limit(LIMIT)
        )
    ).all()
    now = _now()
    return [_out(r, now) for r in rows]


@router.post("/orgs/{org_id}/exports/full", response_model=FullExportOut, status_code=202)
async def request_full(ctx: Owner, request: Request, background: BackgroundTasks) -> FullExportOut:
    t = m.data_exports
    now = _now()
    recent = await ctx.conn.scalar(
        select(t.c.id).where(t.c.status != "failed", t.c.created_at > now - timedelta(days=1))
    )
    if recent is not None:
        raise AppError("export_limit", 429, detail="to'liq eksport kuniga bir marta")
    row = (
        await ctx.conn.execute(
            t.insert()
            .values(org_id=ctx.org_id, user_id=ctx.user.user_id, status="pending")
            .returning(*[t.c[c] for c in _COLS])
        )
    ).one()
    await ctx.audit("export.full.request", "data_export", row.id)
    # Navbatga — tranzaksiya commit bo'lgach (ishchi qatorni ko'rishi uchun).
    background.add_task(_kick, request, ctx.org_id, row.id)
    return _out(row, now)


@router.post("/orgs/{org_id}/exports/full/{export_id}/link", response_model=FullExportLink)
async def link(export_id: UUID, ctx: Owner) -> FullExportLink:
    """Bir martalik yuklash havolasi (har chaqiruv oldingisini bekor qiladi)."""
    t = m.data_exports
    now = _now()
    row = (
        await ctx.conn.execute(select(t.c.status, t.c.expires_at).where(t.c.id == export_id))
    ).first()
    if row is None:
        raise AppError("export_not_found", 404, detail="eksport topilmadi")
    if row.status != "ready" or row.expires_at is None or row.expires_at <= now:
        raise AppError("export_not_ready", 409, detail="eksport tayyor emas yoki muddati tugagan")
    token = secrets.token_urlsafe(32)
    await ctx.conn.execute(
        update(t).where(t.c.id == export_id).values(token_hash=_digest(token), token_used=False)
    )
    await ctx.audit("export.full.link", "data_export", export_id)
    return FullExportLink(
        url=f"/api/v1/orgs/{ctx.org_id}/exports/full/{export_id}/download?token={token}",
        expires_at=row.expires_at,
    )


@router.get("/orgs/{org_id}/exports/full/{export_id}/download")
async def download(
    export_id: UUID, ctx: Owner, token: Annotated[str, Query(min_length=20, max_length=200)]
) -> Response:
    t = m.data_exports
    now = _now()
    row = (
        await ctx.conn.execute(
            select(t.c.status, t.c.expires_at, t.c.token_hash, t.c.token_used).where(
                t.c.id == export_id
            )
        )
    ).first()
    if row is None:
        raise AppError("export_not_found", 404, detail="eksport topilmadi")
    if row.status != "ready" or row.expires_at is None or row.expires_at <= now:
        raise AppError("export_expired", 410, detail="havola muddati tugagan")
    if (
        row.token_hash is None
        or row.token_used
        or not hmac.compare_digest(row.token_hash, _digest(token))
    ):
        raise AppError("export_token_invalid", 403, detail="havola yaroqsiz yoki ishlatilgan")
    # Bir martalik: faqat birinchi so'rov o'tadi (poyga holatida ikkinchisi 0 qator oladi).
    taken = await ctx.conn.execute(
        update(t)
        .where(t.c.id == export_id, t.c.token_used.is_(False))
        .values(token_used=True)
        .returning(t.c.content)
    )
    content = taken.scalar()
    if content is None:
        raise AppError("export_token_invalid", 403, detail="havola yaroqsiz yoki ishlatilgan")
    await ctx.audit("export.full.download", "data_export", export_id)
    return Response(
        bytes(content),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="sellermax-{now:%Y%m%d}.zip"',
            "Cache-Control": "no-store",
        },
    )
