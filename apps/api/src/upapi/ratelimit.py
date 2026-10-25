"""IP bo'yicha so'rov hisoblagichi (B2.10): kirish kodi yuborish har xil raqam bilan ham cheklanadi (ADR-028).

Raqam bo'yicha cheklov bazada (``auth_otp_issue``); bu esa jarayon ichidagi siljuvchi oyna — staging'da API bitta
jarayon. Bir nechta jarayon yoki server bo'lsa (B8), hisoblagich bazaga yoki Caddy'ga ko'chadi. Mijoz IP manzili
Caddy'ning ``X-Forwarded-For`` sarlavhasidan (uvicorn ``--proxy-headers``); Caddy tashqaridan kelgan bu sarlavhaga
ishonmaydi, shuning uchun uni soxtalashtirib bo'lmaydi.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class SlidingWindow:
    """``hit(key)`` — oxirgi ``window`` soniyada ``limit`` tadan oshmasa ``True`` (urinish sanaladi)."""

    def __init__(
        self, limit: int, window: float, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._next_prune = 0.0

    def hit(self, key: str) -> bool:
        now = self._clock()
        self._prune(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def _prune(self, now: float) -> None:
        """Eski kalitlarni vaqti-vaqti bilan tozalash — xotira IP soni bilan cheksiz o'smaydi."""
        if now < self._next_prune:
            return
        self._next_prune = now + self.window
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]
