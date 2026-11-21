"""``GET /config``: ochiq (kirishsiz) mijoz sozlamalari (B8.14) — hozircha faqat yordam havolasi (``UP_SUPPORT_URL``,
Telegram yordam chati). Kirish sahifasida kod kelmasa yoki taklif so'ralganda foydalanuvchi shu havola orqali yozadi."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["config"])


class PublicConfig(BaseModel):
    support_url: str | None


@router.get("/config", response_model=PublicConfig, summary="Ochiq mijoz sozlamalari")
def public_config(request: Request) -> PublicConfig:
    return PublicConfig(support_url=request.app.state.settings.support_url)
