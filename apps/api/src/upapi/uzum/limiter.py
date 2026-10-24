"""Kalit bo'yicha tezlik navbati (03 §6): bitta kalitga so'rovlar orasida kamida ``interval`` soniya, foydalanuvchi
amali fon ishidan oldin o'tadi.

Bu jarayon ichidagi navbat. Jarayonlar orasida bitta kalitga bitta ishchi — Procrastinate ``lock = account_id``
(B2.6); shuning uchun bu yerda taqsimlangan qulf kerak emas.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Priority(StrEnum):
    USER = "user"  # foydalanuvchi bosgan amal ("Hozir yangilash", kalit tekshiruvi)
    BACKGROUND = "background"  # davriy sinxron


@dataclass
class _Slot:
    next_at: float = 0.0
    users_waiting: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RateLimiter:
    """``await limiter.acquire(account_id, Priority.USER)`` — navbat kelganda qaytadi.

    Navbat vaqti kelganda (oldingi so'rovdan ``interval`` o'tgach) kutayotganlardan biri o'tadi; kutayotgan
    foydalanuvchi so'rovi bo'lsa, fon so'rovi unga yo'l beradi.
    """

    def __init__(
        self,
        interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        yield_every: float = 0.01,
    ) -> None:
        self.interval = interval
        self._clock = clock
        self._sleep = sleep
        self._yield_every = yield_every
        self._slots: dict[str, _Slot] = {}

    def _slot(self, key: str) -> _Slot:
        slot = self._slots.get(key)
        if slot is None:
            slot = self._slots[key] = _Slot()
        return slot

    async def acquire(self, key: str, priority: Priority = Priority.BACKGROUND) -> None:
        slot = self._slot(key)
        user = priority is Priority.USER
        if user:
            slot.users_waiting += 1
        try:
            while True:
                async with slot.lock:
                    now = self._clock()
                    wait = slot.next_at - now
                    if wait <= 0 and (user or not slot.users_waiting):
                        slot.next_at = now + self.interval
                        return
                await self._sleep(wait if wait > 0 else self._yield_every)
        finally:
            if user:
                slot.users_waiting -= 1
