"""To'liq eksport (B7.5, ADR-065; 01 D9 "ma'lumot sizniki"): tashkilot ma'lumotining ZIP'i — har jadval CSV va JSON, ``manifest.json``.

Kiradi: sotuvchi kiritgan hamma narsa (xaridlar, chiqimlar, tannarx, o'z xarajatlar, sozlamalar, ombor harakatlari ...) va
Uzumdan olingan faktlar (sotuvlar, xarajatlar, mahsulotlar, postavkalar, qaytarishlar). Kirmaydi (``EXCLUDED``, sabab bilan):
Uzum kaliti, sessiyalar, Telegram chat id, boshqa a'zolarning telefoni va taklif tokenlari, hosila jadvallar (qayta hisoblanadi),
texnik navbatlar. Jadvalning har bir tashkilot jadvali ``TENANT − EXCLUDED`` — yangi jadval qo'shilsa u avtomatik kiradi
(``EXCLUDED`` da nega kirmasligi yozilmasa) — test shuni tekshiradi.

Hamma o'qish ``org_transaction`` ichida: RLS faqat shu tashkilot qatorlarini beradi, boshqa tashkilot ma'lumoti fayla tushmaydi.
ZIP xotirada yig'iladi (diskka yozilmaydi) va ``data_exports.content`` ga yoziladi; hajm ``MAX_BYTES`` dan oshsa — xato.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import LargeBinary, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from upapi.db import models as m
from upapi.db.session import org_transaction

TTL = timedelta(hours=24)  # tayyor fayl va havola muddati
MAX_BYTES = 300 * 1024 * 1024
CHUNK = 2000

EXCLUDED: dict[str, str] = {
    "mp_accounts": "Uzum kaliti (shifrlangan) — hech qachon chiqmaydi",
    "notification_channels": "Telegram chat id",
    "notification_links": "bir martalik ulash tokenlari",
    "notification_rules": "shaxsiy bildirishnoma sozlamasi (boshqa a'zolarniki ham)",
    "notification_prefs": "shaxsiy bildirishnoma sozlamasi (boshqa a'zolarniki ham)",
    "notifications": "yetkazish navbati",
    "memberships": "boshqa a'zolar (telefon va rollar)",
    "invites": "taklif tokenlari va telefonlar",
    "audit_log": "a'zolar harakat jurnali (boshqa a'zolar shaxsiy ma'lumoti)",
    "events": "ichki mahsulot tahlili",
    "sync_state": "texnik holat",
    "sync_runs": "texnik jurnal",
    "recalc_queue": "texnik navbat",
    "lots": "hosila (xaridlardan qayta hisoblanadi)",
    "missing_losses": "hosila (qayta hisoblanadi)",
    "sale_costs": "hosila (qayta hisoblanadi)",
    "daily_sku_metrics": "hosila (qayta hisoblanadi)",
    "subscriptions": "tarif va to'lov (bizning hisob)",
    "billing_invoices": "tarif va to'lov (bizning hisob)",
    "payments": "tarif va to'lov (bizning hisob)",
    "data_exports": "eksportning o'zi",
}
ORG_COLUMNS = (
    "id",
    "name",
    "inn",
    "language",
    "timezone",
    "cost_method",
    "settings",
    "cost_start_on",
    "created_at",
)


def exported_tables() -> list[str]:
    """Eksportga kiradigan tashkilot jadvallari (alifbo tartibida)."""
    return sorted(set(m.TENANT) - set(EXCLUDED) - {"orgs"})


class ExportTooLarge(Exception):
    pass


def _plain(value: Any) -> Any:
    """JSON uchun qiymat: UUID / Decimal / sana → matn (pul va sana aniqligini yo'qotmaydi)."""
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return None  # ikkilik maydonlar eksportga kirmaydi
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _cell(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else value


async def _rows(conn: AsyncConnection, table: Any):  # type: ignore[no-untyped-def]
    columns = [c for c in table.columns if not isinstance(c.type, LargeBinary)]
    result = await conn.stream(select(*columns))
    async for chunk in result.partitions(CHUNK):
        for row in chunk:
            yield columns, row


async def build_zip(
    conn: AsyncConnection, org_id: UUID, now: datetime
) -> tuple[bytes, dict[str, int]]:
    """ZIP baytlari va jadval → qatorlar soni. ``conn`` — shu tashkilot doirasidagi (RLS) ulanish."""
    out = io.BytesIO()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        org = (
            await conn.execute(
                select(*[m.orgs.c[c] for c in ORG_COLUMNS]).where(m.orgs.c.id == org_id)
            )
        ).first()
        if org is not None:
            record = {c: _plain(v) for c, v in zip(ORG_COLUMNS, org, strict=True)}
            z.writestr("json/org.json", json.dumps([record], ensure_ascii=False, indent=1))
            counts["org"] = 1
        for name in exported_tables():
            table = m.metadata.tables[name]
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            header_done = False
            records: list[dict[str, Any]] = []
            n = 0
            async for columns, row in _rows(conn, table):
                if not header_done:
                    writer.writerow([c.name for c in columns])
                    header_done = True
                writer.writerow([_cell(v) for v in row])
                records.append({c.name: _plain(v) for c, v in zip(columns, row, strict=True)})
                n += 1
            if not header_done:  # bo'sh jadval ham sarlavha bilan
                writer.writerow(
                    [c.name for c in table.columns if not isinstance(c.type, LargeBinary)]
                )
            z.writestr(f"csv/{name}.csv", "﻿" + csv_buf.getvalue())
            z.writestr(f"json/{name}.json", json.dumps(records, ensure_ascii=False))
            counts[name] = n
            if out.tell() > MAX_BYTES:
                raise ExportTooLarge(name)
        manifest = {
            "app": "SellerMax",
            "org_id": str(org_id),
            "created_at": now.astimezone(UTC).isoformat(),
            "tables": counts,
            "note": "csv/ — har jadval jadval ko'rinishida (UTF-8), json/ — xuddi shu qatorlar JSON'da; "
            "Uzum kaliti, sessiyalar, Telegram chat id va boshqa a'zolarning telefonlari kirmaydi.",
        }
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    return out.getvalue(), counts


async def run_export(engine: AsyncEngine, org_id: UUID, export_id: UUID, now: datetime) -> str:
    """Fon ishi: so'rovni ``running`` qiladi, ZIP yig'adi va ``ready`` (yoki ``failed``) yozadi. Qaytaradi — yakuniy holat."""
    t = m.data_exports
    async with org_transaction(engine, org_id) as conn:
        row = (await conn.execute(select(t.c.status).where(t.c.id == export_id))).first()
        if row is None or row.status != "pending":
            return "skipped"  # qayta bajarilgan yoki o'chirilgan
        await conn.execute(t.update().where(t.c.id == export_id).values(status="running"))
    try:
        async with org_transaction(engine, org_id) as conn:
            data, counts = await build_zip(conn, org_id, now)
    except ExportTooLarge:
        return await _finish(engine, org_id, export_id, "failed", error="fayl juda katta")
    except Exception as exc:
        return await _finish(engine, org_id, export_id, "failed", error=type(exc).__name__)
    return await _finish(
        engine,
        org_id,
        export_id,
        "ready",
        content=data,
        size=len(data),
        tables=counts,
        expires_at=now + TTL,
    )


async def _finish(
    engine: AsyncEngine,
    org_id: UUID,
    export_id: UUID,
    status: str,
    *,
    error: str | None = None,
    content: bytes | None = None,
    size: int | None = None,
    tables: dict[str, int] | None = None,
    expires_at: datetime | None = None,
) -> str:
    t = m.data_exports
    async with org_transaction(engine, org_id) as conn:
        await conn.execute(
            t.update()
            .where(t.c.id == export_id)
            .values(
                status=status,
                error=error,
                content=content,
                size_bytes=size,
                tables=tables,
                expires_at=expires_at,
            )
        )
        if status == "ready":
            requester = await conn.scalar(select(t.c.user_id).where(t.c.id == export_id))
            await conn.execute(
                m.notifications.insert().values(
                    org_id=org_id,
                    user_id=requester,
                    event="export_ready",
                    dedupe_key=f"export:{export_id}",
                    status="pending",
                    critical=False,
                    payload={"export_id": str(export_id), "size": size},
                    due_at=expires_at - TTL if expires_at else datetime.now(UTC),
                )
            )
    return status
