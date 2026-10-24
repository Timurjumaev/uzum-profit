"""Sog'liq tekshiruvi: Caddy, Docker healthcheck va Uptime Kuma uchun."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from upapi import __version__

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    version: str
    env: str


@router.get("/health", response_model=Health, summary="Ilova ishlayaptimi (liveness)")
def health(request: Request) -> Health:
    # DB va navbat tekshiruvi (readiness) — B2.2 / B2.6 da qo'shiladi.
    return Health(status="ok", version=__version__, env=request.app.state.settings.env.value)
