"""Test bazasi: vaqtinchalik DB, rollar, migratsiya va ikki tashkilotli sintetik ma'lumot.

``UP_TEST_ADMIN_URL`` (superuser, masalan ``postgresql://postgres@localhost:5432/postgres``) bo'lmasa DB testlari
o'tkazib yuboriladi; CI'da PostgreSQL servisi bilan doim ishlaydi.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
from alembic import command
from alembic.config import Config
from psycopg.types.json import Jsonb
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Integer,
    LargeBinary,
    Numeric,
    Table,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from upapi.db import models as m

ADMIN_URL = os.environ.get("UP_TEST_ADMIN_URL")
APP_ROLE, OWNER_ROLE = "up_app", "up_owner"
ROOT = Path(__file__).resolve().parents[1]


def require_admin() -> None:
    """DB yo'q bo'lsa lokalda o'tkazib yuboriladi, CI'da esa xato — RLS testlari jimgina tushib qolmasin."""
    if not ADMIN_URL:
        if os.environ.get("CI"):
            raise RuntimeError("CI'da UP_TEST_ADMIN_URL majburiy (PostgreSQL servisi)")
        import pytest

        pytest.skip("UP_TEST_ADMIN_URL berilmagan")


def with_db(url: str, db: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    netloc = f"{user or parts.username}:{password}@" if password else f"{user or parts.username}@"
    netloc += f"{host}:{parts.port or 5432}"
    return urlunsplit(("postgresql", netloc, f"/{db}", "", ""))


def plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


def ensure_roles(admin: psycopg.Connection) -> None:
    for role, extra in ((OWNER_ROLE, "CREATEDB"), (APP_ROLE, "")):
        exists = admin.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role]).fetchone()
        if not exists:
            admin.execute(
                f"CREATE ROLE {role} LOGIN PASSWORD '{role}' NOSUPERUSER NOBYPASSRLS {extra}"
            )


def create_database(name: str) -> dict[str, str]:
    assert ADMIN_URL
    with psycopg.connect(plain(ADMIN_URL), autocommit=True) as admin:
        ensure_roles(admin)
        admin.execute(f"CREATE DATABASE {name} OWNER {OWNER_ROLE}")
    urls = {
        "admin": with_db(plain(ADMIN_URL), name),
        "owner": with_db(plain(ADMIN_URL), name, OWNER_ROLE, OWNER_ROLE),
        "app": with_db(plain(ADMIN_URL), name, APP_ROLE, APP_ROLE),
    }
    return urls


def drop_database(name: str) -> None:
    assert ADMIN_URL
    with psycopg.connect(plain(ADMIN_URL), autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def alembic(url: str, action: str, target: str) -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.cmd_opts = type(
        "Opts", (), {"x": [f"url={url.replace('postgresql://', 'postgresql+psycopg://')}"]}
    )()
    getattr(command, action)(cfg, target)


# --- Sintetik qatorlar --------------------------------------------------------------------------


def _allowed(table: Table) -> dict[str, str]:
    out = {}
    for c in table.constraints:
        if isinstance(c, CheckConstraint):
            match = re.match(r"(\w+) IN \('([^']+)'", str(c.sqltext))
            if match:
                out[match.group(1)] = match.group(2)
    return out


def _refs(table: Table) -> dict[str, str]:
    """Kompozit FK: ustun → ota jadval."""
    out = {}
    for fk in table.foreign_key_constraints:
        cols = [c.name for c in fk.columns]
        if len(cols) == 2 and cols[0] == "org_id":
            out[cols[1]] = fk.referred_table.name
    return out


def _value(table: Table, col: Any, allowed: dict[str, str]) -> Any:
    if col.name in allowed:
        return allowed[col.name]
    t = col.type
    if isinstance(t, UUID):
        return uuid.uuid4()
    if isinstance(t, (Integer, BigInteger)):
        return 1
    if isinstance(t, Numeric):
        return 0
    if isinstance(t, TIMESTAMP):
        return datetime.now(UTC)
    if isinstance(t, Date):
        return date(2026, 10, 1)
    if isinstance(t, Time):
        return "22:00"
    if isinstance(t, Boolean):
        return True
    if isinstance(t, JSONB):
        return Jsonb({})
    if isinstance(t, LargeBinary):
        return os.urandom(16)
    if isinstance(t, ARRAY):
        return []
    if isinstance(t, Text):
        return f"{table.name}-{col.name}"
    raise TypeError(f"{table.name}.{col.name}: {t!r}")


SKIP = {"id", "org_id", "created_at", "updated_at"}


def row_values(
    table: Table, org: uuid.UUID, parents: dict[str, uuid.UUID], globals_: dict[str, Any]
) -> dict[str, Any]:
    """Jadval uchun to'liq qator: majburiy ustunlar, hamma kompozit FK — shu tashkilot ota qatorlari."""
    allowed, refs = _allowed(table), _refs(table)
    values: dict[str, Any] = {"id": uuid.uuid4(), "org_id": org}
    for col in table.columns:
        if col.name in SKIP:
            continue
        if col.name in refs:
            values[col.name] = parents[refs[col.name]]
        elif col.name == "user_id" or col.name in ("actor_user_id", "invited_by"):
            values[col.name] = globals_["user"][org]
        elif col.name == "plan_id":
            values[col.name] = globals_["plan"]
        elif not col.nullable and col.server_default is None:
            values[col.name] = _value(table, col, allowed)
    return values


def insert(conn: psycopg.Connection, table: str, values: dict[str, Any]) -> None:
    cols = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))


@dataclass
class Seed:
    orgs: list[uuid.UUID]
    users: dict[uuid.UUID, uuid.UUID]
    rows: dict[uuid.UUID, dict[str, uuid.UUID]] = field(default_factory=dict)
    values: dict[uuid.UUID, dict[str, dict[str, Any]]] = field(default_factory=dict)
    plan: uuid.UUID | None = None


def seed_two_orgs(admin_url: str) -> Seed:
    """Superuser bilan (RLS chetlab) ikki tashkilot: har tashkilot jadvalida bittadan qator."""
    orgs = [uuid.uuid4(), uuid.uuid4()]
    users = {org: uuid.uuid4() for org in orgs}
    plan = uuid.uuid4()
    seed = Seed(orgs, users, plan=plan)
    globals_ = {"user": users, "plan": plan}
    with psycopg.connect(admin_url) as conn:
        insert(conn, "plans", {"id": plan, "code": "free", "name": "Bepul", "price_uzs": 0})
        insert(conn, "expense_codes", {"code": "C000003", "category": "storage"})
        insert(
            conn,
            "fx_rates",
            {"day": date(2026, 10, 1), "currency": "USD", "source": "cbu", "rate": 12650},
        )
        insert(
            conn, "ref_tax_rates", {"code": "vat", "valid_from": date(2026, 1, 1), "rate_pct": 12}
        )
        insert(conn, "ref_logistics_tariffs", {"valid_from": date(2026, 6, 1), "rules": Jsonb({})})
        for i, org in enumerate(orgs):
            insert(conn, "orgs", {"id": org, "name": f"Org {i}"})
            insert(conn, "users", {"id": users[org], "phone": f"+99890000000{i}"})
            seed.rows[org] = {"orgs": org}
            seed.values[org] = {}
            for table in m.metadata.sorted_tables:
                if table.name not in m.TENANT or table.name == "orgs":
                    continue
                values = row_values(table, org, seed.rows[org], globals_)
                insert(conn, table.name, values)
                seed.rows[org][table.name] = values["id"]
                seed.values[org][table.name] = values
        conn.commit()
    return seed
