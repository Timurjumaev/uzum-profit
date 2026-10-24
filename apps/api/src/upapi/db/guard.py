"""Ilova DB roli tekshiruvi (ADR-012; B2.10 chiqish mezoni).

RLS faqat ilova roli cheklangan bo'lsa ishlaydi. Superuser, ``BYPASSRLS``, jadval egasi yoki boshqa rol a'zosi
(``SET ROLE`` bilan cheklovdan chiqish mumkin) bo'lgan rol bilan ulanilsa — staging/prod'da ilova ishga tushmaydi,
dev'da ogohlantirish yoziladi.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_CHECK = text(
    """
    SELECT r.rolname, r.rolsuper, r.rolbypassrls,
      (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm') AND c.relowner = r.oid) AS owned,
      ARRAY(SELECT g.rolname FROM pg_roles g WHERE g.oid <> r.oid AND pg_has_role(r.oid, g.oid, 'MEMBER')
            ORDER BY g.rolname) AS member_of
    FROM pg_roles r WHERE r.rolname = current_user
    """
)


async def role_problems(engine: AsyncEngine) -> list[str]:
    """Bo'sh ro'yxat — rol xavfsiz (RLS'ga bo'ysunadi)."""
    async with engine.connect() as conn:
        row = (await conn.execute(_CHECK)).one()
    name, superuser, bypass, owned, member_of = row
    out = []
    if superuser:
        out.append(f"{name}: superuser (RLS ishlamaydi)")
    if bypass:
        out.append(f"{name}: BYPASSRLS")
    if owned:
        out.append(f"{name}: {owned} ta jadval egasi (egasi RLS'ni o'chira oladi)")
    if member_of:
        out.append(
            f"{name}: boshqa rollar a'zosi ({', '.join(member_of)}) — SET ROLE bilan chetlab o'tadi"
        )
    return out


async def _check(url: str) -> list[str]:
    from upapi.db.session import make_engine

    engine = make_engine(url)
    try:
        return await role_problems(engine)
    finally:
        await engine.dispose()


def main(argv: list[str]) -> int:
    """``python -m upapi.db.guard [URL]`` — ilova ulanishi xavfsizmi (CI va deploy uchun). 0 — ha, 1 — yo'q."""
    url = argv[1] if len(argv) > 1 else os.environ.get("UP_DATABASE_URL", "")
    problems = asyncio.run(_check(url))
    for problem in problems:
        print(f"XAVFLI: {problem}", file=sys.stderr)
    if not problems:
        print("DB roli xavfsiz: RLS'ga bo'ysunadi.")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
