"""Kod, token va telefon raqami: yaratish, normallashtirish, xeshlash.

Bazaga faqat xesh yoziladi: OTP — HMAC-SHA256 (``UP_OTP_SECRET`` bilan, baza sizib chiqsa ham 6 xonali kodni
tanlab bo'lmaydi), sessiya va taklif tokenlari — SHA-256 (256 bit tasodifiy).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

CODE_LENGTH = 6
_DIGITS = re.compile(r"\D")


class InvalidPhone(ValueError):
    """Telefon raqami E.164 ga keltirilmadi."""


def normalize_phone(raw: str) -> str:
    """Telefon raqamini E.164 ko'rinishiga keltiradi. O'zbekiston: 9 xonali mahalliy raqam → ``+998…``.

    ``+998 90 123-45-67``, ``998901234567``, ``90 123 45 67`` → ``+998901234567``."""
    text = raw.strip()
    digits = _DIGITS.sub("", text)
    if text.startswith("+") or len(digits) > 9:
        number = digits
    elif len(digits) == 9:
        number = "998" + digits
    else:
        raise InvalidPhone(raw)
    if number.startswith("998") and len(number) != 12:
        raise InvalidPhone(raw)
    if not 8 <= len(number) <= 15 or number[0] == "0":
        raise InvalidPhone(raw)
    return "+" + number


def mask_phone(phone: str) -> str:
    """Log va audit uchun: ``+99890*****67``."""
    return phone[:6] + "*" * max(len(phone) - 8, 0) + phone[-2:]


def new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def code_hash(secret: str, phone: str, code: str) -> bytes:
    return hmac.new(secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).digest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()
