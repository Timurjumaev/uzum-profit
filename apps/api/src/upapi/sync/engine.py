"""Sinxron ishlari (B2.6, 02 M3, 03 §6): bitta akkaunt (kalit) uchun navbatdagi ma'lumot turlarini Uzum'dan olib
bazaga yozadi. Procrastinate ishi (:mod:`upapi.sync.jobs`) shu funksiyani chaqiradi — ``lock = account_id``, ya'ni
bitta kalitga bir vaqtda bitta ish (03 §6 "Tezlik").

Ish tartibi (:func:`sync_account`):

1. Uzum uzilishi bo'lsa — ish bajarilmaydi (pauza tugagach bitta ish sinov qiladi, :mod:`upapi.sync.health`).
2. Akkaunt: uzilgan, yaroqsiz kalit yoki pauza — o'tkazib yuboriladi; kvota tugagan / WAF — ``sync_probe_minutes``
   da bir marta sinov.
3. Navbat: faol do'konlar × ma'lumot turlari, vaqti kelganlari (``sync_intervals``, snapshot — kuniga bir marta
   23:50 dan keyin), eng eski yangilanganidan boshlab. Butun akkaunt bo'yicha olinadigan turlar (do'konlar,
   qaytarishlar) bir marta so'raladi, natija har do'konga yoziladi.
4. Har tur — ``sync_runs`` qatori (boshlanishda ``running``, har sahifadan keyin progress, oxirida holat) va
   ``sync_state`` (oxirgi urinish/muvaffaqiyat, kursor). 0 ta obyekt bilan tugagan ish (sotuv, mahsulot, do'kon) —
   "ogohlantirish".

Sotuv va xarajat usullari: **tarix** (birinchi marta, ``sync_history_from`` dan; Uzum rad etsa qisqaroq oynalar;
uzilsa kursor sahifasidan davom etadi), **inkremental** (oxirgi kunlar), **chuqur** (kuniga bir marta 45 kun —
holatlar o'zgaradi), **uzilish** (uzilish davrini to'ldirish).

Xatolar (02 M3): kalit xatosi ketma-ket ``sync_auth_failures`` marta → "kalit yaroqsiz"; WAF va kunlik kvota —
akkaunt holati; kvota zaxirasi — fon ishi to'xtaydi (foydalanuvchi amali o'tadi); tarmoq/5xx — uzilish signali.
Uzum'ga so'rov paytida DB tranzaksiyasi ochiq turmaydi: har sahifa o'z qisqa tranzaksiyasida yoziladi.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx
from pydantic import SecretStr
from sqlalchemy import Row, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from upcore.expenses import CodeBook

from upapi.crypto import CipherError, TokenCipher, account_aad
from upapi.db import models as m
from upapi.db.session import make_engine, org_transaction
from upapi.logs import get_logger
from upapi.settings import Settings
from upapi.sync import health, mapping, store
from upapi.uzum.client import (
    AuthError,
    BadRequest,
    QuotaExhausted,
    QuotaReserved,
    UpstreamError,
    UzumClient,
    UzumError,
    WafBlocked,
)
from upapi.uzum.limiter import Priority, RateLimiter

_log = get_logger("upapi.sync")


class Kind(StrEnum):
    SHOPS = "shops"
    ORDERS = "orders"
    EXPENSES = "expenses"
    PRODUCTS = "products"
    SNAPSHOT = "snapshot"
    INVOICES = "invoices"
    RETURNS = "returns"


ACCOUNT_KINDS = (Kind.SHOPS, Kind.RETURNS)  # bitta so'rov butun akkaunt uchun
SHOP_KINDS = (Kind.ORDERS, Kind.EXPENSES, Kind.PRODUCTS, Kind.INVOICES, Kind.SNAPSHOT)
USER_KINDS = (Kind.ORDERS, Kind.EXPENSES, Kind.PRODUCTS)  # "Hozir yangilash"
EMPTY_IS_WARNING = frozenset({Kind.SHOPS, Kind.ORDERS, Kind.PRODUCTS})


class Trigger(StrEnum):
    SCHEDULE = "schedule"
    USER = "user"  # "Hozir yangilash" — ustuvor navbat
    CONNECT = "connect"  # kalit ulandi — tarix yuklanadi (M2 3-qadam)


class Mode(StrEnum):
    FULL = "full"  # ro'yxat to'liq (mahsulot, postavka, qaytarish, do'kon, snapshot)
    HISTORY = "history"
    INCREMENTAL = "incremental"
    DEEP = "deep"
    OUTAGE = "outage"


TASHKENT = mapping.TASHKENT


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Runtime:
    """Ishchi (va API) uchun bog'liqliklar. ``transport`` — testlarda soxta Uzum; ``clock`` — vaqt (testlarda)."""

    engine: AsyncEngine
    settings: Settings
    cipher: TokenCipher
    limiter: RateLimiter
    transport: httpx.AsyncBaseTransport | None = None
    clock: Callable[[], datetime] = utcnow
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    @classmethod
    def from_settings(cls, settings: Settings) -> Runtime:
        return cls(
            engine=make_engine(settings.database_url),
            settings=settings,
            cipher=TokenCipher.from_settings(settings.token_keys, settings.token_key_version),
            limiter=RateLimiter(settings.uzum_min_interval_seconds),
        )

    async def aclose(self) -> None:
        await self.engine.dispose()


@dataclass(frozen=True, slots=True)
class ShopRef:
    id: UUID
    external_id: int


@dataclass(slots=True)
class State:
    """``sync_state`` qatori (yo'q bo'lsa bo'sh)."""

    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_status: str | None = None
    failures: int = 0
    cursor: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunSummary:
    shop_id: UUID
    kind: Kind
    mode: Mode
    status: str
    fetched: int
    written: int
    error: str | None = None
    http_status: int | None = None


@dataclass
class AccountResult:
    """``status``: ``done`` (navbat bajarildi), ``idle`` (vaqti kelgan ish yo'q), ``skipped`` (sabab ``reason``)."""

    status: str
    reason: str | None = None
    runs: list[RunSummary] = field(default_factory=list)


@dataclass(slots=True)
class Counts:
    fetched: int = 0
    written: int = 0
    skipped: int = 0
    total: int | None = None


@dataclass
class Task:
    """Navbatdagi bitta ish: tur va do'konlar (butun akkaunt turlarida — hamma faol do'konlar)."""

    kind: Kind
    shops: list[ShopRef]
    staleness: datetime


# --- Navbat (qaysi tur vaqti keldi) --------------------------------------------------------------


def _local(moment: datetime) -> datetime:
    return moment.astimezone(TASHKENT)


def is_due(settings: Settings, kind: Kind, state: State | None, now: datetime) -> bool:
    """Tur vaqti keldimi. Snapshot — Toshkent vaqti bilan ``sync_snapshot_at`` dan keyin, kuniga bir marta
    (muvaffaqiyatsiz bo'lsa 2 daqiqada qayta — oyna yarim tungacha). Tugallanmagan tarix — har daqiqada davom ettiriladi."""
    local = _local(now)
    if kind is Kind.SNAPSHOT:
        if local.time() < settings.sync_snapshot_at:
            return False
        if state is None or state.last_attempt_at is None:
            return True
        done_today = (
            state.last_success_at is not None
            and _local(state.last_success_at).date() == local.date()
        )
        return not done_today and now - state.last_attempt_at >= timedelta(minutes=2)
    if state is None or state.last_attempt_at is None:
        return True
    if kind in (Kind.ORDERS, Kind.EXPENSES) and state.cursor.get("history") is None:
        return now - state.last_attempt_at >= timedelta(minutes=1)
    interval = timedelta(minutes=settings.sync_intervals.get(kind.value, 60))
    return now - state.last_attempt_at >= interval


def plan(
    settings: Settings,
    shops: Sequence[ShopRef],
    states: dict[tuple[UUID, Kind], State],
    now: datetime,
    forced: Sequence[Kind] | None = None,
) -> list[Task]:
    """Navbat: avval butun akkaunt turlari (do'konlar ro'yxati birinchi), keyin do'kon turlari — eng eski
    yangilanganidan boshlab (03 §6). ``forced`` — faqat shu turlar, vaqtidan qat'i nazar ("Hozir yangilash")."""
    oldest = datetime.min.replace(tzinfo=UTC)

    def due(kind: Kind, shop: ShopRef) -> bool:
        if forced is not None:
            return kind in forced
        return is_due(settings, kind, states.get((shop.id, kind)), now)

    def staleness(kind: Kind, shop: ShopRef) -> datetime:
        state = states.get((shop.id, kind))
        return (state.last_success_at if state else None) or oldest

    tasks = []
    for kind in ACCOUNT_KINDS:
        if any(due(kind, s) for s in shops):
            tasks.append(Task(kind, list(shops), min(staleness(kind, s) for s in shops)))
    shop_tasks = [
        Task(kind, [shop], staleness(kind, shop))
        for shop in shops
        for kind in SHOP_KINDS
        if due(kind, shop)
    ]
    shop_tasks.sort(key=lambda t: (t.staleness, SHOP_KINDS.index(t.kind)))
    return tasks + shop_tasks


# --- Akkaunt ishi ----------------------------------------------------------------------------------


class _Stop(Exception):
    """Akkaunt ishi to'xtaydi (kalit, kvota, WAF, uzilish)."""


@dataclass
class _Account:
    id: UUID
    status: str
    quota_remaining: int | None
    auth_failures: int
    token: SecretStr


class _Job:
    def __init__(
        self,
        rt: Runtime,
        org_id: UUID,
        account: _Account,
        client: UzumClient,
        trigger: Trigger,
        states: dict[tuple[UUID, Kind], State],
        outage: health.Outage,
        probe: bool,
    ) -> None:
        self.rt, self.settings = rt, rt.settings
        self.org_id, self.account, self.client, self.trigger = org_id, account, client, trigger
        self.states, self.outage, self.probe = states, outage, probe
        self.status = account.status
        self.auth_failures = account.auth_failures
        self.succeeded = False
        self.runs: list[RunSummary] = []
        self._codebook: CodeBook | None = None

    # --- DB yordamchilari ---

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[AsyncConnection]:
        async with org_transaction(self.rt.engine, self.org_id) as conn:
            yield conn

    async def codebook(self) -> CodeBook:
        if self._codebook is None:
            async with self.rt.engine.connect() as conn:
                rows = await conn.execute(
                    select(
                        m.expense_codes.c.code, m.expense_codes.c.category, m.expense_codes.c.match
                    )
                )
                self._codebook = mapping.codebook(r._asdict() for r in rows)
        return self._codebook

    # --- Bitta ish ---

    async def run(self, task: Task) -> None:
        started = self.rt.clock()
        mode = self.mode(task.kind, task.shops[0], started)
        run = _Run(self, task, mode, started)
        await run.start()
        try:
            await HANDLERS[task.kind](run)
        except UzumError as exc:
            await run.finish(exc)
            await self.on_error(exc, task)
            return
        except Exception as exc:
            _log.exception("sync_failed", kind=task.kind.value, error_code=type(exc).__name__)
            await run.finish(exc)
            return
        await run.finish(None)
        self.succeeded = True
        self.auth_failures = 0
        if self.probe:
            await health.record_success(self.rt.engine, self.rt.clock())
            self.probe = False

    async def on_error(self, exc: UzumError, task: Task) -> None:
        now = self.rt.clock()
        if isinstance(exc, AuthError):
            self.auth_failures += 1
            if self.auth_failures >= self.settings.sync_auth_failures:
                self.status = "invalid"
            raise _Stop
        if isinstance(exc, WafBlocked):
            self.status = "waf_blocked"
            raise _Stop
        if isinstance(exc, QuotaExhausted):
            self.status = "quota_exhausted"
            raise _Stop
        if isinstance(exc, QuotaReserved):
            raise _Stop
        if isinstance(exc, UpstreamError):
            await health.record_failure(self.rt.engine, self.settings, task.shops[0].id, now)
            raise _Stop
        # BadRequest, UnexpectedResponse, BurstLimited — shu tur xato, keyingilari davom etadi.

    def mode(self, kind: Kind, shop: ShopRef, now: datetime) -> Mode:
        if kind not in (Kind.ORDERS, Kind.EXPENSES):
            return Mode.FULL
        state = self.states.get((shop.id, kind)) or State()
        cursor = state.cursor
        if cursor.get("history") is None:
            return Mode.HISTORY
        if self.trigger is Trigger.USER:
            return Mode.INCREMENTAL
        recovered_at, recovered_from = self.outage.recovered_at, self.outage.recovered_from
        if recovered_at is not None and recovered_from is not None:
            filled = _parse(cursor.get("outage_filled_at")) or _parse(cursor.get("history_done_at"))
            if filled is None or filled < recovered_at:
                return Mode.OUTAGE
        deep_at = _parse(cursor.get("deep_at"))
        if deep_at is None or now - deep_at >= timedelta(hours=self.settings.sync_deep_every_hours):
            return Mode.DEEP
        return Mode.INCREMENTAL

    async def finish(self) -> None:
        """Akkaunt holati: kvota qoldig'i, ketma-ket kalit xatolari, holat o'zgarishi (audit bilan)."""
        values: dict[str, Any] = {
            "auth_failures": self.auth_failures,
            "updated_at": self.rt.clock(),
        }
        if self.client.quota_remaining is not None:
            values["quota_remaining"] = self.client.quota_remaining
        status = self.status
        if self.succeeded and status in ("quota_exhausted", "waf_blocked"):
            status = "active"
        if status == "quota_exhausted":
            values["quota_remaining"] = 0
        if status != self.account.status or status in ("quota_exhausted", "waf_blocked"):
            values["checked_at"] = self.rt.clock()
        values["status"] = status
        async with self.tx() as conn:
            # Uzilgan (yoki parallel almashtirilgan) akkauntda holat o'zgarmaydi.
            result = await conn.execute(
                update(m.mp_accounts)
                .where(
                    m.mp_accounts.c.id == self.account.id,
                    m.mp_accounts.c.status == self.account.status,
                    m.mp_accounts.c.token_encrypted.is_not(None),
                )
                .values(**values)
            )
            if result.rowcount and status != self.account.status:
                await conn.execute(
                    insert(m.audit_log).values(
                        org_id=self.org_id,
                        actor_user_id=None,
                        action="account.sync_status",
                        entity="mp_account",
                        entity_id=self.account.id,
                        before={"status": self.account.status},
                        after={"status": status},
                    )
                )
        if status != self.account.status:
            _log.warning(
                "mp_account_status",
                account_id=str(self.account.id),
                before=self.account.status,
                after=status,
            )


def _parse(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


class _Run:
    """Bitta tur ishi: har do'kon uchun ``sync_runs`` qatori, progress va oxirgi holat (``sync_state``)."""

    def __init__(self, job: _Job, task: Task, mode: Mode, started: datetime) -> None:
        self.job, self.task, self.kind, self.mode, self.started = (
            job,
            task,
            task.kind,
            mode,
            started,
        )
        self.client = job.client
        self.counts = {s.id: Counts() for s in task.shops}
        self.cursors: dict[UUID, dict[str, Any]] = {
            s.id: dict((job.states.get((s.id, task.kind)) or State()).cursor) for s in task.shops
        }
        self.run_ids: dict[UUID, UUID] = {}
        self._requests_at_start = job.client.requests

    @property
    def org_id(self) -> UUID:
        return self.job.org_id

    @property
    def settings(self) -> Settings:
        return self.job.settings

    async def start(self) -> None:
        async with self.job.tx() as conn:
            for shop in self.task.shops:
                # Ishchi to'xtab qolgan (crash) ishlar — tugallanmagan.
                await conn.execute(
                    update(m.sync_runs)
                    .where(
                        m.sync_runs.c.shop_id == shop.id,
                        m.sync_runs.c.kind == self.kind.value,
                        m.sync_runs.c.status == "running",
                    )
                    .values(
                        status="error",
                        error="interrupted",
                        finished_at=self.started,
                        updated_at=self.started,
                    )
                )
                self.run_ids[shop.id] = (
                    await conn.execute(
                        insert(m.sync_runs)
                        .values(
                            org_id=self.org_id,
                            shop_id=shop.id,
                            kind=self.kind.value,
                            started_at=self.started,
                            trigger=self.job.trigger.value,
                            mode=self.mode.value,
                        )
                        .returning(m.sync_runs.c.id)
                    )
                ).scalar_one()

    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncConnection]:
        """Ma'lumot yozish tranzaksiyasi; oxirida shu tranzaksiyada progress (olingan, yozilgan, jami)."""
        async with self.job.tx() as conn:
            yield conn
            await self._progress(conn)

    async def _progress(self, conn: AsyncConnection, **extra: Any) -> None:
        requests = self.client.requests - self._requests_at_start
        for shop_id, counts in self.counts.items():
            await conn.execute(
                update(m.sync_runs)
                .where(m.sync_runs.c.id == self.run_ids[shop_id])
                .values(
                    fetched=counts.fetched,
                    written=counts.written,
                    total=counts.total,
                    requests=requests,
                    updated_at=self.job.rt.clock(),
                    **extra,
                )
            )

    async def save_cursor(self, conn: AsyncConnection, shop_id: UUID) -> None:
        """Tarix yuklashi uzilsa shu joydan davom etish uchun — ma'lumot bilan bitta tranzaksiyada."""
        await self._state(conn, shop_id, {"cursor": self.cursors[shop_id]})

    async def _state(self, conn: AsyncConnection, shop_id: UUID, values: dict[str, Any]) -> None:
        stmt = pg_insert(m.sync_state).values(
            org_id=self.org_id, shop_id=shop_id, kind=self.kind.value, **values
        )
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["org_id", "shop_id", "kind"],
                set_={**{k: stmt.excluded[k] for k in values}, "updated_at": self.job.rt.clock()},
            )
        )

    def map_rows(
        self,
        shop: ShopRef,
        rows: list[dict[str, Any]],
        fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        counts = self.counts[shop.id]
        counts.fetched += len(rows)
        out = []
        for raw in rows:
            try:
                out.append({**fn(raw), "org_id": self.org_id, "shop_id": shop.id})
            except mapping.MappingError as exc:
                counts.skipped += 1
                _log.warning(
                    "sync_row_skipped", kind=self.kind.value, row_id=raw.get("id"), reason=str(exc)
                )
        return out

    async def finish(self, exc: BaseException | None) -> None:
        now = self.job.rt.clock()
        error_code, http_status = None, None
        if isinstance(exc, QuotaReserved):
            status, error_code = "skipped", exc.kind
        elif isinstance(exc, UzumError):
            status, error_code, http_status = "error", exc.kind, exc.status
        elif exc is not None:
            status, error_code = "error", "internal"
        else:
            status = "ok"
        async with self.job.tx() as conn:
            for shop in self.task.shops:
                counts = self.counts[shop.id]
                shop_status, shop_error = status, error_code
                if status == "ok" and counts.skipped:
                    shop_status, shop_error = "warning", f"skipped:{counts.skipped}"
                elif status == "ok" and not counts.fetched and self.kind in EMPTY_IS_WARNING:
                    shop_status, shop_error = "warning", "empty"
                await conn.execute(
                    update(m.sync_runs)
                    .where(m.sync_runs.c.id == self.run_ids[shop.id])
                    .values(
                        status=shop_status,
                        error=shop_error,
                        http_status=http_status,
                        finished_at=now,
                        fetched=counts.fetched,
                        written=counts.written,
                        total=counts.total,
                        requests=self.client.requests - self._requests_at_start,
                        updated_at=now,
                    )
                )
                previous = self.job.states.get((shop.id, self.kind)) or State()
                failed = shop_status in ("error", "skipped")
                values: dict[str, Any] = {
                    "last_attempt_at": self.started,
                    "last_status": shop_status,
                    "last_error": shop_error,
                    "failures": previous.failures + 1 if failed else 0,
                    "cursor": self.cursors[shop.id],
                    "last_success_at": previous.last_success_at if failed else self.started,
                }
                await self._state(conn, shop.id, values)
                self.job.states[(shop.id, self.kind)] = State(
                    values["last_success_at"],
                    self.started,
                    shop_status,
                    values["failures"],
                    self.cursors[shop.id],
                )
                self.job.runs.append(
                    RunSummary(
                        shop.id,
                        self.kind,
                        self.mode,
                        shop_status,
                        counts.fetched,
                        counts.written,
                        shop_error,
                        http_status,
                    )
                )
        if exc is not None:
            _log.warning(
                "sync_run_failed",
                kind=self.kind.value,
                mode=self.mode.value,
                error_code=error_code,
                http_status=http_status,
            )


# --- Turlar --------------------------------------------------------------------------------------

_HOUR_MS = 3_600_000


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


async def _shops(run: _Run) -> None:
    infos = await run.client.shops()
    async with run.write() as conn:
        written = await store.upsert_shops(conn, run.org_id, run.job.account.id, infos)
        for counts in run.counts.values():
            counts.fetched, counts.written = len(infos), written


async def _timeline(run: _Run, fetch: Callable[..., AsyncIterator[Any]], write: Any) -> None:
    """Sotuv yoki xarajat: usul bo'yicha oyna, sahifalab yozish; tarix — kursor bilan davom ettiriladi."""
    shop = run.task.shops[0]
    cursor = run.cursors[shop.id]
    now = run.started
    settings = run.settings
    if run.mode is not Mode.HISTORY:
        if run.mode is Mode.DEEP:
            start = now - timedelta(days=settings.sync_deep_days)
        elif run.mode is Mode.OUTAGE:
            recovered_from = run.job.outage.recovered_from
            assert recovered_from is not None
            start = min(
                recovered_from, now - timedelta(days=settings.sync_recent_days)
            ) - timedelta(days=1)
        else:
            start = now - timedelta(days=settings.sync_recent_days)
            state = run.job.states.get((shop.id, run.kind))
            if state is not None and state.last_success_at is not None:
                start = min(start, state.last_success_at - timedelta(days=1))
        async for page in fetch(shop.external_id, _ms(start), max_pages=200):
            await write(run, shop, page)
        if run.mode is Mode.DEEP:
            cursor["deep_at"] = now.isoformat()
        elif run.mode is Mode.OUTAGE:
            cursor["outage_filled_at"] = now.isoformat()
        return

    windows = [
        (_ms(datetime.combine(settings.sync_history_from, datetime.min.time(), UTC)), "full")
    ]
    windows += [
        (_ms(now - timedelta(days=d)), f"limited:{d}") for d in settings.sync_history_fallback_days
    ]
    resume = cursor.get("resume") or {}
    index = next((i for i, w in enumerate(windows) if w[1] == resume.get("tag")), 0)
    if resume.get("tag") and resume.get("from"):
        windows[index] = (int(resume["from"]), windows[index][1])
    for position, (date_from, tag) in enumerate(windows[index:], start=index):
        resuming = position == index and resume.get("tag") == tag
        start_page = int(resume.get("page", 0)) if resuming else 0
        size = int(resume["size"]) if resuming and resume.get("size") else None
        wrote = False
        try:
            async for page in fetch(
                shop.external_id, date_from, max_pages=1000, start_page=start_page, size=size
            ):
                cursor["resume"] = {
                    "tag": tag,
                    "from": date_from,
                    "page": page.page + 1,
                    "size": page.size,
                }
                await write(run, shop, page, save_cursor=True)
                wrote = True
        except BadRequest:
            # Uzum bu oynani rad etdi (birinchi sahifada) — qisqarog'i; yarim yo'lda 400 — haqiqiy xato.
            if wrote or resuming or position == len(windows) - 1:
                raise
            _log.info("sync_history_window_rejected", kind=run.kind.value, window=tag)
            cursor.pop("resume", None)
            continue
        cursor.pop("resume", None)
        cursor.update(history=tag, history_done_at=now.isoformat(), deep_at=now.isoformat())
        if run.kind is Kind.ORDERS:
            async with run.write() as conn:
                await conn.execute(
                    update(m.shops).where(m.shops.c.id == shop.id).values(history_status=tag)
                )
        return


async def _write_sales(run: _Run, shop: ShopRef, page: Any, save_cursor: bool = False) -> None:
    rows = run.map_rows(shop, page.rows, mapping.sale)
    async with run.write() as conn:
        result = await store.upsert(
            conn, m.sale_items, rows, ("org_id", "shop_id", "order_id", "external_id")
        )
        run.counts[shop.id].written += result.written
        run.counts[shop.id].total = page.total
        if save_cursor:
            await run.save_cursor(conn, shop.id)


async def _orders(run: _Run) -> None:
    await _timeline(run, run.client.orders, _write_sales)
    shop = run.task.shops[0]
    async with run.write() as conn:
        await store.link_sales(conn, shop.id)
        first = await store.first_sale_on(conn, shop.id)
        await conn.execute(
            update(m.shops)
            .where(m.shops.c.id == shop.id, m.shops.c.first_sale_on.is_distinct_from(first))
            .values(first_sale_on=first, updated_at=run.job.rt.clock())
        )


async def _write_expenses(run: _Run, shop: ShopRef, page: Any, save_cursor: bool = False) -> None:
    book = await run.job.codebook()
    rows = run.map_rows(shop, page.rows, lambda raw: mapping.expense(raw, book))
    async with run.write() as conn:
        result = await store.upsert(
            conn,
            m.mp_expenses,
            rows,
            ("org_id", "shop_id", "external_id"),
            exact=mapping.EXPENSE_DERIVED,
        )
        run.counts[shop.id].written += result.written
        if save_cursor:
            await run.save_cursor(conn, shop.id)


async def _expenses(run: _Run) -> None:
    await _timeline(run, run.client.expenses, _write_expenses)
    async with run.write() as conn:
        await store.link_expenses(conn, run.task.shops[0].id)


async def _products(run: _Run) -> None:
    shop = run.task.shops[0]
    async for page in run.client.products(shop.external_id):
        counts = run.counts[shop.id]
        counts.fetched += len(page.rows)
        counts.total = page.total
        products, skus = [], []
        for raw in page.rows:
            try:
                product_row, sku_rows = mapping.product(raw)
            except mapping.MappingError:
                counts.skipped += 1
                continue
            products.append({**product_row, "org_id": run.org_id, "shop_id": shop.id})
            skus += [
                {
                    **s,
                    "org_id": run.org_id,
                    "shop_id": shop.id,
                    "product_ext": product_row["external_id"],
                }
                for s in sku_rows
            ]
        async with run.write() as conn:
            key = ("org_id", "shop_id", "external_id")
            counts.written += (await store.upsert(conn, m.mp_products, products, key)).written
            ids = await store.ids_by_external(
                conn, m.mp_products, shop.id, (p["external_id"] for p in products)
            )
            for sku in skus:
                sku["product_id"] = ids.get(sku.pop("product_ext"))
            counts.written += (await store.upsert(conn, m.mp_skus, skus, key)).written
    async with run.write() as conn:
        await store.link_sales(conn, shop.id)
        await store.link_children_skus(conn, shop.id)


async def _snapshot(run: _Run) -> None:
    """Kunlik qoldiq: avval mahsulotlar yangilanadi (yangi qoldiq), keyin ``sku_daily`` ga Toshkent sanasi bilan."""
    await _products(run)
    shop = run.task.shops[0]
    async with run.write() as conn:
        run.counts[shop.id].written = await store.snapshot(
            conn, run.org_id, shop.id, _local(run.started).date()
        )


async def _invoices(run: _Run) -> None:
    """Postavkalar ro'yxati; tarkibi — yangi yoki holati o'zgarganlari uchun bir marta (kursorda: id → holat)."""
    shop = run.task.shops[0]
    cursor = run.cursors[shop.id]
    fetched_items: dict[str, str] = dict(cursor.get("items") or {})
    invoices: list[dict[str, Any]] = []
    async for page in run.client.invoices(shop.external_id):
        rows = run.map_rows(shop, page.rows, mapping.invoice)
        async with run.write() as conn:
            result = await store.upsert(
                conn, m.fbo_invoices, rows, ("org_id", "shop_id", "external_id")
            )
            run.counts[shop.id].written += result.written
        invoices += rows
    pending = [
        r for r in invoices if fetched_items.get(str(r["external_id"])) != (r["status"] or "")
    ][: run.settings.sync_invoice_items_per_run]
    for invoice in pending:
        items: list[dict[str, Any]] = []
        async for page in run.client.invoice_products(shop.external_id, invoice["external_id"]):
            items += mapping.invoice_items(page.rows)
        async with run.write() as conn:
            parent = (
                await store.ids_by_external(conn, m.fbo_invoices, shop.id, [invoice["external_id"]])
            )[invoice["external_id"]]
            skus = await store.ids_by_external(
                conn, m.mp_skus, shop.id, (i["sku_external_id"] for i in items)
            )
            rows = [
                {
                    **i,
                    "org_id": run.org_id,
                    "invoice_id": parent,
                    "sku_id": skus.get(i["sku_external_id"]),
                }
                for i in items
            ]
            run.counts[shop.id].written += await store.replace_children(
                conn, m.fbo_invoice_items, "invoice_id", parent, rows
            )
            fetched_items[str(invoice["external_id"])] = invoice["status"] or ""
            cursor["items"] = fetched_items
            await run.save_cursor(conn, shop.id)


async def _returns(run: _Run) -> None:
    """Qaytarishlar — butun akkaunt (``/v1/return``, 08 §8): qator ``shopId`` bo'yicha do'konga; tarkibi — yangi
    yoki o'zgargan qaytarishlarda almashtiriladi."""
    by_external = {s.external_id: s for s in run.task.shops}
    async for page in run.client.returns():
        grouped: dict[UUID, list[dict[str, Any]]] = {}
        for raw in page.rows:
            shop = by_external.get(mapping.as_int(raw.get("shopId")) or -1)
            if shop is not None:  # boshqa (faol bo'lmagan) do'kon — yozilmaydi
                grouped.setdefault(shop.id, []).append(raw)
        async with run.write() as conn:
            for shop in run.task.shops:
                raws = grouped.get(shop.id, [])
                rows = run.map_rows(shop, raws, mapping.return_row)
                result = await store.upsert(
                    conn, m.mp_returns, rows, ("org_id", "shop_id", "external_id")
                )
                counts = run.counts[shop.id]
                counts.written += result.written
                changed = {key[2] for key in result.ids}
                skus = await store.ids_by_external(
                    conn,
                    m.mp_skus,
                    shop.id,
                    (i["sku_external_id"] for raw in raws for i in mapping.return_items(raw)),
                )
                for raw in raws:
                    ext = mapping.as_int(raw.get("id"))
                    if ext not in changed:
                        continue
                    parent = result.ids[(run.org_id, shop.id, ext)]
                    items = [
                        {
                            **i,
                            "org_id": run.org_id,
                            "return_id": parent,
                            "sku_id": skus.get(i["sku_external_id"]),
                        }
                        for i in mapping.return_items(raw)
                    ]
                    counts.written += await store.replace_children(
                        conn, m.mp_return_items, "return_id", parent, items
                    )


HANDLERS: dict[Kind, Callable[[_Run], Awaitable[None]]] = {
    Kind.SHOPS: _shops,
    Kind.ORDERS: _orders,
    Kind.EXPENSES: _expenses,
    Kind.PRODUCTS: _products,
    Kind.SNAPSHOT: _snapshot,
    Kind.INVOICES: _invoices,
    Kind.RETURNS: _returns,
}


# --- Kirish nuqtasi ------------------------------------------------------------------------------


async def _load(
    rt: Runtime, org_id: UUID, account_id: UUID, now: datetime
) -> tuple[Row[Any], list[ShopRef], dict[tuple[UUID, Kind], State]] | str:
    async with org_transaction(rt.engine, org_id) as conn:
        account = (
            await conn.execute(
                select(m.mp_accounts).where(m.mp_accounts.c.id == account_id).with_for_update()
            )
        ).first()
        if account is None or account.token_encrypted is None:
            return "disconnected"
        if account.status == "invalid":
            return "invalid"
        if account.sync_paused_until is not None and account.sync_paused_until > now:
            return "paused"
        if account.status in ("quota_exhausted", "waf_blocked"):
            probe_after = timedelta(minutes=rt.settings.sync_probe_minutes)
            if account.checked_at is not None and now - account.checked_at < probe_after:
                return str(account.status)
            # Sinov: keyingisi yana ``sync_probe_minutes`` dan keyin (ishchilar orasida bitta).
            await conn.execute(
                update(m.mp_accounts).where(m.mp_accounts.c.id == account_id).values(checked_at=now)
            )
        shops = [
            ShopRef(r.id, r.external_id)
            for r in await conn.execute(
                select(m.shops.c.id, m.shops.c.external_id)
                .where(m.shops.c.account_id == account_id, m.shops.c.active)
                .order_by(m.shops.c.created_at, m.shops.c.external_id)
            )
        ]
        if not shops:
            return "no_shops"
        states = {
            (r.shop_id, Kind(r.kind)): State(
                r.last_success_at,
                r.last_attempt_at,
                r.last_status,
                r.failures,
                dict(r.cursor or {}),
            )
            for r in await conn.execute(
                select(m.sync_state).where(m.sync_state.c.shop_id.in_([s.id for s in shops]))
            )
        }
    return account, shops, states


async def sync_account(
    rt: Runtime,
    org_id: UUID,
    account_id: UUID,
    *,
    trigger: Trigger = Trigger.SCHEDULE,
    kinds: Sequence[Kind] | None = None,
) -> AccountResult:
    """Akkaunt sinxroni: vaqti kelgan (yoki ``kinds`` — majburiy) turlar. Xatolar natijada va bazada; istisno
    faqat kutilmagan DB xatosida."""
    now = rt.clock()
    gate = await health.gate(rt.engine, rt.settings, now)
    if gate is health.Gate.PAUSED:
        return AccountResult("skipped", "outage")
    loaded = await _load(rt, org_id, account_id, now)
    if isinstance(loaded, str):
        return AccountResult("skipped", loaded)
    row, shops, states = loaded
    forced = kinds if kinds is not None else (USER_KINDS if trigger is Trigger.USER else None)
    tasks = plan(rt.settings, shops, states, now, forced)
    if not tasks:
        return AccountResult("idle")
    try:
        token = rt.cipher.decrypt(
            row.token_encrypted, row.key_version, account_aad(org_id, account_id)
        )
    except CipherError as exc:
        _log.error("mp_token_unreadable", account_id=str(account_id), reason=str(exc))
        async with org_transaction(rt.engine, org_id) as conn:
            await conn.execute(
                update(m.mp_accounts)
                .where(m.mp_accounts.c.id == account_id)
                .values(sync_paused_until=now + timedelta(days=1), updated_at=now)
            )
        return AccountResult("skipped", "token_unreadable")
    account = _Account(row.id, row.status, row.quota_remaining, row.auth_failures, token)
    priority = Priority.BACKGROUND if trigger is Trigger.SCHEDULE else Priority.USER
    async with UzumClient(
        token,
        base_url=rt.settings.uzum_base_url,
        timeout=rt.settings.uzum_timeout_seconds,
        transport=rt.transport,
        limiter=rt.limiter,
        key_id=str(account_id),
        priority=priority,
        quota_reserve=rt.settings.uzum_quota_reserve,
        # Kunlik qoldiq yangilanadi: saqlangan qiymat eskirgan bo'lishi mumkin — birinchi javobdan olinadi.
        quota_remaining=None,
        sleep=rt.sleep,
    ) as client:
        job = _Job(
            rt,
            org_id,
            account,
            client,
            trigger,
            states,
            await health.outage(rt.engine),
            gate is health.Gate.PROBE,
        )
        try:
            for task in tasks:
                await job.run(task)
        except _Stop:
            pass
        finally:
            await job.finish()
    _log.info(
        "sync_account_done",
        account_id=str(account_id),
        trigger=trigger.value,
        runs=len(job.runs),
        errors=sum(r.status == "error" for r in job.runs),
    )
    return AccountResult("done", runs=job.runs)
