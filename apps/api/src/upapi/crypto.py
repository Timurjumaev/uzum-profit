"""Marketplace kalitini shifrlash: AES-256-GCM, kalit versiyalari bilan (03-arxitektura.md §10).

- Bazada faqat ``nonce (12 bayt) || shifrmatn || teg`` va kalit versiyasi; ochiq kalit hech qachon yozilmaydi.
- AAD — tashkilot va akkaunt id: shifrmatnni boshqa qatorga yoki tashkilotga ko'chirsa, ochilmaydi.
- Rotatsiya: ``UP_TOKEN_KEYS`` ga yangi versiya qo'shiladi va ``UP_TOKEN_KEY_VERSION`` unga o'tkaziladi; eski
  versiyadagi yozuvlar ochiladi va keyingi ishlatilishida joriy versiya bilan qayta shifrlanadi
  (:meth:`TokenCipher.needs_rotation`). Eski versiyani faqat hamma yozuv o'tgandan keyin olib tashlash mumkin.
- Shifrlash kaliti zaxira nusxalarda yo'q (server sirlari — ``.env`` / Docker secrets).

Yangi kalit: ``python -m upapi.crypto keygen``.
"""

from __future__ import annotations

import base64
import binascii
import os
import sys
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

NONCE_BYTES = 12
KEY_BYTES = 32
_AAD_PREFIX = b"uzum-profit/mp_accounts/v1/"
_URLSAFE = str.maketrans("-_", "+/")


class CipherError(Exception):
    """Shifrmatn ochilmadi yoki kalit sozlamasi noto'g'ri. Matnida sir yo'q."""


def account_aad(org_id: UUID, account_id: UUID) -> bytes:
    return _AAD_PREFIX + org_id.bytes + account_id.bytes


def decode_key(value: str) -> bytes:
    """Base64 (standart yoki URL-safe) → 32 bayt. Xato matnida qiymat ko'rsatilmaydi."""
    raw = value.strip().rstrip("=").translate(_URLSAFE)
    try:
        key = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=True)
    except (binascii.Error, ValueError):
        raise CipherError("kalit base64 emas") from None
    if len(key) != KEY_BYTES:
        raise CipherError(f"kalit {KEY_BYTES} bayt bo'lishi kerak, {len(key)} bayt berilgan")
    return key


def keygen() -> str:
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()


class TokenCipher:
    """Kalitlar to'plami: ``keys`` — versiya → 32 baytli kalit, ``current`` — yangi yozuvlar uchun versiya."""

    def __init__(self, keys: dict[int, bytes], current: int) -> None:
        if current not in keys:
            raise CipherError(f"joriy kalit versiyasi ({current}) kalitlar ichida yo'q")
        if any(len(k) != KEY_BYTES for k in keys.values()):
            raise CipherError(f"har kalit {KEY_BYTES} bayt bo'lishi kerak")
        self._aead = {version: AESGCM(key) for version, key in keys.items()}
        self.current = current

    @classmethod
    def from_settings(cls, keys: dict[int, SecretStr], current: int) -> TokenCipher:
        try:
            decoded = {v: decode_key(k.get_secret_value()) for v, k in keys.items()}
        except CipherError as exc:
            raise CipherError(f"UP_TOKEN_KEYS: {exc}") from None
        return cls(decoded, current)

    def __repr__(self) -> str:
        return f"TokenCipher(versions={sorted(self._aead)}, current={self.current})"

    def encrypt(self, token: SecretStr, aad: bytes) -> tuple[bytes, int]:
        nonce = os.urandom(NONCE_BYTES)
        sealed = self._aead[self.current].encrypt(
            nonce, token.get_secret_value().encode("utf-8"), aad
        )
        return nonce + sealed, self.current

    def decrypt(self, blob: bytes, version: int, aad: bytes) -> SecretStr:
        aead = self._aead.get(version)
        if aead is None:
            raise CipherError(f"kalit versiyasi {version} sozlamada yo'q")
        try:
            plain = aead.decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)
        except InvalidTag:
            raise CipherError("shifrmatn ochilmadi (kalit yoki AAD mos emas)") from None
        return SecretStr(plain.decode("utf-8"))

    def needs_rotation(self, version: int) -> bool:
        return version != self.current


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["keygen"]:
        print(keygen())
        return 0
    print("Foydalanish: python -m upapi.crypto keygen", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
