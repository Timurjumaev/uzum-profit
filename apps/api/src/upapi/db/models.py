"""Ma'lumotlar modeli (03-arxitektura.md §5): PostgreSQL, SQLAlchemy Core jadvallari.

Tashkilotlarni ajratish (ADR-012) ikki qavatli: ilova ``org_id`` bo'yicha filtrlaydi va PostgreSQL RLS
(``app.org_id``) ruxsat bermaydi. Qoidalar:

- Har **tashkilot jadvali** (``TENANT``) — ``org_id NOT NULL``, ``UNIQUE (org_id, id)``, RLS + FORCE.
- Tashkilot ichidagi bog'lanish — **kompozit FK** ``(org_id, x_id) → x (org_id, id)``: FK tekshiruvi RLS'ni
  chetlab o'tadi, kompozit kalit esa boshqa tashkilot qatoriga havolani imkonsiz qiladi.
- Unikal tabiiy kalitlar ``org_id`` bilan boshlanadi — boshqa tashkilot yozuvi borligi "dublikat" xatosi
  orqali ham bilinmaydi.
- **Global** ma'lumotnomalar (``GLOBAL``) — RLS'siz, ilova roli faqat o'qiydi.
- **Kirish** jadvallari (``AUTH``: sessiyalar, kodlar) — ilova roliga berilmaydi; faqat ``auth_*`` funksiyalari
  (``SECURITY DEFINER``, ``up_auth`` roli, 0002 migratsiyasi) orqali, OTP kodi yoki sessiya tokeni bilan.
- **Tizim** jadvallari (``SYSTEM``) — tashkilotga tegishli emas, sirsiz (masalan, Uzum uzilishi holati, B2.6);
  RLS'siz, ilova roli o'qiydi va yozadi (o'chirmaydi).

Pul ``numeric(18,2)`` (so'm), valyuta ``numeric(18,4)``, kurs ``numeric(18,6)``; vaqt ``timestamptz``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    Table,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

UZS = Numeric(18, 2)
FX = Numeric(18, 4)
RATE = Numeric(18, 6)
PCT = Numeric(7, 4)
TS = TIMESTAMP(timezone=True)

TENANT: list[str] = []  # RLS: org_id = app.org_id
GLOBAL: list[str] = []  # ilova roli: faqat SELECT
AUTH: list[str] = []  # ilova roliga berilmaydi
SYSTEM: list[str] = []  # tashkilotsiz tizim holati: ilova roli SELECT, INSERT, UPDATE
APPEND_ONLY: set[str] = set()  # ilova roli: UPDATE/DELETE yo'q


def _id() -> Column[Any]:
    return Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _times() -> list[Column[Any]]:
    return [
        Column("created_at", TS, nullable=False, server_default=func.now()),
        Column("updated_at", TS, nullable=False, server_default=func.now()),
    ]


def tenant(
    name: str,
    *columns: Any,
    refs: dict[str, tuple[str, bool]] | None = None,
    append_only: bool = False,
) -> Table:
    """Tashkilot jadvali. ``refs``: ustun → (ota jadval, NULL bo'lishi mumkinmi) — kompozit FK bilan."""
    refs = refs or {}
    cols: list[Any] = [
        _id(),
        Column(
            "org_id", UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
        ),
    ]
    for col, (_, nullable) in refs.items():
        cols.append(Column(col, UUID(as_uuid=True), nullable=nullable))
    cols += list(columns)
    cols += _times()
    cols.append(UniqueConstraint("org_id", "id"))
    for col, (parent, _) in refs.items():
        cols.append(
            ForeignKeyConstraint(
                ["org_id", col],
                [f"{parent}.org_id", f"{parent}.id"],
                name=f"fk_{name}_{col}",
                # Majburiy bog'lanish — ota bilan o'chadi; ixtiyoriy — ota o'chirilmaydi (NO ACTION).
                ondelete="CASCADE" if not refs[col][1] else None,
            )
        )
    TENANT.append(name)
    if append_only:
        APPEND_ONLY.add(name)
    return Table(name, metadata, *cols)


def global_table(name: str, *columns: Any) -> Table:
    GLOBAL.append(name)
    return Table(name, metadata, *columns)


def system_table(name: str, *columns: Any) -> Table:
    SYSTEM.append(name)
    return Table(name, metadata, *columns)


def check_in(column: str, values: tuple[str, ...]) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_allowed")


ROLES = ("owner", "manager", "accountant", "warehouse")

# --- Tashkilot va kirish ----------------------------------------------------------------------

orgs = Table(
    "orgs",
    metadata,
    _id(),
    Column("name", Text, nullable=False),
    Column("inn", Text),
    Column("language", Text, nullable=False, server_default="uz-Latn"),
    Column("timezone", Text, nullable=False, server_default="Asia/Tashkent"),
    Column("cost_method", Text, nullable=False, server_default="fifo"),
    # Sozlamalar (B4.8): ``lead_days`` (F25 standart muddatlar), ``cover_days`` (F27 qamrov) — ``upapi.orgsettings``.
    Column("settings", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    # F41 (ADR-033): boshlang'ich holat sanasi — undan oldingi sotuvlar tarixiy tannarxda; NULL — o'chirilgan.
    Column("cost_start_on", Date),
    Column("deleted_at", TS),
    *_times(),
    check_in("cost_method", ("fifo", "average")),
)
TENANT.append("orgs")  # RLS: id = app.org_id

users = Table(
    "users",
    metadata,
    _id(),
    Column("phone", Text, nullable=False, unique=True),
    Column("name", Text),
    Column("language", Text, nullable=False, server_default="uz-Latn"),
    Column("telegram_user_id", BigInteger, unique=True),
    Column("last_login_at", TS),
    *_times(),
    CheckConstraint("phone ~ '^\\+[1-9][0-9]{7,14}$'", name="phone_e164"),
)
# users: o'zi yoki joriy tashkilot a'zosi ko'rinadi (RLS siyosati migratsiyada).

sessions = Table(
    "sessions",
    metadata,
    _id(),
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    Column("token_hash", LargeBinary, nullable=False, unique=True),
    # Yangilangandan keyin eski token qisqa muddat ishlaydi (parallel so'rovlar chiqib ketmasin).
    Column("prev_token_hash", LargeBinary, index=True),
    Column("prev_valid_until", TS),
    Column("device", Text),
    Column("expires_at", TS, nullable=False),
    Column("revoked_at", TS),
    *_times(),
    Index(None, "user_id"),
)
otp_codes = Table(
    "otp_codes",
    metadata,
    _id(),
    Column("phone", Text, nullable=False),
    Column("code_hash", LargeBinary, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("expires_at", TS, nullable=False),
    Column("consumed_at", TS),
    *_times(),
    Index(None, "phone", "created_at"),
)
AUTH += ["sessions", "otp_codes"]

memberships = tenant(
    "memberships",
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    Column("role", Text, nullable=False),
    UniqueConstraint("org_id", "user_id"),
    check_in("role", ROLES),
)
invites = tenant(
    "invites",
    Column("phone", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("token_hash", LargeBinary, nullable=False, unique=True),
    Column("invited_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Column("expires_at", TS, nullable=False),
    Column("accepted_at", TS),
    check_in("role", ROLES),
)
audit_log = tenant(
    "audit_log",
    Column("actor_user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Column("action", Text, nullable=False),
    Column("entity", Text, nullable=False),
    Column("entity_id", UUID(as_uuid=True)),
    Column("before", JSONB),
    Column("after", JSONB),
    append_only=True,
)
# Cheklovlar (masalan, kalit urinishlari soni) va jurnal filtri.
Index(None, audit_log.c.org_id, audit_log.c.action, audit_log.c.created_at)

# --- Marketplace ------------------------------------------------------------------------------

MP_ACCOUNT_STATUSES = ("active", "invalid", "quota_exhausted", "waf_blocked", "disconnected")
TOKEN_STATE = (
    "(token_encrypted IS NULL) = (status = 'disconnected') "
    "AND (key_version IS NULL) = (token_encrypted IS NULL) "
    "AND (token_last4 IS NULL) = (token_encrypted IS NULL)"
)

mp_accounts = tenant(
    "mp_accounts",
    Column("provider", Text, nullable=False, server_default="uzum"),
    # AES-256-GCM (upapi.crypto): nonce || shifrmatn || teg; ochiq kalit hech qachon saqlanmaydi.
    # Uzilgan akkauntda (B2.4) kalit o'chiriladi — uchala ustun NULL.
    Column("token_encrypted", LargeBinary),
    Column("key_version", Integer),
    Column("token_last4", Text),
    Column("status", Text, nullable=False, server_default="active"),
    Column("quota_remaining", Integer),
    Column("checked_at", TS),
    # Sinxron (B2.6): ketma-ket JSON 401/403 soni (3 ta — "kalit yaroqsiz") va akkaunt sinxroni pauzasi.
    Column("auth_failures", Integer, nullable=False, server_default="0"),
    Column("sync_paused_until", TS),
    check_in("status", MP_ACCOUNT_STATUSES),
    CheckConstraint(TOKEN_STATE, name="token_state"),
)
shops = tenant(
    "shops",
    Column("external_id", BigInteger, nullable=False),
    Column("name", Text, nullable=False),
    Column("alias", Text),
    Column("color", Text),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("history_status", Text),
    Column("first_sale_on", Date),
    UniqueConstraint("org_id", "account_id", "external_id"),
    refs={"account_id": ("mp_accounts", False)},
)
SYNC_KINDS = ("shops", "orders", "expenses", "products", "snapshot", "invoices", "returns")
SYNC_RUN_STATUSES = ("running", "ok", "warning", "error", "skipped")
SYNC_TRIGGERS = ("schedule", "user", "connect")
SYNC_MODES = ("full", "history", "incremental", "deep", "outage")

sync_state = tenant(
    "sync_state",
    Column("kind", Text, nullable=False),
    Column("last_success_at", TS),
    Column("cursor", JSONB),
    # B2.6: navbat va "Ma'lumotlar holati" uchun oxirgi urinish (muvaffaqiyatli yoki yo'q).
    Column("last_attempt_at", TS),
    Column("last_status", Text),
    Column("last_error", Text),
    Column("failures", Integer, nullable=False, server_default="0"),
    UniqueConstraint("org_id", "shop_id", "kind"),
    check_in("kind", SYNC_KINDS),
    refs={"shop_id": ("shops", False)},
)
sync_runs = tenant(
    "sync_runs",
    Column("kind", Text, nullable=False),
    Column("started_at", TS, nullable=False, server_default=func.now()),
    Column("finished_at", TS),
    Column("status", Text, nullable=False, server_default="running"),
    Column("fetched", Integer, nullable=False, server_default="0"),
    Column("written", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Column("http_status", Integer),
    # B2.6: progress (Uzum aytgan jami), sarflangan so'rovlar, kim boshlagan va qaysi usulda.
    Column("total", Integer),
    Column("requests", Integer, nullable=False, server_default="0"),
    Column("trigger", Text, nullable=False, server_default="schedule"),
    Column("mode", Text),
    check_in("kind", SYNC_KINDS),
    check_in("status", SYNC_RUN_STATUSES),
    check_in("trigger", SYNC_TRIGGERS),
    check_in("mode", SYNC_MODES),
    refs={"shop_id": ("shops", False)},
)
Index(None, sync_runs.c.org_id, sync_runs.c.shop_id, sync_runs.c.kind, sync_runs.c.started_at)
# Uzum uzilishi (03 §6): bir necha do'konda bir vaqtda tarmoq/5xx xatosi → umumiy pauza va vaqti-vaqti bilan bitta
# sinov; tiklangach uzilish davri chuqur sinxron bilan to'ldiriladi. Tashkilotsiz, sirsiz: ``failures`` — do'kon
# uuid'i → oxirgi xato vaqti (ISO).
provider_health = system_table(
    "provider_health",
    Column("provider", Text, primary_key=True),
    Column("outage_since", TS),
    Column("paused_until", TS),
    Column("failures", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("recovered_from", TS),
    Column("recovered_at", TS),
    Column("updated_at", TS, nullable=False, server_default=func.now()),
)

# --- Katalog ----------------------------------------------------------------------------------

items = tenant(
    "items",
    Column("name", Text, nullable=False),
    Column("image_url", Text),
    Column("weight_g", Integer),
    Column("length_mm", Integer),
    Column("width_mm", Integer),
    Column("height_mm", Integer),
    Column("is_sim", Boolean, nullable=False, server_default="false"),
)
mp_products = tenant(
    "mp_products",
    Column("external_id", BigInteger, nullable=False),
    Column("title", Text),
    Column("category", Text),
    Column("raw", JSONB),
    UniqueConstraint("org_id", "shop_id", "external_id"),
    refs={"shop_id": ("shops", False)},
)
mp_skus = tenant(
    "mp_skus",
    Column("external_id", BigInteger, nullable=False),
    Column("sku_code", Text),
    Column("barcode", Text),
    Column("article", Text),
    Column("ikpu", Text),
    Column("price", UZS),
    Column("commission_pct", PCT),
    Column("qty_active", Integer),
    Column("qty_fbs", Integer),
    Column("qty_defected", Integer),
    Column("qty_pending", Integer),
    Column("qty_sold", Integer),
    Column("qty_returned", Integer),
    Column("avg_daily_sales", Numeric(12, 4)),
    Column("rank", Text),
    Column("storage_price", UZS),
    Column("status", Text),
    Column("raw", JSONB),
    UniqueConstraint("org_id", "shop_id", "external_id"),
    refs={
        "shop_id": ("shops", False),
        "product_id": ("mp_products", True),
        "item_id": ("items", True),
    },
)
# Sotuv qatori SKU'ga ``skuTitle`` = ``skuFullTitle`` (``sku_code``) orqali bog'lanadi (legacy kabi).
Index(None, mp_skus.c.org_id, mp_skus.c.shop_id, mp_skus.c.sku_code)
Index(None, mp_skus.c.org_id, mp_skus.c.item_id)
sku_daily = tenant(
    "sku_daily",
    Column("day", Date, nullable=False),
    Column("qty_active", Integer),
    Column("qty_fbs", Integer),
    Column("qty_defected", Integer),
    Column("qty_pending", Integer),
    Column("price", UZS),
    Column("commission_pct", PCT),
    UniqueConstraint("org_id", "sku_id", "day"),
    refs={"sku_id": ("mp_skus", False)},
)

# --- Uzum faktlari ----------------------------------------------------------------------------

sale_items = tenant(
    "sale_items",
    Column("external_id", BigInteger, nullable=False),
    Column("order_id", BigInteger, nullable=False),
    Column("status", Text, nullable=False),
    Column("ordered_at", TS, nullable=False),
    Column("sell_price", UZS, nullable=False),
    Column("amount", Integer, nullable=False),
    Column("commission", UZS, nullable=False, server_default="0"),
    Column("logistics_fee", UZS, nullable=False, server_default="0"),
    Column("seller_profit", UZS),
    Column("amount_returns", Integer, nullable=False, server_default="0"),
    Column("return_cause", Text),
    Column("purchase_price", UZS),  # faqat ma'lumot uchun (ADR-016)
    Column("raw", JSONB),
    # B2.6: SKU bog'lanishi (``skuTitle``), mahsulot va topshirilgan vaqt (``dateIssued``).
    Column("sku_title", Text),
    Column("product_external_id", BigInteger),
    Column("issued_at", TS),
    UniqueConstraint("org_id", "shop_id", "order_id", "external_id"),
    refs={"shop_id": ("shops", False), "sku_id": ("mp_skus", True)},
)
Index(None, sale_items.c.org_id, sale_items.c.shop_id, sale_items.c.ordered_at)
Index(None, sale_items.c.org_id, sale_items.c.sku_id)  # B2.8: tovar bo'yicha sotuvlar (SKU → item)
expense_codes = global_table(
    "expense_codes",
    Column("code", Text, primary_key=True),
    Column("category", Text, nullable=False),
    Column("name_uz", Text),
    Column("name_ru", Text),
    Column("in_pnl", Boolean, nullable=False, server_default="true"),
    Column("match", Text, nullable=False, server_default="exact"),
    check_in("match", ("exact", "prefix", "keyword", "source")),
)
mp_expenses = tenant(
    "mp_expenses",
    Column("external_id", BigInteger, nullable=False),
    Column("raw_code", Text),
    Column("code", Text),
    Column("category", Text, nullable=False),
    Column("status", Text),
    Column("type", Text, nullable=False),
    Column("amount", UZS, nullable=False),
    Column("name", Text),
    Column("order_external_id", BigInteger),
    Column("item_external_id", BigInteger),
    Column("excluded", Text),
    Column("created_on", TS, nullable=False),
    Column("raw", JSONB),
    UniqueConstraint("org_id", "shop_id", "external_id"),
    refs={"shop_id": ("shops", False), "sale_item_id": ("sale_items", True)},
)
Index(None, mp_expenses.c.org_id, mp_expenses.c.shop_id, mp_expenses.c.created_on)
fbo_invoices = tenant(
    "fbo_invoices",
    Column("external_id", BigInteger, nullable=False),
    Column("number", BigInteger),
    Column("status", Text),
    Column("created_on", TS),
    Column("full_price", UZS),
    Column("accepted", Integer),
    Column("to_stock", Integer),
    Column("raw", JSONB),
    UniqueConstraint("org_id", "shop_id", "external_id"),
    refs={"shop_id": ("shops", False)},
)
fbo_invoice_items = tenant(
    "fbo_invoice_items",
    Column("sku_external_id", BigInteger, nullable=False),
    Column("quantity_to_stock", Integer, nullable=False, server_default="0"),
    Column("quantity_accepted", Integer, nullable=False, server_default="0"),
    refs={"invoice_id": ("fbo_invoices", False), "sku_id": ("mp_skus", True)},
)
mp_returns = tenant(
    "mp_returns",
    Column("external_id", BigInteger, nullable=False),
    Column("type", Text, nullable=False),
    Column("status", Text),
    Column("created_on", TS),
    Column("raw", JSONB),
    UniqueConstraint("org_id", "shop_id", "external_id"),
    check_in("type", ("RETURN", "DEFECTED", "FBS")),
    refs={"shop_id": ("shops", False)},
)
mp_return_items = tenant(
    "mp_return_items",
    Column("sku_external_id", BigInteger, nullable=False),
    Column("quantity", Integer, nullable=False),
    refs={"return_id": ("mp_returns", False), "sku_id": ("mp_skus", True)},
)

# --- Xarid va ombor ---------------------------------------------------------------------------

suppliers = tenant(
    "suppliers",
    Column("name", Text, nullable=False),
    Column("platform", Text),
    Column("contact", Text),
    Column("currency", Text),
    Column("avg_prep_days", Numeric(6, 1)),
    Column("note", Text),
)
carriers = tenant(
    "carriers",
    Column("name", Text, nullable=False),
    Column("pricing", Text),
    Column("currency", Text),
    Column("avg_transit_days", Numeric(6, 1)),
)
cash_accounts = tenant(
    "cash_accounts",
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("currency", Text, nullable=False),
    Column("opening_balance", FX, nullable=False, server_default="0"),
)
purchases = tenant(
    "purchases",
    Column("title", Text),
    Column("status", Text, nullable=False, server_default="draft"),
    Column("ordered_on", Date),
    Column("paid_on", Date),
    Column("cn_warehouse_on", Date),
    Column("shipped_on", Date),
    Column("arrived_on", Date),
    Column("received_on", Date),
    Column("sent_to_uzum_on", Date),
    Column("closed_on", Date),
    Column("legacy_batch_id", Integer),
    Column("note", Text),
    refs={"supplier_id": ("suppliers", True), "carrier_id": ("carriers", True)},
)
purchase_lines = tenant(
    "purchase_lines",
    Column("temp_name", Text),
    Column("url", Text),
    Column("image_url", Text),
    Column("variant", Text),
    Column("ordered_qty", Integer, nullable=False),
    Column("received_qty", Integer),
    Column("unit_price", FX),
    Column("currency", Text),
    Column("unit_weight", Numeric(12, 4)),
    Column("unit_volume", Numeric(12, 6)),
    refs={"purchase_id": ("purchases", False), "item_id": ("items", True)},
)
cost_components = tenant(
    "cost_components",
    Column("kind", Text, nullable=False),
    Column("amount", FX, nullable=False),
    Column("currency", Text, nullable=False),
    Column("paid_on", Date),
    Column("rate_mode", Text, nullable=False, server_default="cbu"),
    Column("rate", RATE),
    Column("charged_amount", FX),
    Column("charged_currency", Text),
    Column("allocation", Text, nullable=False, server_default="units"),
    Column(
        "targets", JSONB
    ),  # qatorlar va qo'lda ulushlar (purchase_lines id'lari shu xarid ichida)
    check_in("rate_mode", ("cbu", "manual", "effective")),
    check_in("allocation", ("units", "weight", "volume", "value", "manual")),
    refs={"purchase_id": ("purchases", False), "account_id": ("cash_accounts", True)},
)
stock_moves = tenant(
    "stock_moves",
    Column("kind", Text, nullable=False),
    Column("qty", Integer, nullable=False),
    Column("day", Date, nullable=False),
    Column("note", Text),
    check_in("kind", ("receive", "to_uzum", "adjust", "writeoff")),
    refs={"item_id": ("items", False), "purchase_line_id": ("purchase_lines", True)},
)
# F41 (ADR-033): boshlang'ich holat. ``item_costs`` — tovarning tarixiy tannarxi sana bo'yicha (``valid_from`` NULL —
# boshidan); ``opening_stock`` — boshlash sanasidagi qoldiq (Uzumda + o'z omborimda), sotuvchi tasdiqlagan son.
item_costs = tenant(
    "item_costs",
    Column("valid_from", Date),
    Column("unit_cost", UZS, nullable=False),
    CheckConstraint("unit_cost >= 0", name="unit_cost"),
    UniqueConstraint("org_id", "item_id", "valid_from", postgresql_nulls_not_distinct=True),
    refs={"item_id": ("items", False)},
)
opening_stock = tenant(
    "opening_stock",
    Column("uzum_qty", Integer, nullable=False, server_default="0"),
    Column("own_qty", Integer, nullable=False, server_default="0"),
    CheckConstraint("uzum_qty >= 0 AND own_qty >= 0", name="qty"),
    UniqueConstraint("org_id", "item_id"),
    refs={"item_id": ("items", False)},
)
fx_rates = global_table(
    "fx_rates",
    Column("day", Date, primary_key=True),
    Column("currency", Text, primary_key=True),
    Column("source", Text, primary_key=True),
    Column("rate", RATE, nullable=False),
    Column("fetched_at", TS, nullable=False, server_default=func.now()),
)

# --- Hosila (hisoblangan) jadvallar -----------------------------------------------------------

lots = tenant(
    "lots",
    Column("ready_on", Date),
    Column("qty", Integer, nullable=False),
    Column("total", UZS, nullable=False),
    Column("unit_cost", RATE, nullable=False),
    Column("flags", ARRAY(Text), nullable=False, server_default="{}"),
    UniqueConstraint("org_id", "purchase_line_id"),  # bitta xarid qatori — bitta lot (F20)
    refs={"purchase_line_id": ("purchase_lines", False), "item_id": ("items", True)},
)
Index(None, lots.c.org_id, lots.c.item_id)
sale_costs = tenant(
    "sale_costs",
    Column("method", Text, nullable=False),
    Column("unit_cost", RATE),
    Column("cogs", UZS),
    Column("flags", ARRAY(Text), nullable=False, server_default="{}"),
    Column("allocations", JSONB),
    Column("computed_at", TS, nullable=False, server_default=func.now()),
    # "Qayta hisoblandi" (03 §7): oldingi hisobdan keyin COGS o'zgargan vaqt va oldingi qiymat (B2.8).
    Column("changed_at", TS),
    Column("previous_cogs", UZS),
    UniqueConstraint("org_id", "sale_item_id"),
    refs={"sale_item_id": ("sale_items", False)},
)
daily_sku_metrics = tenant(
    "daily_sku_metrics",
    Column("day", Date, nullable=False),
    Column("revenue", UZS, nullable=False, server_default="0"),
    Column("units", Integer, nullable=False, server_default="0"),
    Column("commission", UZS, nullable=False, server_default="0"),
    Column("logistics", UZS, nullable=False, server_default="0"),
    Column("cogs", UZS, nullable=False, server_default="0"),
    Column("ads", UZS, nullable=False, server_default="0"),
    Column("returns", Integer, nullable=False, server_default="0"),
    Column("canceled", Integer, nullable=False, server_default="0"),
    # B2.8: tannarxi ma'lum qatorlar (F15, F8) va taxminiy qism (F22).
    Column("revenue_costed", UZS, nullable=False, server_default="0"),
    Column("payout_costed", UZS, nullable=False, server_default="0"),
    Column("cogs_estimated", UZS, nullable=False, server_default="0"),
    # B2.9: Yakunlangan qatorlar soni, shundan tannarxsizlari (P&L "N ta sotuv tannarxsiz", F15) va tannarxi
    # ma'lum dona (M6: tannarx/dona, foyda/dona).
    Column("lines", Integer, nullable=False, server_default="0"),
    Column("lines_uncosted", Integer, nullable=False, server_default="0"),
    Column("units_costed", Integer, nullable=False, server_default="0"),
    UniqueConstraint("org_id", "shop_id", "sku_id", "day", postgresql_nulls_not_distinct=True),
    refs={"shop_id": ("shops", False), "sku_id": ("mp_skus", True)},
)

# Qayta hisob navbati (B2.8, ``upapi.calc``): manba o'zgargani yozuvi — ma'lumot bilan bitta tranzaksiyada.
# ``ref_id`` NULL — shu turdagi hammasi; ``since`` (do'kon turlari) — shu Toshkent kunidan, NULL — butun tarix.
RECALC_KINDS = ("purchase", "item", "shop", "metrics")
recalc_queue = tenant(
    "recalc_queue",
    Column("kind", Text, nullable=False),
    Column("ref_id", UUID(as_uuid=True)),
    Column("since", Date),
    check_in("kind", RECALC_KINDS),
    UniqueConstraint("org_id", "kind", "ref_id", postgresql_nulls_not_distinct=True),
)

# --- Pul --------------------------------------------------------------------------------------

expense_categories = tenant(
    "expense_categories",
    Column("name", Text, nullable=False),
    UniqueConstraint("org_id", "name"),
)
manual_expenses = tenant(
    "manual_expenses",
    Column("amount", UZS, nullable=False),
    Column("start_on", Date, nullable=False),
    Column("end_on", Date, nullable=False),
    Column("recurrence", Text),
    Column("note", Text),
    CheckConstraint("end_on >= start_on", name="period"),
    refs={
        "category_id": ("expense_categories", False),
        "shop_id": ("shops", True),
        "item_id": ("items", True),
    },
)
transactions = tenant(
    "transactions",
    Column("day", Date, nullable=False),
    Column("amount", FX, nullable=False),
    Column("currency", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("counterparty", Text),
    Column("note", Text),
    refs={
        "account_id": ("cash_accounts", False),
        "purchase_id": ("purchases", True),
        "manual_expense_id": ("manual_expenses", True),
    },
)
payout_schedules = tenant(
    "payout_schedules",
    Column("kind", Text, nullable=False),
    Column("valid_from", Date, nullable=False),
    check_in("kind", ("daily", "weekly", "biweekly", "monthly")),
    refs={"shop_id": ("shops", False)},
)
goals = tenant(
    "goals",
    Column("period_start", Date, nullable=False),
    Column("period_end", Date, nullable=False),
    Column("metric", Text, nullable=False),
    Column("target", UZS, nullable=False),
    refs={"shop_id": ("shops", True), "item_id": ("items", True)},
)

# --- Sozlama va ma'lumotnoma ------------------------------------------------------------------

tax_profiles = tenant(
    "tax_profiles",
    Column("valid_from", Date, nullable=False),
    Column("regime", Text, nullable=False),
    Column("rate_pct", PCT, nullable=False, server_default="0"),
    Column("base", Text, nullable=False, server_default="revenue"),
    Column("vat_pct", PCT, nullable=False, server_default="0"),
    Column("profit_pct", PCT, nullable=False, server_default="0"),
    check_in("regime", ("turnover", "agent", "vat_profit", "none")),
)
ref_logistics_tariffs = global_table(
    "ref_logistics_tariffs",
    _id(),
    Column("valid_from", Date, nullable=False, unique=True),
    Column("rules", JSONB, nullable=False),
)
ref_tax_rates = global_table(
    "ref_tax_rates",
    _id(),
    Column("code", Text, nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("rate_pct", PCT, nullable=False),
    Column("note", Text),
    UniqueConstraint("code", "valid_from"),
)

# --- Bildirishnoma ----------------------------------------------------------------------------

notification_channels = tenant(
    "notification_channels",
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    Column("kind", Text, nullable=False),
    Column("target", Text, nullable=False),
    Column("active", Boolean, nullable=False, server_default="true"),
    check_in("kind", ("telegram", "push")),
)
notification_rules = tenant(
    "notification_rules",
    Column("event", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default="true"),
    Column("params", JSONB),
    Column("quiet_from", Time),
    Column("quiet_to", Time),
)
notifications = tenant(
    "notifications",
    Column("dedupe_key", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("payload", JSONB, nullable=False),
    Column("sent_at", TS),
    UniqueConstraint("org_id", "dedupe_key"),
    refs={"rule_id": ("notification_rules", True), "channel_id": ("notification_channels", True)},
)

# --- Tarif (bizning) --------------------------------------------------------------------------

plans = global_table(
    "plans",
    _id(),
    Column("code", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("price_uzs", UZS, nullable=False),
    Column("limits", JSONB),
)
subscriptions = tenant(
    "subscriptions",
    Column("plan_id", UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False),
    Column("status", Text, nullable=False),
    Column("trial_until", Date),
    Column("current_period_end", Date),
    check_in("status", ("trial", "active", "past_due", "read_only", "canceled")),
)
billing_invoices = tenant(
    "billing_invoices",
    Column("amount", UZS, nullable=False),
    Column("status", Text, nullable=False),
    Column("fiscal_url", Text),
    Column("issued_on", Date, nullable=False),
    refs={"subscription_id": ("subscriptions", False)},
)
payments = tenant(
    "payments",
    Column("amount", UZS, nullable=False),
    Column("provider", Text, nullable=False),
    Column("provider_ref", Text),
    Column("status", Text, nullable=False),
    Column("paid_at", TS),
    refs={"invoice_id": ("billing_invoices", False)},
)

# --- Mahsulot analitikasi ---------------------------------------------------------------------

events = tenant(
    "events",
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Column("name", Text, nullable=False),
    Column("props", JSONB),
    append_only=True,
)

SPECIAL = ["users"]  # o'z RLS siyosati bilan
