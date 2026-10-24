"""structlog sozlamasi: JSON loglar, so'rov konteksti, maxfiy qiymatlar filtri (03-arxitektura.md §10, §15).

Token, kod, kalit, parol, cookie loglarga **yozilmaydi**: kalit nomi bo'yicha (ichma-ich ham) ``[yashirildi]``
bilan almashtiriladi, ``Authorization`` qiymatiga o'xshash matnlar ham.
"""

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[yashirildi]"
SECRET_KEYS = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|otp|code|session|signature)",
    re.IGNORECASE,
)
# Kod nomli, lekin maxfiy bo'lmagan maydonlar. Oddiy ``code`` ataylab yashiriladi (OTP bo'lishi mumkin):
# xato kodi logga ``error_code`` nomi bilan yoziladi.
SAFE_KEYS = frozenset({"error_code", "status_code", "expense_code"})
_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: (REDACTED if _secret(k) else _clean(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_clean(v) for v in value)
    if isinstance(value, str):
        return _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    return value


def _secret(key: object) -> bool:
    name = str(key)
    return name.lower() not in SAFE_KEYS and bool(SECRET_KEYS.search(name))


def redact(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """structlog protsessori: maxfiy maydonlarni (kalit nomi bo'yicha) va Bearer/Basic qiymatlarini yashiradi."""
    for key in list(event_dict):
        if key == "event":
            event_dict[key] = _clean(event_dict[key])
        elif _secret(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _clean(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact,
        structlog.processors.JSONRenderer()
        if json
        else structlog.dev.ConsoleRenderer(colors=False),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "upapi") -> Any:
    return structlog.get_logger(name)
