"""Tashkilotlarni ajratish (ADR-012): har tashkilot jadvalida A tashkiloti B ning qatorini o'qiy, o'zgartira,
o'chira va qo'sha olmaydi; o'z qatorini B ga ko'chira olmaydi va B ning ota qatoriga bog'lay olmaydi."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import dbtools
import psycopg
import pytest
import sqlalchemy as sa
from psycopg import errors
from upapi.db import models as m

TABLES = sorted(m.TENANT)
WRITABLE = [t for t in TABLES if t not in m.APPEND_ONLY]
KEY = {"orgs": "id"}
REFS = sorted(
    (t.name, col, parent)
    for t in m.metadata.sorted_tables
    if t.name in m.TENANT
    for col, parent in dbtools._refs(t).items()
)


@pytest.fixture
def app(db: dict[str, str], seed: dbtools.Seed) -> Iterator[psycopg.Connection]:
    """up_app ulanishi, A tashkiloti doirasida; test oxirida rollback (seed o'zgarmaydi)."""
    with psycopg.connect(db["app"]) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, true)", [str(seed.orgs[0])])
        yield conn
        conn.rollback()


def admin_count(db: dict[str, str], table: str, row_id: uuid.UUID) -> int:
    with psycopg.connect(db["admin"]) as conn:
        return conn.execute(f"SELECT count(*) FROM {table} WHERE id = %s", [row_id]).fetchone()[0]


def key(table: str) -> str:
    return KEY.get(table, "org_id")


# --- Har jadval uchun -----------------------------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_cannot_read_other_org(app: psycopg.Connection, seed: dbtools.Seed, table: str) -> None:
    a, b = seed.orgs
    assert (
        app.execute(
            f"SELECT count(*) FROM {table} WHERE id = %s", [seed.rows[b][table]]
        ).fetchone()[0]
        == 0
    )
    assert (
        app.execute(f"SELECT count(*) FROM {table} WHERE {key(table)} = %s", [b]).fetchone()[0] == 0
    )
    visible = app.execute(f"SELECT DISTINCT {key(table)} FROM {table}").fetchall()
    assert visible == [(a,)]  # o'zini ko'radi (ijobiy nazorat), boshqasini emas


@pytest.mark.parametrize("table", WRITABLE)
def test_cannot_update_other_org(
    app: psycopg.Connection, db: dict[str, str], seed: dbtools.Seed, table: str
) -> None:
    b = seed.orgs[1]
    cur = app.execute(f"UPDATE {table} SET updated_at = now() WHERE id = %s", [seed.rows[b][table]])
    assert cur.rowcount == 0
    cur = app.execute(f"UPDATE {table} SET updated_at = now() WHERE {key(table)} = %s", [b])
    assert cur.rowcount == 0


@pytest.mark.parametrize("table", [t for t in WRITABLE if t != "orgs"])
def test_cannot_move_own_row_to_other_org(
    app: psycopg.Connection, seed: dbtools.Seed, table: str
) -> None:
    a, b = seed.orgs
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        app.execute(f"UPDATE {table} SET org_id = %s WHERE id = %s", [b, seed.rows[a][table]])


@pytest.mark.parametrize("table", WRITABLE)
def test_cannot_delete_other_org(
    app: psycopg.Connection, db: dict[str, str], seed: dbtools.Seed, table: str
) -> None:
    b = seed.orgs[1]
    target = seed.rows[b][table]
    assert app.execute(f"DELETE FROM {table} WHERE id = %s", [target]).rowcount == 0
    assert app.execute(f"DELETE FROM {table} WHERE {key(table)} = %s", [b]).rowcount == 0
    app.commit()
    assert admin_count(db, table, target) == 1


@pytest.mark.parametrize("table", sorted(m.APPEND_ONLY))
def test_append_only_tables(app: psycopg.Connection, seed: dbtools.Seed, table: str) -> None:
    """Audit va hodisalar o'zgartirilmaydi va o'chirilmaydi — hatto o'z tashkilotida ham."""
    own = seed.rows[seed.orgs[0]][table]
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(f"UPDATE {table} SET updated_at = now() WHERE id = %s", [own])
    app.rollback()
    app.execute("SELECT set_config('app.org_id', %s, true)", [str(seed.orgs[0])])
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(f"DELETE FROM {table} WHERE id = %s", [own])


def _fresh(seed: dbtools.Seed, table: str, org: uuid.UUID) -> dict[str, Any]:
    """Seed qatorining nusxasi yangi id va unikal maydonlar bilan (to'qnashuv RLS xatosini yashirmasin)."""
    tbl = m.metadata.tables[table]
    values = dict(seed.values[org][table])
    values["id"] = uuid.uuid4()
    keep = _keep(tbl)
    for c in tbl.constraints:
        if isinstance(c, sa.UniqueConstraint):
            for col in c.columns:
                if col.name in values and col.name not in keep:
                    values[col.name] = _bump(values[col.name])
    for col in tbl.columns:
        if col.unique and col.name in values:
            values[col.name] = _bump(values[col.name])
    return values


def _keep(tbl: sa.Table) -> set[str]:
    return {"org_id", *dbtools._refs(tbl), *(fk.parent.name for fk in tbl.foreign_keys)}


def _natural_key_only(table: str) -> bool:
    tbl = m.metadata.tables[table]
    return any(
        isinstance(c, sa.UniqueConstraint) and {col.name for col in c.columns} <= _keep(tbl)
        for c in tbl.constraints
    )


def _bump(value: Any) -> Any:
    import datetime as dt
    import os

    if isinstance(value, bytes):
        return os.urandom(16)
    if isinstance(value, int):
        return value + 1000
    if isinstance(value, str):
        return value + "-2"
    if isinstance(value, dt.date):
        return value + dt.timedelta(days=1)
    return value


@pytest.mark.parametrize("table", [t for t in TABLES if t != "orgs"])
def test_cannot_insert_for_other_org(
    app: psycopg.Connection, seed: dbtools.Seed, table: str
) -> None:
    b = seed.orgs[1]
    with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
        dbtools.insert(app, table, _fresh(seed, table, b))


@pytest.mark.parametrize("table", [t for t in TABLES if t != "orgs"])
def test_can_insert_for_own_org(app: psycopg.Connection, seed: dbtools.Seed, table: str) -> None:
    """Ijobiy nazorat: xuddi shu qator o'z tashkilotiga qo'shiladi — demak yuqoridagi rad etish RLS'dan."""
    a = seed.orgs[0]
    if _natural_key_only(
        table
    ):  # unikal kalit faqat org + ota ustunlardan: seed qatorini (tranzaksiyada) bo'shatamiz
        app.execute(f"DELETE FROM {table} WHERE id = %s", [seed.rows[a][table]])
    dbtools.insert(app, table, _fresh(seed, table, a))


@pytest.mark.parametrize(("table", "column", "parent"), REFS)
def test_cannot_reference_other_org_parent(
    app: psycopg.Connection, seed: dbtools.Seed, table: str, column: str, parent: str
) -> None:
    """FK tekshiruvi RLS'ni chetlab o'tadi — kompozit FK (org_id, id) boshqa tashkilot ota qatorini rad etadi."""
    a, b = seed.orgs
    values = _fresh(seed, table, a)
    values[column] = seed.rows[b][parent]
    with pytest.raises(errors.ForeignKeyViolation):
        dbtools.insert(app, table, values)


# --- Umumiy ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_no_org_set_sees_nothing(db: dict[str, str], seed: dbtools.Seed, table: str) -> None:
    with psycopg.connect(db["app"]) as conn:
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        if table != "orgs":
            with pytest.raises(errors.InsufficientPrivilege):
                dbtools.insert(conn, table, _fresh(seed, table, seed.orgs[0]))


def test_set_local_does_not_leak(db: dict[str, str], seed: dbtools.Seed) -> None:
    with psycopg.connect(db["app"]) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, true)", [str(seed.orgs[0])])
        assert conn.execute("SELECT count(*) FROM shops").fetchone()[0] == 1
        conn.commit()
        assert (
            conn.execute("SELECT count(*) FROM shops").fetchone()[0] == 0
        )  # keyingi tranzaksiya — hech narsa


def test_invalid_org_setting_fails_closed(db: dict[str, str]) -> None:
    with psycopg.connect(db["app"]) as conn:
        conn.execute("SELECT set_config('app.org_id', 'emas-uuid', true)")
        with pytest.raises(errors.InvalidTextRepresentation):
            conn.execute("SELECT count(*) FROM shops")


def test_app_role_is_restricted(db: dict[str, str]) -> None:
    with psycopg.connect(db["admin"]) as conn:
        row = conn.execute(
            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = %s",
            [dbtools.APP_ROLE],
        ).fetchone()
        assert row == (False, False, False, False)
        owners = conn.execute(
            "SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
        assert owners == [(dbtools.OWNER_ROLE,)]


def test_every_table_is_classified_and_protected(db: dict[str, str]) -> None:
    """Yangi jadval RLS'siz qolib ketmasligi uchun: har jadval aniq bir sinfda va bazada himoyalangan."""
    classes = [set(m.TENANT), set(m.GLOBAL), set(m.AUTH), set(m.SPECIAL)]
    every = set(m.metadata.tables)
    assert set().union(*classes) == every
    assert sum(len(c) for c in classes) == len(every)
    with psycopg.connect(db["admin"]) as conn:
        rls = dict(
            (name, (enabled, forced))
            for name, enabled, forced in conn.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND relkind = 'r'"
            ).fetchall()
        )
        for table in [*m.TENANT, *m.AUTH, *m.SPECIAL]:
            assert rls[table] == (True, True), table
        policies = {r[0] for r in conn.execute("SELECT tablename FROM pg_policies").fetchall()}
        assert set(m.TENANT) | set(m.SPECIAL) <= policies
        assert not policies & set(m.AUTH)

        def priv(table: str, p: str) -> bool:
            return conn.execute(
                "SELECT has_table_privilege(%s, %s, %s)", [dbtools.APP_ROLE, table, p]
            ).fetchone()[0]

        for table in every:
            for p in ("TRUNCATE", "REFERENCES", "TRIGGER"):
                assert not priv(table, p), (table, p)
        for table in m.TENANT:
            assert priv(table, "SELECT") and priv(table, "INSERT")
            assert priv(table, "UPDATE") == priv(table, "DELETE") == (table not in m.APPEND_ONLY), (
                table
            )
        for table in m.GLOBAL:
            assert priv(table, "SELECT") and not any(
                priv(table, p) for p in ("INSERT", "UPDATE", "DELETE")
            )
        for table in m.AUTH:
            assert not any(priv(table, p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE")), table


@pytest.mark.parametrize("table", sorted(m.TENANT))
def test_truncate_denied(app: psycopg.Connection, table: str) -> None:
    """TRUNCATE RLS'ga bo'ysunmaydi — ilova roliga umuman berilmagan."""
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(f"TRUNCATE {table} CASCADE")


@pytest.mark.parametrize("table", m.GLOBAL)
def test_global_tables_read_only(app: psycopg.Connection, table: str) -> None:
    assert app.execute(f"SELECT count(*) FROM {table}").fetchone()[0] >= 1
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(f"DELETE FROM {table}")


@pytest.mark.parametrize("table", m.AUTH)
def test_auth_tables_inaccessible(app: psycopg.Connection, table: str) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        app.execute(f"SELECT count(*) FROM {table}")


def test_users_visibility(db: dict[str, str], seed: dbtools.Seed) -> None:
    a, b = seed.orgs
    ua, ub = seed.users[a], seed.users[b]
    with psycopg.connect(db["app"]) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, true)", [str(a)])
        assert conn.execute("SELECT id FROM users").fetchall() == [
            (ua,)
        ]  # faqat o'z tashkiloti a'zosi
        assert (
            conn.execute("UPDATE users SET name = 'x' WHERE id = %s", [ua]).rowcount == 0
        )  # app.user_id yo'q
        conn.execute("SELECT set_config('app.user_id', %s, true)", [str(ua)])
        assert conn.execute("UPDATE users SET name = 'x' WHERE id = %s", [ua]).rowcount == 1
        assert conn.execute("UPDATE users SET name = 'x' WHERE id = %s", [ub]).rowcount == 0
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("INSERT INTO users (phone) VALUES ('+998901111111')")
        conn.rollback()
        conn.execute("SELECT set_config('app.user_id', %s, true)", [str(ub)])
        assert conn.execute("SELECT id FROM users").fetchall() == [
            (ub,)
        ]  # tashkilotsiz — faqat o'zi
