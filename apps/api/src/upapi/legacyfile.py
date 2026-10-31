"""Legacy ``uzum.db`` (SQLite) faylini o'qish (B4.9): do'konlar va partiyalar → ``upcore.legacy`` tiplari.

Fayl faqat o'qish uchun ochiladi (``mode=ro``, ``immutable``) — vaqtinchalik nusxada, so'rov tugagach o'chiriladi.
Faqat partiya jadvallari o'qiladi (``shops``, ``batches``, ``batch_lines``, ``batch_extras``): sotuvlar Uzum'dan qayta
olinadi (03 §16). Eski fayllarda keyin qo'shilgan ustunlar (``title``, ``cargo_date``, ``label``) bo'lmasligi mumkin.
Buzilgan qator butun faylni rad etmaydi: partiya xatosi bilan qaytadi (raqam o'ylab topilmaydi).
"""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from upcore.legacy import LegacyBatch, LegacyExtra, LegacyLine, decimal_of

HEADER = b"SQLite format 3\x00"
MAX_BYTES = 200 * 1024 * 1024
REQUIRED = ("batches", "batch_lines", "batch_extras")


class LegacyFileError(ValueError):
    """Fayl legacy bazasi emas yoki o'qib bo'lmaydi."""


@dataclass
class LegacyFile:
    shops: dict[int, str] = field(default_factory=dict)  # Uzum do'kon id → nom
    batches: list[LegacyBatch] = field(default_factory=list)
    errors: dict[int, str] = field(default_factory=dict)  # partiya id → o'qib bo'lmagan sabab


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _select(conn: sqlite3.Connection, table: str, wanted: tuple[str, ...], order: str) -> list[Any]:
    have = _columns(conn, table)
    cols = ", ".join(c if c in have else f"NULL AS {c}" for c in wanted)
    return list(conn.execute(f"SELECT {cols} FROM {table} ORDER BY {order}"))


def _day(value: Any) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    return date.fromisoformat(str(value).strip()[:10])


def _text(value: Any) -> str | None:
    text = None if value is None else str(value).strip()
    return text or None


def parse(conn: sqlite3.Connection) -> LegacyFile:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing = [t for t in REQUIRED if t not in tables]
    if missing:
        raise LegacyFileError(f"legacy partiya jadvallari topilmadi: {', '.join(missing)}")
    out = LegacyFile()
    if "shops" in tables:
        out.shops = {
            int(r["id"]): str(r["name"] or r["id"])
            for r in _select(conn, "shops", ("id", "name"), "id")
        }
    lines: dict[int, list[Any]] = {}
    for r in _select(
        conn, "batch_lines", ("id", "batch_id", "sku", "qty", "cny_unit", "label"), "id"
    ):
        lines.setdefault(r["batch_id"], []).append(r)
    extras: dict[int, list[Any]] = {}
    for r in _select(conn, "batch_extras", ("id", "batch_id", "name", "amount"), "id"):
        extras.setdefault(r["batch_id"], []).append(r)
    wanted = ("id", "shop_id", "date", "goods_cny", "cny_rate", "cargo_usd", "usd_rate", "note")
    for b in _select(conn, "batches", (*wanted, "title", "cargo_date"), "date, id"):
        try:
            day = _day(b["date"])
            if day is None:
                raise ValueError("buyurtma sanasi yo'q")
            out.batches.append(
                LegacyBatch(
                    id=int(b["id"]),
                    shop_id=None if b["shop_id"] is None else int(b["shop_id"]),
                    day=day,
                    goods_cny=decimal_of(b["goods_cny"]),
                    cny_rate=decimal_of(b["cny_rate"]),
                    cargo_usd=decimal_of(b["cargo_usd"]),
                    usd_rate=decimal_of(b["usd_rate"]),
                    cargo_day=_day(b["cargo_date"]),
                    title=_text(b["title"]),
                    note=_text(b["note"]),
                    lines=tuple(
                        LegacyLine(
                            id=int(x["id"]),
                            qty=int(x["qty"] or 0),
                            sku=_text(x["sku"]),
                            label=_text(x["label"]),
                            cny_unit=decimal_of(x["cny_unit"]),
                        )
                        for x in lines.get(b["id"], [])
                    ),
                    extras=tuple(
                        LegacyExtra(
                            id=int(e["id"]),
                            name=_text(e["name"]) or "Qo'shimcha",
                            amount=decimal_of(e["amount"]) or Decimal(0),
                        )
                        for e in extras.get(b["id"], [])
                    ),
                )
            )
        except (ValueError, TypeError, InvalidOperation) as exc:
            out.errors[int(b["id"])] = str(exc) or type(exc).__name__
    return out


def read(data: bytes) -> LegacyFile:
    """Yuklangan fayl baytlari → :class:`LegacyFile` (sinxron; API ``asyncio.to_thread`` bilan chaqiradi)."""
    if len(data) > MAX_BYTES:
        raise LegacyFileError("fayl juda katta (200 MB dan ko'p)")
    if not data.startswith(HEADER):
        raise LegacyFileError("bu SQLite fayli emas — legacy papkasidagi uzum.db ni tanlang")
    with tempfile.TemporaryDirectory(prefix="legacy-") as tmp:
        path = Path(tmp) / "uzum.db"
        path.write_bytes(data)
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        except sqlite3.Error as exc:  # pragma: no cover - sarlavha tekshiruvidan keyin kam uchraydi
            raise LegacyFileError(f"faylni ochib bo'lmadi: {exc}") from None
        try:
            conn.row_factory = sqlite3.Row
            return parse(conn)
        except sqlite3.Error as exc:
            raise LegacyFileError(f"faylni o'qib bo'lmadi: {exc}") from None
        finally:
            conn.close()
