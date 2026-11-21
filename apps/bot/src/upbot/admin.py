"""Admin kuzatuvi (B8.5a, 06 §4): xatolar va ishdan chiqqan fon ishlari adminning Telegram'iga — yangi servis o'rnatmasdan.

- **Kunlik jamlanma** (Toshkent 09:00 dan keyin, kuniga bitta): oxirgi 24 soatda yiqilgan fon ishlari (nomi bo'yicha soni),
  navbatda qotib qolgan ishlar, disk bandligi.
- **Zudlik bilan** (kritik, har 6 soatda bir marta takrorlanadi): ishlar 30 daqiqadan beri bajarilmayapti (ishchi o'lgan
  bo'lishi mumkin) yoki disk 80% dan oshdi.

Manzil — ``UP_ADMIN_CHAT_ID`` (adminning shaxsiy chat id'si; berilmasa kuzatuv o'chiq). Matnda sotuvchi ma'lumoti yo'q:
faqat ish nomlari va sonlar. "Ishlayaptimi" tekshiruvi (boshqa hostdan), zaxira va Gateway balansi — infratuzilma (B8.8).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

TASHKENT = ZoneInfo("Asia/Tashkent")
DIGEST_HOUR = 9
STUCK_AFTER = timedelta(minutes=30)
DISK_LIMIT = 80
REPEAT = timedelta(hours=6)
WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Snapshot:
    failed: dict[str, int] = field(default_factory=dict)  # ish nomi → oxirgi 24 soatda yiqilishlar
    stuck: int = 0  # 30 daqiqadan beri "todo" va vaqti o'tgan ishlar
    disk_percent: int = 0


@dataclass
class State:
    """Jarayon ichidagi eslab qolish (qayta ishga tushsa — bir marta ortiqcha xabar bo'lishi mumkin, xavfsiz)."""

    digest_day: date | None = None
    last_critical: dict[str, datetime] = field(default_factory=dict)


async def snapshot(engine: AsyncEngine, now: datetime, disk_path: str = "/") -> Snapshot:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT j.task_name, count(*) AS n FROM procrastinate_events e "
                "JOIN procrastinate_jobs j ON j.id = e.job_id "
                "WHERE e.type = 'failed' AND e.at >= :since GROUP BY j.task_name ORDER BY j.task_name"
            ),
            {"since": now - WINDOW},
        )
        failed = {r.task_name: int(r.n) for r in rows}
        stuck = await conn.scalar(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status = 'todo' AND scheduled_at IS NOT NULL AND scheduled_at < :cutoff"
            ),
            {"cutoff": now - STUCK_AFTER},
        )
    usage = shutil.disk_usage(disk_path)
    return Snapshot(failed, int(stuck or 0), int(usage.used * 100 / usage.total))


def digest_text(snap: Snapshot) -> str:
    lines = ["📋 SellerMax — kunlik jamlanma"]
    if snap.failed:
        total = sum(snap.failed.values())
        lines.append(f"❗ Yiqilgan fon ishlari (24 soat): {total}")
        lines += [f"• {name}: {n}" for name, n in sorted(snap.failed.items())]
    else:
        lines.append("✅ Yiqilgan fon ishlari yo'q")
    lines.append(f"⏳ Qotib qolgan ishlar: {snap.stuck}")
    lines.append(f"💽 Disk: {snap.disk_percent}%")
    return "\n".join(lines)


def messages_due(snap: Snapshot, state: State, now: datetime) -> list[str]:
    """Hozir yuboriladigan xabarlar (holatni yangilaydi). Kritiklar — zudlik bilan, 6 soatda bir marta takror."""
    out: list[str] = []
    critical = {
        "stuck": f"🚨 {snap.stuck} ta fon ishi 30 daqiqadan beri bajarilmayapti — ishchi ishlayaptimi?"
        if snap.stuck
        else None,
        "disk": f"🚨 Disk {snap.disk_percent}% — {DISK_LIMIT}% dan oshdi"
        if snap.disk_percent > DISK_LIMIT
        else None,
    }
    for key, message in critical.items():
        if message is None:
            state.last_critical.pop(key, None)
            continue
        last = state.last_critical.get(key)
        if last is None or now - last >= REPEAT:
            state.last_critical[key] = now
            out.append(message)
    local = now.astimezone(TASHKENT)
    if local.hour >= DIGEST_HOUR and state.digest_day != local.date():
        state.digest_day = local.date()
        out.append(digest_text(snap))
    return out
