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
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename NOT LIKE 'procrastinate\\_%'"
        )
        return {r[0] for r in rows} - {"alembic_version"}


def _procrastinate(url: str) -> int:
    """Navbat obyektlari (0004): jadvallar, funksiyalar, turlar."""
    with psycopg.connect(url) as conn:
        return conn.execute(
            "SELECT (SELECT count(*) FROM pg_tables WHERE tablename LIKE 'procrastinate\\_%') "
            "+ (SELECT count(*) FROM pg_proc WHERE proname LIKE 'procrastinate\\_%') "
            "+ (SELECT count(*) FROM pg_type WHERE typname LIKE 'procrastinate\\_%')"
        ).fetchone()[0]


def test_normalize_url() -> None:
    assert normalize_url("postgresql://u@h/db") == "postgresql+asyncpg://u@h/db"
    assert normalize_url("postgres://u@h/db", async_driver=False) == "postgresql+psycopg://u@h/db"
    assert normalize_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"


def test_migration_roundtrip(fresh: dict[str, str]) -> None:
    from upapi.db import models as m

    assert _tables(fresh["owner"]) == set(m.metadata.tables)
    assert _procrastinate(fresh["owner"]) > 0
    dbtools.alembic(fresh["owner"], "downgrade", "base")
    assert _tables(fresh["owner"]) == set()
    assert _procrastinate(fresh["owner"]) == 0
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
        # ADR-058: BHM ma'lumotnomasi (sana bo'yicha) seed'da.
        bhm = conn.execute(
            "SELECT valid_from, amount FROM ref_amounts WHERE code = 'bhm' ORDER BY valid_from"
        ).fetchall()
        assert [(str(d), int(a)) for d, a in bhm] == [
            ("2025-08-01", 412000),
            ("2026-09-01", 440000),
        ]


def test_tax_lines_shape_check(fresh: dict[str, str]) -> None:
    """ADR-058: foizli qatorda stavka > 0 va summa yo'q; qat'iy qatorda summa yoki BHM sonidan aynan bittasi."""
    org, profile = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(fresh["admin"]) as conn:
        conn.execute("INSERT INTO orgs (id, name) VALUES (%s, 'tax-lines')", [org])
        conn.execute(
            "INSERT INTO tax_profiles (id, org_id, valid_from, regime) VALUES (%s, %s, '2026-01-01', 'turnover')",
            [profile, org],
        )
        sql = (
            "INSERT INTO tax_lines (org_id, profile_id, name, kind, rate_pct, amount, bhm_count) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )

        def add(name: str, kind: str, rate: int, amount: int | None, count: int | None) -> None:
            conn.execute(sql, [org, profile, name, kind, rate, amount, count])

        add("a", "percent", 1, None, None)
        add("b", "fixed", 0, None, 1)
        add("c", "fixed", 0, 310000, None)
        bad = [
            ("d", "percent", 0, None, None),  # stavka 0
            ("e", "percent", 101, None, None),  # stavka > 100
            ("f", "percent", 1, 5, None),  # foizli, lekin summa bor
            ("g", "fixed", 0, None, None),  # summa ham BHM ham yo'q
            ("h", "fixed", 0, 5, 1),  # ikkalasi ham bor
            ("i", "fixed", 1, 5, None),  # qat'iyda stavka
            ("j", "fixed", 0, 0, None),  # 0 summa
        ]
        for row in bad:
            with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
                add(*row)
        # Profil ichida nom takrorlanmaydi.
        with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
            add("a", "percent", 2, None, None)
        # Profil o'chsa — qatorlari ham o'chadi.
        conn.execute("DELETE FROM tax_profiles WHERE id = %s", [profile])
        assert (
            conn.execute("SELECT count(*) FROM tax_lines WHERE org_id = %s", [org]).fetchone()[0]
            == 0
        )
        conn.execute("DELETE FROM orgs WHERE id = %s", [org])
        conn.commit()


def test_seed_cli_needs_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("UP_MIGRATION_DATABASE_URL", raising=False)
    assert demo.main(["seed"]) == 2
    assert "URL" in capsys.readouterr().err


def test_seed_cli(fresh: dict[str, str], capsys: pytest.CaptureFixture[str]) -> None:
    assert demo.main(["seed", fresh["admin"]]) == 0
    assert "Demo tashkilot" in capsys.readouterr().out
