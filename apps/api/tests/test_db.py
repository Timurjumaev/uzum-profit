"""Migratsiya (upgrade → downgrade → upgrade, model ↔ migratsiya mosligi), ``org_transaction`` va seed."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date

import dbtools
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from upapi.db import seed as demo
from upapi.db.session import make_engine, org_transaction
from upapi.db.url import normalize_url


@pytest.fixture(scope="module")
def fresh() -> Iterator[dict[str, str]]:
    """RLS testlarining umumiy bazasiga tegmaslik uchun alohida baza."""
    with dbtools.migrated_database() as urls:
        yield urls


def _tables(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {r[0] for r in rows} - {"alembic_version"}


def test_normalize_url() -> None:
    assert normalize_url("postgresql://u@h/db") == "postgresql+asyncpg://u@h/db"
    assert normalize_url("postgres://u@h/db", async_driver=False) == "postgresql+psycopg://u@h/db"
    assert normalize_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"


def test_migration_roundtrip(fresh: dict[str, str]) -> None:
    from upapi.db import models as m

    assert _tables(fresh["owner"]) == set(m.metadata.tables)
    dbtools.alembic(fresh["owner"], "downgrade", "base")
    assert _tables(fresh["owner"]) == set()
    with psycopg.connect(fresh["owner"]) as conn:
        assert conn.execute(
            "SELECT count(*) FROM pg_proc WHERE proname LIKE 'app_current_%'"
        ).fetchone() == (0,)
    dbtools.alembic(fresh["owner"], "upgrade", "head")
    assert _tables(fresh["owner"]) == set(m.metadata.tables)


def test_models_match_migration(fresh: dict[str, str]) -> None:
    """Autogenerate farq topmasligi kerak: modelni o'zgartirib, migratsiya yozishni unutish CI'da ushlanadi."""
    cfg = Config(str(dbtools.ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(dbtools.ROOT / "migrations"))
    cfg.cmd_opts = type(
        "Opts", (), {"x": [f"url={normalize_url(fresh['owner'], async_driver=False)}"]}
    )()
    command.check(cfg)


def test_seed_and_org_transaction(fresh: dict[str, str]) -> None:
    today = date(2026, 10, 24)
    assert asyncio.run(demo.run(fresh["admin"], today=today)) is True
    assert asyncio.run(demo.run(fresh["admin"], today=today)) is False  # takror — o'zgarishsiz

    async def check() -> None:
        engine = make_engine(fresh["app"], pool_size=1, max_overflow=0)
        try:
            async with org_transaction(engine, demo.DEMO_ORG, demo.DEMO_USER) as conn:
                assert (await conn.exec_driver_sql("SELECT count(*) FROM shops")).scalar() == 2
                assert (await conn.exec_driver_sql("SELECT count(*) FROM sale_items")).scalar() > 50
                assert (await conn.exec_driver_sql("SELECT count(*) FROM users")).scalar() == 1
                user = (await conn.exec_driver_sql("SELECT app_current_user()")).scalar()
                assert user == demo.DEMO_USER
            async with org_transaction(engine, uuid.uuid4()) as conn:
                assert (await conn.exec_driver_sql("SELECT count(*) FROM shops")).scalar() == 0
                assert (await conn.exec_driver_sql("SELECT app_current_user()")).scalar() is None
            # Xuddi shu (yagona) pool ulanishi: tranzaksiyadan keyin sozlama qolmaydi.
            async with engine.connect() as conn:
                assert (await conn.exec_driver_sql("SELECT count(*) FROM shops")).scalar() == 0
        finally:
            await engine.dispose()

    asyncio.run(check())
    with psycopg.connect(fresh["admin"]) as conn:
        assert conn.execute("SELECT count(*) FROM expense_codes").fetchone()[0] >= 16
        assert (
            conn.execute("SELECT rate_pct FROM ref_tax_rates WHERE code = 'vat'").fetchone()[0]
            == 12
        )


def test_seed_cli_needs_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("UP_MIGRATION_DATABASE_URL", raising=False)
    assert demo.main(["seed"]) == 2
    assert "URL" in capsys.readouterr().err


def test_seed_cli(fresh: dict[str, str], capsys: pytest.CaptureFixture[str]) -> None:
    assert demo.main(["seed", fresh["admin"]]) == 0
    assert "Demo tashkilot" in capsys.readouterr().out
