"""FastAPI ilovasi. Hozircha faqat sog'liq endpoint'i; to'liq skelet — B2.1."""

from fastapi import FastAPI

from upapi import __version__

app = FastAPI(title="Uzum Profit API", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
