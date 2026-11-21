"""Dev-token boshqaruvi (ADR-072): ``python -m upapi.devtokens create|list|revoke`` (staging serverda,
``infra/staging/devtoken.sh`` orqali).

**Vaqtinchalik ishlab chiqish vositasi, faqat staging.** Token — ``Authorization: Bearer`` bilan faqat o'qish
(GET) uchun; bazada faqat SHA-256 xesh; muddatli va bekor qilinadi. Yaratilgan token **bir marta** stdout'ga chiqadi.
``UP_DEV_TOKENS_ENABLED`` yoqilmagan bo'lsa (production'da doim) CLI ishlamaydi.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from typing import TextIO
from uuid import UUID

from sqlalchemy import text

from upapi.auth.tokens import InvalidPhone, new_token, normalize_phone, token_hash
from upapi.db.session import make_engine
from upapi.settings import Environment, Settings, get_settings

PREFIX = "dvt_"  # token turi ko'rinib tursin (maxfiy skanerlar va loglar uchun)
DEFAULT_DAYS = 90
LABEL_MAX = 80


class DevTokenError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xato (stderr, chiqish kodi 1)."""


def _guard(settings: Settings) -> None:
    if settings.env is Environment.PROD:
        raise DevTokenError("production'da dev-token taqiqlangan (ADR-072)")
    if not settings.dev_tokens_enabled:
        raise DevTokenError("UP_DEV_TOKENS_ENABLED yoqilmagan (faqat staging'da yoqiladi)")


async def create(settings: Settings, phone: str, label: str, days: int, out: TextIO) -> None:
    _guard(settings)
    if not 1 <= days <= settings.dev_token_max_days:
        raise DevTokenError(f"muddat 1..{settings.dev_token_max_days} kun bo'lishi kerak")
    label = label.strip()[:LABEL_MAX]
    if not label:
        raise DevTokenError("--label bo'sh bo'lmasligi kerak")
    try:
        number = normalize_phone(phone)
    except InvalidPhone as exc:
        raise DevTokenError("telefon raqami noto'g'ri") from exc
    token = PREFIX + new_token()
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            token_id = await conn.scalar(
                text("SELECT auth_dev_token_create(:p, :h, :l, :s)"),
                {
                    "p": number,
                    "h": token_hash(token),
                    "l": label,
                    "s": int(timedelta(days=days).total_seconds()),
                },
            )
    finally:
        await engine.dispose()
    if token_id is None:
        raise DevTokenError(
            "bu telefon raqamli foydalanuvchi yo'q — avval staging'ga bir marta kiring"
        )
    print(f"Token id: {token_id}\nMuddati: {days} kun\nLabel: {label}", file=sys.stderr)
    print("Token faqat hozir ko'rsatiladi — saqlab qo'ying; chatga yozmang.", file=sys.stderr)
    out.write(token + "\n")


async def list_tokens(settings: Settings, out: TextIO) -> None:
    _guard(settings)
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(text("SELECT * FROM auth_dev_token_list()"))).all()
    finally:
        await engine.dispose()
    for r in rows:
        state = "bekor" if r.revoked_at else "yaroqli"
        used = r.last_used_at.isoformat(timespec="minutes") if r.last_used_at else "—"
        out.write(
            f"{r.id}  {state:8}  tugaydi {r.expires_at.date()}  oxirgi ishlatilgan {used}  {r.label}\n"
        )
    if not rows:
        out.write("Token yo'q.\n")


async def revoke(settings: Settings, token_id: UUID | None, out: TextIO) -> None:
    _guard(settings)
    engine = make_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            count = await conn.scalar(text("SELECT auth_dev_token_revoke(:i)"), {"i": token_id})
    finally:
        await engine.dispose()
    out.write(f"Bekor qilindi: {count}\n")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — jarayon kirish nuqtasi
    parser = argparse.ArgumentParser(description="Dev-token (ADR-072): faqat staging, faqat o'qish")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create", help="yangi token (bir marta ko'rsatiladi)")
    c.add_argument("--phone", required=True, help="staging'da ro'yxatdan o'tgan telefon raqami")
    c.add_argument("--label", default="claude", help="token nomi (masalan, claude)")
    c.add_argument("--days", type=int, default=DEFAULT_DAYS)
    sub.add_parser("list", help="tokenlar ro'yxati (xeshsiz)")
    r = sub.add_parser("revoke", help="bitta tokenni bekor qilish yoki --all")
    group = r.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=UUID)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if args.command == "create":
            asyncio.run(create(settings, args.phone, args.label, args.days, sys.stdout))
        elif args.command == "list":
            asyncio.run(list_tokens(settings, sys.stdout))
        else:
            asyncio.run(revoke(settings, None if args.all else args.id, sys.stdout))
    except DevTokenError as exc:
        print(f"Xato: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
