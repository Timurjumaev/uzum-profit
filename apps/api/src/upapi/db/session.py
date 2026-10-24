"""Ulanish va tashkilot tranzaksiyasi (ADR-012).

Har so'rov o'z tranzaksiyasida ``app.org_id`` (va ``app.user_id``) ni ``set_config(..., true)`` bilan o'rnatadi —
bu ``SET LOCAL``: tranzaksiya tugashi bilan o'chadi va pooldagi boshqa so'rovga o'tmaydi.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from upapi.db.url import normalize_url

_SET = text("SELECT set_config('app.org_id', :org, true), set_config('app.user_id', :user, true)")


def make_engine(url: str, **kwargs: object) -> AsyncEngine:
    return create_async_engine(normalize_url(url), pool_pre_ping=True, **kwargs)


@asynccontextmanager
async def org_transaction(
    engine: AsyncEngine, org_id: UUID | None, user_id: UUID | None = None
) -> AsyncIterator[AsyncConnection]:
    """Tashkilot doirasidagi tranzaksiya: ichidagi hamma so'rovlar faqat shu tashkilot qatorlarini ko'radi.

    ``org_id=None`` — faqat foydalanuvchi o'zi (masalan, profilini o'zgartirish)."""
    async with engine.begin() as conn:
        await conn.execute(
            _SET, {"org": str(org_id) if org_id else "", "user": str(user_id) if user_id else ""}
        )
        yield conn
