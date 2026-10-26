"""Ilova sozlamalari (03-arxitektura.md §10, §14).

Qiymatlar muhit o'zgaruvchilaridan (``UP_`` prefiksi) yoki ``.env`` dan; sirlar kodda va repozitoriyda yo'q.
"""

import base64
import hashlib
from datetime import date, time
from enum import StrEnum
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Faqat dev/test; staging/prod'da bu qiymat bilan ilova ishga tushmaydi.
DEV_OTP_SECRET = "dev-only-otp-secret"
# Marketplace kalitini shifrlash (B2.4) uchun dev/test kaliti — hamma biladi, shuning uchun staging/prod'da taqiq.
DEV_TOKEN_KEY = base64.b64encode(
    hashlib.sha256(b"uzum-profit dev-only token key").digest()
).decode()
UZUM_BASE_URL = "https://api-seller.uzum.uz/api/seller-openapi"


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class OtpSender(StrEnum):
    CONSOLE = "console"  # dev: kod terminalga chiqadi; test: xotirada
    TELEGRAM_GATEWAY = "telegram_gateway"  # ADR-028


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UP_", env_file=".env", extra="ignore")

    env: Environment = Environment.DEV
    log_level: str = "INFO"
    # None — muhitga qarab: dev'da odam o'qiydigan, boshqalarida JSON (structlog).
    log_json: bool | None = None
    database_url: str = "postgresql://uzum:uzum@localhost:5432/uzum"

    # Kirish (M1, 03 §10). Cheklovlar biznes qoidasi, lekin xavfsizlik chegarasi — sozlamada.
    otp_sender: OtpSender = OtpSender.CONSOLE
    otp_secret: SecretStr = SecretStr(DEV_OTP_SECRET)
    telegram_gateway_token: SecretStr | None = None
    otp_ttl_seconds: int = 300
    otp_per_hour: int = 5
    # Bitta IP manzildan soatiga shuncha kod so'rovi (har xil raqam bilan ham; har kod ≈ $0.01, ADR-028).
    otp_per_ip_hour: int = 20
    otp_max_attempts: int = 5
    otp_block_minutes: int = 15
    session_days: int = 30
    session_rotate_hours: int = 24
    session_grace_seconds: int = 60
    invite_days: int = 7
    # Brauzer manbalari (CSRF ``Origin`` tekshiruvi) va taklif havolasi asosi.
    allowed_origins: list[str] = ["http://localhost:5173"]
    web_url: str = "http://localhost:5173"
    cookie_secure: bool | None = None

    # Marketplace kaliti (B2.4, 03 §10): AES-256-GCM. ``UP_TOKEN_KEYS='{"1": "<base64 32 bayt>"}'``,
    # yangi kalit — ``python -m upapi.crypto keygen``. Rotatsiya: yangi versiya qo'shib, joriyni unga o'tkazish.
    token_keys: dict[int, SecretStr] = {1: SecretStr(DEV_TOKEN_KEY)}
    token_key_version: int = 1
    uzum_base_url: str = UZUM_BASE_URL
    # Uzum mahsulot sahifasiga havola (SKU sahifasi): ``{id}`` — Uzum mahsulot id'si.
    uzum_product_url: str = "https://uzum.uz/ru/product/{id}"
    uzum_timeout_seconds: float = 30
    # Uzum limiti ~2 so'rov/s kalit bo'yicha (08 §8) — so'rovlar orasida kamida shuncha (03 §6).
    uzum_min_interval_seconds: float = 0.45
    # Kunlik qoldiq shundan kam bo'lsa fon sinxroni to'xtaydi, qolgani foydalanuvchi amallari uchun (02 M3).
    uzum_quota_reserve: int = 10_000
    # Kalit tekshiruvi rad etilsa (yaroqsiz kalit) — tashkilot bo'yicha soatiga shuncha urinish.
    mp_verify_failures_per_hour: int = 10

    # Sinxron (B2.6, 02 M3). Chastota — ma'lumot turi bo'yicha daqiqa; kunlik snapshot — Toshkent vaqti bilan.
    sync_intervals: dict[str, int] = {
        "shops": 1440,
        "orders": 15,
        "expenses": 60,
        "products": 60,
        "invoices": 60,
        "returns": 60,
    }
    sync_snapshot_at: time = time(23, 50)
    # Birinchi ulanish — butun tarix shu sanadan (Uzum qancha bersa; rad etsa qisqaroq oynalar, legacy kabi).
    sync_history_from: date = date(2020, 1, 1)
    sync_history_fallback_days: list[int] = [1825, 1095, 730, 365, 180, 100]
    # Inkremental oyna (kun) va kuniga bir marta chuqur sinxron (sotuv holatlari, kechikkan xarajatlar).
    sync_recent_days: int = 3
    sync_deep_days: int = 45
    sync_deep_every_hours: int = 24
    # Uzilish rejimi (03 §6): shu oynada shuncha do'konda tarmoq/5xx xatosi → umumiy pauza, keyin bitta sinov.
    sync_outage_shops: int = 2
    sync_outage_window_minutes: int = 5
    sync_outage_pause_minutes: int = 15
    # Kvota tugagan yoki WAF to'sgan akkaunt — shuncha daqiqada bitta sinov (02 M3); ketma-ket JSON 401/403 soni,
    # undan keyin kalit "yaroqsiz".
    sync_probe_minutes: int = 30
    sync_auth_failures: int = 3
    # "Hozir yangilash" (02 M3): tashkilot bo'yicha shuncha soniyada bir marta, ustuvor navbat.
    sync_refresh_cooldown_seconds: int = 60
    # Bitta ishda ko'pi bilan shuncha postavka tarkibi so'raladi (qolgani keyingi ishda) — kvota tejaladi.
    sync_invoice_items_per_run: int = 100
    worker_concurrency: int = 4

    # CBU kurslari (B2.7, F20): kuniga 2 marta (Toshkent vaqti 09:05 va 16:05), arxiv orqaga to'ldiriladi.
    cbu_url: str = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
    fx_currencies: list[str] = ["USD", "CNY", "RUB", "EUR"]
    fx_timeout_seconds: float = 20
    fx_backfill_days: int = 730
    fx_backfill_per_run: int = 30

    @property
    def json_logs(self) -> bool:
        return self.log_json if self.log_json is not None else self.env is not Environment.DEV

    @property
    def strict(self) -> bool:
        """Staging va production: xavfsizlik shartlari bajarilmasa ilova ishga tushmaydi."""
        return self.env in (Environment.STAGING, Environment.PROD)

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else self.strict

    def problems(self) -> list[str]:
        """Staging/prod uchun xavfli sozlamalar (ishga tushishda tekshiriladi)."""
        out = []
        secret = self.otp_secret.get_secret_value()
        if secret == DEV_OTP_SECRET or len(secret) < 32:
            out.append("UP_OTP_SECRET: kamida 32 belgili tasodifiy qiymat kerak")
        if self.otp_sender is OtpSender.CONSOLE:
            out.append("UP_OTP_SENDER=console faqat dev/test uchun")
        if self.otp_sender is OtpSender.TELEGRAM_GATEWAY and not self.telegram_gateway_token:
            out.append("UP_TELEGRAM_GATEWAY_TOKEN berilmagan")
        dev_key = [v for v, k in self.token_keys.items() if k.get_secret_value() == DEV_TOKEN_KEY]
        if dev_key:
            out.append(f"UP_TOKEN_KEYS: {dev_key[0]}-versiya — dev kaliti; yangi kalit kerak")
        if self.token_key_version not in self.token_keys:
            out.append("UP_TOKEN_KEY_VERSION: bunday versiya UP_TOKEN_KEYS ichida yo'q")
        if not self.cbu_url.startswith("https://"):
            out.append("UP_CBU_URL: faqat https://")
        if not self.uzum_base_url.startswith("https://"):
            out.append("UP_UZUM_BASE_URL: faqat https://")
        if not self.secure_cookies:
            out.append("UP_COOKIE_SECURE=false — sessiya cookie HTTPS'siz yuboriladi")
        if any(not o.startswith("https://") for o in self.allowed_origins):
            out.append("UP_ALLOWED_ORIGINS: faqat https:// manbalar")
        return out

    @property
    def show_error_details(self) -> bool:
        """500 xatolarida ichki tafsilot faqat dev/test'da ko'rinadi."""
        return self.env in (Environment.DEV, Environment.TEST)


@lru_cache
def get_settings() -> Settings:
    return Settings()
