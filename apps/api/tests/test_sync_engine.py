"""B2.6 sinxron ishlari (haqiqiy PostgreSQL + soxta Uzum): to'liq tarix, inkremental, chuqur, uzilish, kursor bilan
davom etish, upsert qoidalari (dublikat yo'q, ``NULL`` bilan ustidan yozilmaydi, sotuvchi kiritgani o'zgarmaydi),
bog'lanishlar, snapshot, postavka tarkibi, qaytarishlar, xato turlari va akkaunt holati, ``sync_runs``/``sync_state``.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import psycopg
import pytest
import sellerfake as sf
from sellerfake import BOTH, NOW, TOKEN, A, B, Clock, admin, create_account, runtime, seller
from upapi.sync import engine as eng
from upapi.sync import health
from upapi.uzum import client as uz


@pytest.fixture(autouse=True)
def _no_outage(db: dict[str, str]) -> Iterator[None]:
    """``provider_health`` — umumiy (tashkilotsiz) holat: har test toza boshlanadi."""
    admin(db, "DELETE FROM provider_health")
    yield
    admin(db, "DELETE FROM provider_health")


def sync(run: Any, account: sf.Account, **kw: Any) -> eng.AccountResult:
    return run(lambda rt: eng.sync_account(rt, account.org_id, account.account_id, **kw))


def by_kind(result: eng.AccountResult, shop: uuid.UUID) -> dict[str, eng.RunSummary]:
    return {r.kind.value: r for r in result.runs if r.shop_id == shop}


def count(db: dict[str, str], table: str, account: sf.Account) -> int:
    return admin(db, f"SELECT count(*) FROM {table} WHERE org_id = %s", [account.org_id])[0][0]


# --- To'liq birinchi sinxron -----------------------------------------------------------------------


def test_first_sync_loads_everything(db: dict[str, str]) -> None:
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A, B])
        result = sync(run, account, trigger=eng.Trigger.CONNECT)
    assert result.status == "done"
    a, b = account.shops[A], account.shops[B]
    runs = by_kind(result, a)
    assert set(runs) == {"shops", "returns", "orders", "expenses", "products", "invoices"}
    assert runs["orders"].mode is eng.Mode.HISTORY and runs["orders"].status == "ok"
    assert (runs["orders"].fetched, runs["orders"].written) == (3, 3)
    assert runs["expenses"].written == 3
    assert by_kind(result, b)["expenses"].status == "ok"  # xarajat yo'qligi ogohlantirish emas
    assert by_kind(result, b)["returns"].fetched == 1

    assert count(db, "sale_items", account) == 4
    assert count(db, "mp_expenses", account) == 3
    assert count(db, "mp_products", account) == 2
    assert count(db, "mp_skus", account) == 3
    assert count(db, "fbo_invoices", account) == 1
    assert count(db, "fbo_invoice_items", account) == 1
    assert count(db, "mp_returns", account) == 2  # boshqa do'kon qaytarishi yozilmadi
    assert count(db, "mp_return_items", account) == 2

    # Do'kon: tarix to'liq, birinchi sotuv (Toshkent sanasi).
    shop = admin(db, "SELECT history_status, first_sale_on FROM shops WHERE id = %s", [a])[0]
    assert shop == ("full", (NOW - timedelta(days=100)).date())
    # Sotuv → SKU (skuTitle = skuFullTitle), logistika xarajati → sotuv qatori, tarkiblar → SKU.
    linked = admin(
        db,
        "SELECT s.external_id, k.external_id FROM sale_items s JOIN mp_skus k ON k.id = s.sku_id "
        "WHERE s.shop_id = %s ORDER BY 1",
        [a],
    )
    assert linked == [(1, 5011), (2, 5012), (3, 5011)]
    assert admin(
        db,
        "SELECT s.external_id FROM mp_expenses e JOIN sale_items s ON s.id = e.sale_item_id "
        "WHERE e.external_id = 102 AND e.org_id = %s",
        [account.org_id],
    ) == [(3,)]
    assert admin(
        db,
        "SELECT count(*) FROM fbo_invoice_items WHERE sku_id IS NOT NULL AND org_id = %s",
        [account.org_id],
    ) == [(1,)]
    # Xarajat: kirill kod normallashgan, toifa, reklama summasi Decimal.
    rows = admin(
        db,
        "SELECT external_id, raw_code, code, category, amount, excluded FROM mp_expenses "
        "WHERE org_id = %s ORDER BY external_id",
        [account.org_id],
    )
    assert [r[2:4] for r in rows] == [
        ("C000003", "storage"),
        ("LOGISTICS-VOLUME", "logistics"),
        ("Y000120", "advertising"),
    ]
    assert rows[0][1] == "С000003" and rows[1][5] == "not_expense"
    # Sotuv qatori: pul Decimal, xom JSON saqlangan.
    sale = admin(
        db,
        "SELECT sell_price, commission, logistics_fee, seller_profit, raw->>'skuTitle', sku_title "
        "FROM sale_items WHERE external_id = 3 AND org_id = %s",
        [account.org_id],
    )[0]
    assert [str(v) for v in sale[:4]] == ["100000.00", "40000.00", "4000.00", "160000.00"]
    assert sale[4] == sale[5] == "SKU-A"
    # Holat jadvali: har do'kon × tur.
    states = admin(
        db,
        "SELECT kind, last_status, cursor->>'history' FROM sync_state WHERE shop_id = %s ORDER BY kind",
        [a],
    )
    assert ("orders", "ok", "full") in states and ("expenses", "ok", "full") in states
    runs_db = admin(
        db,
        "SELECT kind, status, trigger, requests > 0 FROM sync_runs WHERE shop_id = %s ORDER BY kind",
        [a],
    )
    assert all(r[1] == "ok" and r[2] == "connect" and r[3] for r in runs_db)
    quota = admin(
        db, "SELECT quota_remaining, status FROM mp_accounts WHERE id = %s", [account.account_id]
    )
    assert quota == [(90_000, "active")]


def test_resync_creates_no_duplicates(db: dict[str, str]) -> None:
    """02 M3: bir xil ma'lumotni qayta olish dublikat yaratmaydi; o'zgarmagan qator qayta yozilmaydi."""
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A, B])
        sync(run, account)
        before = {t: count(db, t, account) for t in ("sale_items", "mp_expenses", "mp_skus")}
        again = sync(run, account, kinds=list(eng.Kind))
    after = {t: count(db, t, account) for t in ("sale_items", "mp_expenses", "mp_skus")}
    assert before == after
    runs = by_kind(again, account.shops[A])
    assert (
        runs["orders"].mode is eng.Mode.INCREMENTAL
    )  # tarix hozirgina — chuqur ham shu payt hisoblanadi
    assert (runs["orders"].fetched, runs["orders"].written) == (1, 0)
    assert runs["products"].written == 0 and runs["returns"].written == 0


def test_null_does_not_overwrite_and_seller_data_kept(db: dict[str, str]) -> None:
    """Uzum bermagan maydon ``NULL`` bilan ustidan yozilmaydi; sotuvchi kiritgani (taxallus, rang, SKU → tovar
    bog'lanishi) sinxron tomonidan o'zgarmaydi; holat o'zgarishi yoziladi."""
    fake = seller()
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        a = account.shops[A]
        item = uuid.uuid4()
        admin(
            db,
            "INSERT INTO items (id, org_id, name) VALUES (%s, %s, 'Ko''ylak')",
            [item, account.org_id],
        )
        admin(
            db,
            "UPDATE mp_skus SET item_id = %s WHERE shop_id = %s AND external_id = 5011",
            [item, a],
        )
        admin(db, "UPDATE shops SET alias = 'BD', color = '#112233' WHERE id = %s", [a])
        changed = sf.order(
            3, A, NOW - timedelta(days=1), "SKU-A", amount=2, status="PARTIALLY_CANCELLED"
        )
        del changed["sellerProfit"]
        changed["purchasePrice"] = None
        fake.orders[A][2] = changed
        fake.products[A][0]["skuList"][0]["quantityActive"] = None
        fake.products[A][0]["skuList"][0]["price"] = 110_000
        fake.shops[0]["name"] = "byDurii yangi"
        result = sync(run, account, kinds=[eng.Kind.ORDERS, eng.Kind.PRODUCTS, eng.Kind.SHOPS])
    assert by_kind(result, a)["orders"].written == 1
    sale = admin(
        db,
        "SELECT status, seller_profit, purchase_price FROM sale_items WHERE shop_id = %s AND external_id = 3",
        [a],
    )[0]
    assert sale[0] == "PARTIALLY_CANCELLED" and sale[1] is not None and sale[2] is not None
    sku = admin(
        db,
        "SELECT item_id, qty_active, price FROM mp_skus WHERE shop_id = %s AND external_id = 5011",
        [a],
    )[0]
    assert sku[0] == item and sku[1] == 10 and str(sku[2]) == "110000.00"
    assert admin(db, "SELECT name, alias, color, active FROM shops WHERE id = %s", [a]) == [
        ("byDurii yangi", "BD", "#112233", True)
    ]


def test_expense_status_change_recomputes_derived(db: dict[str, str]) -> None:
    fake = seller()
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        query = "SELECT excluded FROM mp_expenses WHERE external_id = 103 AND org_id = %s"
        fake.expenses[A][2]["status"] = "CANCELED"
        sync(run, account, kinds=[eng.Kind.EXPENSES])
        assert admin(db, query, [account.org_id]) == [("status",)]
        fake.expenses[A][2]["status"] = "CONFIRMED"
        sync(run, account, kinds=[eng.Kind.EXPENSES])
    assert admin(db, query, [account.org_id]) == [(None,)]


# --- Tarix: cheklangan va davom ettirish -------------------------------------------------------------


def test_history_falls_back_to_shorter_window(db: dict[str, str]) -> None:
    """Uzum 2020-01-01 dan bermasa — legacy kabi qisqaroq oyna; do'konda "cheklangan" belgisi."""
    fake = seller(oldest=sf.ms(NOW - timedelta(days=400)))
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        result = sync(run, account)
    assert by_kind(result, account.shops[A])["orders"].status == "ok"
    assert admin(db, "SELECT history_status FROM shops WHERE id = %s", [account.shops[A]]) == [
        ("limited:365",)
    ]
    assert count(db, "sale_items", account) == 3


def test_history_resumes_from_cursor(db: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """M2: yuklash uzilsa qolgan joydan davom etadi (sahifa va hajm kursorda, ma'lumot bilan bitta tranzaksiyada)."""
    monkeypatch.setattr(uz, "ORDERS", dataclasses.replace(uz.ORDERS, sizes=(2,)))
    fake = seller()
    fake.orders[A] += [sf.order(i, A, NOW - timedelta(days=i), "SKU-A") for i in range(20, 25)]
    fake.fail, fake.fail_from_page = {"orders": "5xx"}, {"orders": 2}
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        first = sync(run, account, kinds=[eng.Kind.ORDERS])
        a = account.shops[A]
        assert by_kind(first, a)["orders"].status == "error"
        assert by_kind(first, a)["orders"].error == "upstream"
        assert count(db, "sale_items", account) == 4  # 2 sahifa yozildi
        cursor = admin(
            db, "SELECT cursor FROM sync_state WHERE shop_id = %s AND kind = 'orders'", [a]
        )[0][0]
        assert (
            cursor["resume"]["page"] == 2
            and cursor["resume"]["size"] == 2
            and "history" not in cursor
        )
        fake.fail = {}
        fake.seen.clear()
        second = sync(run, account, kinds=[eng.Kind.ORDERS])
    assert by_kind(second, a)["orders"].mode is eng.Mode.HISTORY
    assert by_kind(second, a)["orders"].status == "ok"
    pages = [int(r.url.params["page"]) for r in fake.requests("orders")]
    assert pages[0] == 2  # boshidan emas
    assert count(db, "sale_items", account) == 8
    cursor = admin(db, "SELECT cursor FROM sync_state WHERE shop_id = %s AND kind = 'orders'", [a])[
        0
    ][0]
    assert cursor["history"] == "full" and "resume" not in cursor


# --- Usullar: inkremental, chuqur, uzilish -------------------------------------------------------------


def test_incremental_and_deep_windows(db: dict[str, str]) -> None:
    fake = seller()
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        a = account.shops[A]
        clock.advance(minutes=16)
        fake.seen.clear()
        result = sync(run, account)
        orders = by_kind(result, a)["orders"]
        assert orders.mode is eng.Mode.INCREMENTAL
        frm = int(fake.requests("orders")[0].url.params["dateFrom"])
        assert frm == sf.ms(
            clock.now - timedelta(days=3)
        )  # oxirgi muvaffaqiyat yaqin — 3 kunlik oyna
        assert "expenses" not in by_kind(result, a)  # soatiga bir marta
        clock.advance(hours=25)
        fake.seen.clear()
        deep = by_kind(sync(run, account), a)
    assert deep["orders"].mode is eng.Mode.DEEP and deep["expenses"].mode is eng.Mode.DEEP
    frm = int(fake.requests("orders")[0].url.params["dateFrom"])
    assert frm == sf.ms(clock.now - timedelta(days=45))


def test_incremental_covers_gap_since_last_success(db: dict[str, str]) -> None:
    fake = seller()
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        clock.advance(days=5)  # ishchi 5 kun ishlamadi
        fake.seen.clear()
        result = sync(run, account, trigger=eng.Trigger.USER)
    assert by_kind(result, account.shops[A])["orders"].mode is eng.Mode.INCREMENTAL
    frm = int(fake.requests("orders")[0].url.params["dateFrom"])
    assert frm == sf.ms(NOW - timedelta(days=1))  # min(hozir − 3 kun, oxirgi muvaffaqiyat − 1 kun)


def test_outage_pause_probe_and_fill(db: dict[str, str]) -> None:
    """03 §6: ko'p do'konda tarmoq xatosi → umumiy pauza; pauzada ish yo'q; pauza tugagach bitta sinov; tiklangach
    uzilish davri chuqur sinxron bilan to'ldiriladi."""
    fake = seller()
    other = seller(token="uzk-other-token-0002", shops=[{"id": 900_003, "name": "Boshqa"}])
    clock = Clock()
    with runtime(db, fake, clock) as run, runtime(db, other, clock) as run_other:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        second = create_account(db, sf.settings_for(db), other.token, [900_003])
        sync(run, account)
        sync(run_other, second)
        clock.advance(minutes=20)
        fake.fail = {"orders": "network"}
        other.fail = {"orders": "5xx"}
        failed = sync(run, account)
        assert by_kind(failed, account.shops[A])["orders"].error == "upstream"
        assert not run(
            lambda rt: health.outage(rt.engine)
        ).active  # bitta do'kon — hali uzilish emas
        sync(run_other, second)
        state = run(lambda rt: health.outage(rt.engine))
        assert state.active and state.since == clock.now
        assert sync(run, account).reason == "outage"  # pauza
        fake.fail = other.fail = {}
        clock.advance(minutes=16)
        probe = sync(run, account)  # pauza tugadi — sinov
        assert probe.status == "done"
        assert sync(run_other, second).status in ("done", "idle")
        recovered = run(lambda rt: health.outage(rt.engine))
        assert not recovered.active and recovered.recovered_from == NOW + timedelta(minutes=20)
        clock.advance(minutes=16)
        fake.seen.clear()
        filled = by_kind(sync(run, account), account.shops[A])
    assert filled["orders"].mode is eng.Mode.OUTAGE
    frm = int(fake.requests("orders")[0].url.params["dateFrom"])
    assert frm == sf.ms(clock.now - timedelta(days=3) - timedelta(days=1))


def test_probe_is_exclusive(db: dict[str, str]) -> None:
    clock = Clock()
    with runtime(db, seller(), clock) as run:
        settings = sf.settings_for(db)
        for shop in (uuid.uuid4(), uuid.uuid4()):
            run(lambda rt, s=shop: health.record_failure(rt.engine, settings, s, clock.now))
        assert run(lambda rt: health.gate(rt.engine, settings, clock.now)) is health.Gate.PAUSED
        clock.advance(minutes=15)
        assert run(lambda rt: health.gate(rt.engine, settings, clock.now)) is health.Gate.PROBE
        assert run(lambda rt: health.gate(rt.engine, settings, clock.now)) is health.Gate.PAUSED
        assert run(lambda rt: health.record_success(rt.engine, clock.now)) is True
        assert run(lambda rt: health.record_success(rt.engine, clock.now)) is False
        assert run(lambda rt: health.gate(rt.engine, settings, clock.now)) is health.Gate.OPEN


def test_old_failures_do_not_start_outage(db: dict[str, str]) -> None:
    clock = Clock()
    with runtime(db, seller(), clock) as run:
        settings = sf.settings_for(db)
        run(lambda rt: health.record_failure(rt.engine, settings, uuid.uuid4(), clock.now))
        clock.advance(minutes=6)
        assert (
            run(lambda rt: health.record_failure(rt.engine, settings, uuid.uuid4(), clock.now))
            is False
        )


# --- Xatolar va akkaunt holati -----------------------------------------------------------------------


def test_auth_errors_three_times_mark_invalid(db: dict[str, str]) -> None:
    """02 M3: ketma-ket 3 ta JSON 401/403 → "kalit yaroqsiz" (audit bilan); keyin sinxron to'xtaydi."""
    fake = seller(fail={"shops": "auth"})
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        for attempt in range(3):
            result = sync(run, account)
            assert result.runs[0].error == "auth" and len(result.runs) == 1  # akkaunt ishi to'xtadi
            status = admin(
                db,
                "SELECT status, auth_failures FROM mp_accounts WHERE id = %s",
                [account.account_id],
            )
            assert status == [("invalid" if attempt == 2 else "active", attempt + 1)]
            clock.advance(days=1, minutes=1)
        assert sync(run, account).reason == "invalid"
    audit = admin(
        db,
        "SELECT action, before, after, actor_user_id FROM audit_log WHERE entity_id = %s",
        [account.account_id],
    )
    assert audit == [("account.sync_status", {"status": "active"}, {"status": "invalid"}, None)]


def test_success_resets_auth_failures(db: dict[str, str]) -> None:
    fake = seller(fail={"shops": "token_not_found"})
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        fake.fail = {}
        clock.advance(days=1, minutes=1)
        sync(run, account)
    assert admin(
        db, "SELECT status, auth_failures FROM mp_accounts WHERE id = %s", [account.account_id]
    ) == [("active", 0)]


@pytest.mark.parametrize(("mode", "status"), [("waf", "waf_blocked"), ("quota", "quota_exhausted")])
def test_waf_and_quota_probe_every_30_minutes(db: dict[str, str], mode: str, status: str) -> None:
    fake = seller(fail={"shops": mode})
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        assert sync(run, account).runs[0].error == ("waf" if mode == "waf" else "quota")
        assert admin(db, "SELECT status FROM mp_accounts WHERE id = %s", [account.account_id]) == [
            (status,)
        ]
        fake.fail = {}
        clock.advance(minutes=10)
        assert sync(run, account).reason == status  # sinov vaqti emas
        clock.advance(minutes=21)
        result = sync(run, account)
    assert result.status == "done" and all(r.status != "error" for r in result.runs)
    assert admin(db, "SELECT status FROM mp_accounts WHERE id = %s", [account.account_id]) == [
        ("active",)
    ]


def test_quota_reserve_stops_background_not_user(db: dict[str, str]) -> None:
    """Kunlik qoldiq zaxiradan kam — fon ishi to'xtaydi ("skipped"), "Hozir yangilash" o'tadi."""
    fake = seller(quota=5_000)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        admin(
            db, "UPDATE mp_accounts SET quota_remaining = 5000 WHERE id = %s", [account.account_id]
        )
        background = sync(run, account)
        # Kvota qoldig'i har ishda birinchi javobdan (kunlik qoldiq yangilanadi): keyingi so'rov yuborilmaydi.
        assert [(r.kind.value, r.status, r.error) for r in background.runs] == [
            ("shops", "ok", None),
            ("returns", "skipped", "quota_reserved"),
        ]
        user = sync(run, account, trigger=eng.Trigger.USER)
    assert {r.kind for r in user.runs} == set(eng.USER_KINDS)
    assert all(r.status == "ok" for r in user.runs)


def test_bad_request_fails_one_kind_only(db: dict[str, str]) -> None:
    fake = seller(fail={"invoices": "bad_request"})
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account), account.shops[A])
    assert runs["invoices"].status == "error" and runs["invoices"].error == "bad_request"
    assert runs["products"].status == "ok" and runs["orders"].status == "ok"


def test_unreadable_row_is_warning(db: dict[str, str]) -> None:
    fake = seller()
    fake.orders[A].append(
        {"id": 99, "status": "TO_WITHDRAW", "date": sf.ms(NOW)}
    )  # orderId, narx yo'q
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account), account.shops[A])
    assert (runs["orders"].status, runs["orders"].error) == ("warning", "skipped:1")
    assert count(db, "sale_items", account) == 3


def test_empty_orders_is_warning(db: dict[str, str]) -> None:
    """03 §6: 0 ta obyekt bilan tugagan ish ham ogohlantirish (sotuv, mahsulot, do'kon)."""
    fake = seller()
    fake.orders[A] = []
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account), account.shops[A])
    assert (runs["orders"].status, runs["orders"].error) == ("warning", "empty")
    assert admin(db, "SELECT first_sale_on FROM shops WHERE id = %s", [account.shops[A]]) == [
        (None,)
    ]


def test_internal_error_recorded(db: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(run: Any) -> None:
        raise RuntimeError("kutilmagan")

    monkeypatch.setitem(eng.HANDLERS, eng.Kind.INVOICES, broken)
    with runtime(db, seller()) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account), account.shops[A])
    assert (runs["invoices"].status, runs["invoices"].error) == ("error", "internal")
    assert runs["returns"].status == "ok"


def test_interrupted_run_closed(db: dict[str, str]) -> None:
    with runtime(db, seller()) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        stale = uuid.uuid4()
        admin(
            db,
            "INSERT INTO sync_runs (id, org_id, shop_id, kind) VALUES (%s, %s, %s, 'orders')",
            [stale, account.org_id, account.shops[A]],
        )
        sync(run, account, kinds=[eng.Kind.ORDERS])
    assert admin(db, "SELECT status, error FROM sync_runs WHERE id = %s", [stale]) == [
        ("error", "interrupted")
    ]


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        (
            "UPDATE mp_accounts SET status = 'disconnected', token_encrypted = NULL, key_version = NULL, "
            "token_last4 = NULL WHERE id = %s",
            "disconnected",
        ),
        ("UPDATE shops SET active = false WHERE account_id = %s", "no_shops"),
        (
            "UPDATE mp_accounts SET sync_paused_until = now() + interval '1 day' WHERE id = %s",
            "paused",
        ),
    ],
)
def test_skipped_accounts(db: dict[str, str], sql: str, reason: str) -> None:
    fake = seller()
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        admin(db, sql, [account.account_id])
        assert sync(run, account).reason == reason
    assert fake.seen == []


def test_unreadable_token_pauses_account(db: dict[str, str]) -> None:
    fake = seller()
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        admin(
            db,
            "UPDATE mp_accounts SET token_encrypted = %s WHERE id = %s",
            [b"x" * 40, account.account_id],
        )
        assert sync(run, account).reason == "token_unreadable"
        assert sync(run, account).reason == "paused"
    assert fake.seen == []


def test_new_shop_from_uzum_added_and_synced(db: dict[str, str]) -> None:
    """M2: Uzum bergan yangi do'kon faol holda qo'shiladi va keyingi ishda sinxronlanadi."""
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        first = sync(run, account)
        new = admin(
            db,
            "SELECT id, active FROM shops WHERE org_id = %s AND external_id = %s",
            [account.org_id, B],
        )
        assert new and new[0][1] is True and {r.shop_id for r in first.runs} == {account.shops[A]}
        second = sync(run, account)
    assert {r.kind.value for r in second.runs if r.shop_id == new[0][0]} >= {"orders", "products"}


def test_idle_when_nothing_due(db: dict[str, str]) -> None:
    clock = Clock()
    with runtime(db, seller(), clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        clock.advance(minutes=5)
        assert sync(run, account).status == "idle"


# --- Snapshot, postavka tarkibi, qaytarishlar -----------------------------------------------------------


def test_daily_snapshot_after_2350_tashkent(db: dict[str, str]) -> None:
    clock = Clock(NOW.replace(hour=18, minute=55))  # Toshkent 23:55
    fake = seller()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account), account.shops[A])
        assert runs["snapshot"].status == "ok" and runs["snapshot"].written == 2
        fake.products[A][0]["skuList"][0]["quantityActive"] = 7
        clock.advance(minutes=3)
        assert "snapshot" not in by_kind(sync(run, account), account.shops[A])  # kuniga bir marta
        clock.advance(minutes=3)  # Toshkent ertasi kun 00:01 — vaqti hali kelmagan
        assert "snapshot" not in by_kind(sync(run, account), account.shops[A])
    rows = admin(
        db,
        "SELECT d.day, d.qty_active, d.price FROM sku_daily d JOIN mp_skus k ON k.id = d.sku_id "
        "WHERE k.shop_id = %s AND k.external_id = 5011",
        [account.shops[A]],
    )
    assert [(r[0].isoformat(), r[1], str(r[2])) for r in rows] == [("2026-10-24", 10, "100000.00")]


def test_invoice_items_fetched_once_per_status(db: dict[str, str]) -> None:
    fake = seller()
    clock = Clock()
    with runtime(db, fake, clock) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        assert len(fake.requests("invoice_products")) == 1
        created = admin(
            db,
            "SELECT created_on, status FROM fbo_invoices WHERE external_id = 601 AND org_id = %s",
            [account.org_id],
        )[0]
        assert created[0].isoformat() == "2026-10-24T05:30:00+00:00" and created[1] == "ACCEPTED"
        clock.advance(minutes=61)
        sync(run, account)
        assert len(fake.requests("invoice_products")) == 1  # holat o'zgarmadi — qayta so'ralmaydi
        fake.invoices[A][0]["invoiceStatus"]["value"] = "CLOSED"
        fake.invoice_products[601] = [sf.invoice_product(5011, 4), sf.invoice_product(5012, 1)]
        clock.advance(minutes=61)
        sync(run, account)
    assert len(fake.requests("invoice_products")) == 2
    assert admin(
        db,
        "SELECT sku_external_id, quantity_accepted FROM fbo_invoice_items WHERE org_id = %s ORDER BY 1",
        [account.org_id],
    ) == [(5011, 4), (5012, 1)]


def test_invoice_items_limited_per_run(db: dict[str, str]) -> None:
    fake = seller()
    fake.invoices[A] = [sf.invoice(600 + i) for i in range(5)]
    with runtime(db, fake, sync_invoice_items_per_run=2) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        sync(run, account)
        assert len(fake.requests("invoice_products")) == 2
        sync(run, account, kinds=[eng.Kind.INVOICES])
        sync(run, account, kinds=[eng.Kind.INVOICES])
        sync(run, account, kinds=[eng.Kind.INVOICES])
    assert len(fake.requests("invoice_products")) == 5


def test_returns_items_replaced_on_change(db: dict[str, str]) -> None:
    fake = seller(shops=BOTH)
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A, B])
        sync(run, account)
        fake.returns[0]["returnItems"] = [{"id": 1, "skuId": 5012, "amount": 1}]
        fake.returns[0]["status"] = "COMPLETED"
        again = sync(run, account, kinds=[eng.Kind.RETURNS])
    assert by_kind(again, account.shops[A])["returns"].written == 2  # qaytarish + tarkib
    assert by_kind(again, account.shops[B])["returns"].written == 0
    rows = admin(
        db,
        "SELECT r.type, r.status, i.sku_external_id, i.quantity, i.sku_id IS NOT NULL FROM mp_returns r "
        "JOIN mp_return_items i ON i.return_id = r.id WHERE r.shop_id = %s",
        [account.shops[A]],
    )
    assert rows == [("RETURN", "COMPLETED", 5012, 1, True)]


# --- Navbat (sof) ---------------------------------------------------------------------------------------


def _shops() -> list[eng.ShopRef]:
    return [eng.ShopRef(uuid.uuid4(), A), eng.ShopRef(uuid.uuid4(), B)]


def test_plan_first_time_everything_but_snapshot() -> None:
    settings = sf.settings_for({"app": "postgresql://x@y/z"})
    tasks = eng.plan(settings, _shops(), {}, NOW)
    kinds = [t.kind for t in tasks]
    assert kinds[:2] == [eng.Kind.SHOPS, eng.Kind.RETURNS]
    assert eng.Kind.SNAPSHOT not in kinds and kinds.count(eng.Kind.ORDERS) == 2


def test_plan_oldest_first_and_forced() -> None:
    settings = sf.settings_for({"app": "postgresql://x@y/z"})
    shops = _shops()
    done = eng.State(NOW, NOW, "ok", 0, {"history": "full"})
    stale = eng.State(
        NOW - timedelta(hours=3), NOW - timedelta(hours=3), "ok", 0, {"history": "full"}
    )
    states = {(s.id, k): done for s in shops for k in eng.Kind}
    states[(shops[1].id, eng.Kind.ORDERS)] = stale
    states[(shops[0].id, eng.Kind.ORDERS)] = dataclasses.replace(
        stale, last_success_at=NOW - timedelta(hours=1)
    )
    tasks = eng.plan(settings, shops, states, NOW)
    assert [(t.kind, t.shops[0]) for t in tasks] == [
        (eng.Kind.ORDERS, shops[1]),
        (eng.Kind.ORDERS, shops[0]),
    ]
    forced = eng.plan(settings, shops, states, NOW, forced=[eng.Kind.PRODUCTS])
    assert [t.kind for t in forced] == [eng.Kind.PRODUCTS, eng.Kind.PRODUCTS]


def test_is_due_rules() -> None:
    settings = sf.settings_for({"app": "postgresql://x@y/z"})
    history = eng.State(None, NOW - timedelta(minutes=2), "error", 1, {"resume": {"page": 3}})
    assert eng.is_due(settings, eng.Kind.ORDERS, history, NOW)  # tugallanmagan tarix — darhol davom
    assert eng.is_due(settings, eng.Kind.EXPENSES, None, NOW)
    recent = eng.State(NOW, NOW - timedelta(minutes=30), "ok", 0, {"history": "full"})
    assert not eng.is_due(settings, eng.Kind.EXPENSES, recent, NOW)
    assert eng.is_due(settings, eng.Kind.ORDERS, recent, NOW)
    late = NOW.replace(hour=18, minute=51)  # Toshkent 23:51
    assert not eng.is_due(settings, eng.Kind.SNAPSHOT, None, NOW)
    assert eng.is_due(settings, eng.Kind.SNAPSHOT, None, late)
    failed = eng.State(None, late, "error", 1, {})
    assert not eng.is_due(settings, eng.Kind.SNAPSHOT, failed, late + timedelta(minutes=1))
    assert eng.is_due(settings, eng.Kind.SNAPSHOT, failed, late + timedelta(minutes=2))
    assert not eng.is_due(
        settings, eng.Kind.SNAPSHOT, failed, late + timedelta(minutes=10)
    )  # 00:01


def test_sync_accounts_function(db: dict[str, str]) -> None:
    """Rejalashtiruvchi ro'yxati (``SECURITY DEFINER``, faqat id'lar): uzilgan, o'chirilgan tashkilot va faol
    do'konsiz akkauntlar yo'q; ilova roli boshqa jadvallarni baribir ko'rmaydi."""
    settings = sf.settings_for(db)
    live = create_account(db, settings, TOKEN, [A])
    gone = create_account(db, settings, TOKEN, [A])
    admin(db, "UPDATE orgs SET deleted_at = now() WHERE id = %s", [gone.org_id])
    idle = create_account(db, settings, TOKEN, [A])
    admin(db, "UPDATE shops SET active = false WHERE org_id = %s", [idle.org_id])
    with psycopg.connect(db["app"]) as conn:
        accounts = conn.execute("SELECT org_id, account_id FROM sync_accounts()").fetchall()
        assert conn.execute("SELECT count(*) FROM mp_accounts").fetchone() == (0,)  # RLS
    assert (live.org_id, live.account_id) in accounts
    assert all(acc[0] not in (gone.org_id, idle.org_id) for acc in accounts)


def test_history_rejected_everywhere_is_error(db: dict[str, str]) -> None:
    fake = seller(oldest=sf.ms(NOW + timedelta(days=1)))  # hech qaysi oynani bermaydi
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account, kinds=[eng.Kind.ORDERS]), account.shops[A])
    assert (runs["orders"].status, runs["orders"].error) == ("error", "bad_request")
    cursor = admin(db, "SELECT cursor FROM sync_state WHERE shop_id = %s", [account.shops[A]])
    assert cursor == [({},)]  # keyingi safar tarix yana boshidan


def test_product_without_id_is_skipped(db: dict[str, str]) -> None:
    fake = seller()
    fake.products[A].append({"title": "id'siz", "skuList": []})
    with runtime(db, fake) as run:
        account = create_account(db, sf.settings_for(db), TOKEN, [A])
        runs = by_kind(sync(run, account, kinds=[eng.Kind.PRODUCTS]), account.shops[A])
    assert (runs["products"].status, runs["products"].error) == ("warning", "skipped:1")
    assert count(db, "mp_products", account) == 1
