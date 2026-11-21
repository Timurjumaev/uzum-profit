"""Ro'yxatdan o'tish ruxsat ro'yxati (B8.11): ``python -m upapi.signup allow|list|remove``.

``UP_SIGNUP_OPEN=false`` bo'lganda yangi telefon raqami kirish kodini faqat shu ro'yxatda bo'lsa (yoki biror tashkilot
uni a'zo sifatida taklif qilgan bo'lsa) oladi; mavjud foydalanuvchilar doim kiradi. Ochiq ro'yxat — B8-B da yoqiladi.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TextIO

from sqlalchemy import text

from upapi.auth.tokens import InvalidPhone, normalize_phone
from upapi.db.session import make_engine
from upapi.settings import Settings, get_settings


class SignupError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (stderr, chiqish kodi 1)."""


def _phone(value: str) -> str:
    try:
        return normalize_phone(value)
    except InvalidPhone as exc:
        raise SignupError("telefon raqami noto'g'ri") from exc


async def allow(settings: Settings, phones: list[str], out: TextIO) -> None:
    numbers = [_phone(p) for p in phones]
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            for number in numbers:
                await conn.execute(text("SELECT auth_signup_allow(:p, 'admin')"), {"p": number})
    finally:
        await engine.dispose()
    out.write(f"Ruxsat berildi: {len(numbers)} ta raqam\n")


async def list_allowed(settings: Settings, out: TextIO) -> None:
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(text("SELECT * FROM auth_signup_list()"))).all()
    finally:
        await engine.dispose()
    for r in rows:
        out.write(f"{r.phone}\t{r.source}\t{r.created_at:%Y-%m-%d}\n")
    if not rows:
        out.write("Ro'yxat bo'sh\n")


async def remove(settings: Settings, phone: str, out: TextIO) -> None:
    number = _phone(phone)
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            count = await conn.scalar(text("SELECT auth_signup_remove(:p)"), {"p": number})
    finally:
        await engine.dispose()
    out.write("O'chirildi\n" if count else "Ro'yxatda yo'q edi\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m upapi.signup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("allow", help="raqam(lar)ga ro'yxatdan o'tishga ruxsat")
    a.add_argument("phones", nargs="+", help="+998XXXXXXXXX")
    sub.add_parser("list", help="ruxsat ro'yxati")
    r = sub.add_parser("remove", help="raqamni ro'yxatdan olib tashlash")
    r.add_argument("phone")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "allow":
            asyncio.run(allow(settings, args.phones, sys.stdout))
        elif args.command == "list":
            asyncio.run(list_allowed(settings, sys.stdout))
        else:
            asyncio.run(remove(settings, args.phone, sys.stdout))
    except SignupError as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
