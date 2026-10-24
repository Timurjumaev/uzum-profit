"""Ulanish satrini drayverga moslash (ilova — asyncpg; migratsiya va testlar — psycopg ham)."""


def normalize_url(url: str, async_driver: bool = True) -> str:
    """``postgresql://`` → ``postgresql+asyncpg://`` (yoki sync uchun ``+psycopg``); drayver ko'rsatilgan bo'lsa o'zgarmaydi."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            driver = "asyncpg" if async_driver else "psycopg"
            return f"postgresql+{driver}://" + url[len(prefix) :]
    return url
