"""Alembic muhiti: URL ``UP_DATABASE_URL`` (yoki ``-x url=...``) dan, sync va async drayverlar."""

import asyncio
import os

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlalchemy.ext.asyncio import create_async_engine
from upapi.db.models import metadata
from upapi.db.url import normalize_url

config = context.config
target_metadata = metadata


def _url() -> str:
    raw = context.get_x_argument(as_dictionary=True).get("url") or os.environ.get("UP_DATABASE_URL")
    if not raw:
        raise RuntimeError("UP_DATABASE_URL berilmagan")
    return normalize_url(raw)  # drayver ko'rsatilmagan bo'lsa asyncpg


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async(url: str) -> None:
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


def run_online() -> None:
    url = _url()
    if "+asyncpg" in url:
        asyncio.run(_run_async(url))
        return
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
