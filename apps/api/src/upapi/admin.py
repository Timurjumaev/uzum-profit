"""Admin ko'rinishi (B8.3a): ``python -m upapi.admin overview`` — faqat o'qish.

Tashkilotlar ro'yxati: nomi, a'zolar va faol do'konlar soni, akkaunt holati, oxirgi muvaffaqiyatli sinxron, ketma-ket
xatolar va oxirgi xato (200 belgigacha). Sotuvchi biznes ma'lumoti yo'q. Ma'lumotni ``admin_overview()`` (egasi —
``up_admin``, ustun darajasida SELECT; migratsiya 0047) beradi — funksiya ilova roliga berilmagan, shuning uchun CLI
**migratsiya egasi** ulanishi bilan ishlaydi: ``UP_ADMIN_DATABASE_URL`` (yoki ``UP_MIGRATION_DATABASE_URL``). Ruxsat ro'yxati
(taklif kodlari o'rnida, B8.11) — ``python -m upapi.signup list``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import TextIO

from sqlalchemy import text

from upapi.db.session import make_engine


class AdminError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (stderr, chiqish kodi 1)."""


def admin_url() -> str:
    url = os.environ.get("UP_ADMIN_DATABASE_URL") or os.environ.get("UP_MIGRATION_DATABASE_URL")
    if not url:
        raise AdminError(
            "UP_ADMIN_DATABASE_URL (yoki UP_MIGRATION_DATABASE_URL) berilmagan — migratsiya egasi ulanishi kerak"
        )
    return url


async def overview(url: str, out: TextIO) -> int:
    engine = make_engine(url)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT * FROM admin_overview()"))).all()
    finally:
        await engine.dispose()
    out.write(f"Tashkilotlar: {len(rows)}\n")
    for r in rows:
        ok = f"{r.last_success_at:%Y-%m-%d %H:%M}" if r.last_success_at else "hali yo'q"
        line = (
            f"{r.created_at:%Y-%m-%d}  {r.name}  a'zo={r.members} do'kon={r.shops}  "
            f"akkaunt={r.account_status or '—'}  sinxron={ok}  xato={r.sync_failures}"
        )
        if r.auth_failures:
            line += f"  kalit-xato={r.auth_failures}"
        if r.paused_until:
            line += f"  pauza={r.paused_until:%Y-%m-%d %H:%M}"
        out.write(line + "\n")
        if r.last_error:
            out.write(f"    oxirgi xato: {r.last_error}\n")
    return len(rows)


FUNNEL = (
    "org_created",
    "mp_account_connected",
    "history_loaded",
    "first_cost",
    "costs_60",
    "telegram_linked",
)


async def funnel(url: str, out: TextIO) -> int:
    """B8.9/B9.4: har tashkilot bo'yicha aktivatsiya bosqichlarining birinchi vaqti (jadval) va kunlik kirishlar soni."""
    engine = make_engine(url)
    try:
        async with engine.connect() as conn:
            names = {
                r.org_id: r.name
                for r in await conn.execute(text("SELECT org_id, name FROM admin_overview()"))
            }
            rows = (await conn.execute(text("SELECT * FROM admin_funnel()"))).all()
    finally:
        await engine.dispose()
    per: dict[object, dict[str, tuple[object, int]]] = {}
    for r in rows:
        per.setdefault(r.org_id, {})[r.name] = (r.first_at, r.times)
    out.write("tashkilot\t" + "\t".join(FUNNEL) + "\tkirishlar\n")
    for org_id, steps in per.items():
        cells = [f"{steps[s][0]:%Y-%m-%d %H:%M}" if s in steps else "—" for s in FUNNEL]
        visits = steps["daily_visit"][1] if "daily_visit" in steps else 0
        out.write(f"{names.get(org_id, str(org_id))}\t" + "\t".join(cells) + f"\t{visits}\n")
    return len(per)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m upapi.admin", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("overview", help="tashkilotlar va sinxron holati (faqat o'qish)")
    sub.add_parser("funnel", help="aktivatsiya voronkasi: bosqichlarning birinchi vaqti (B9.4)")
    args = parser.parse_args(argv)
    try:
        if args.command == "funnel":
            asyncio.run(funnel(admin_url(), sys.stdout))
        else:
            asyncio.run(overview(admin_url(), sys.stdout))
    except AdminError as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
