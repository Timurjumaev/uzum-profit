"""Bot servisi (B6.2): ``python -m upbot`` — aiogram 3, long polling + navbatdagi xabarlarni yuborish (har 30 s).

API va ishchi bilan bir xil xavfsizlik shartlari (``check_settings``, ``up_app`` roli). Token — ``UP_TELEGRAM_BOT_TOKEN``
(faqat shu servisda); berilmagan bo'lsa servis ishga tushmaydi. Mantiq — :mod:`upbot.service` (testlanadi), bu yerda
faqat Telegram bilan ulanish.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncEngine
from upapi.db.session import make_engine
from upapi.logs import configure_logging, get_logger
from upapi.settings import Settings, get_settings
from upapi.startup import UnsafeConfiguration, check_role, check_settings

from upbot import messages as msg
from upbot import service

DELIVER_EVERY = 30.0
_log = get_logger("upbot")

DESCRIPTIONS = {
    "bugun": "Bugungi xulosa",
    "kecha": "Kechagi xulosa",
    "hafta": "Shu hafta",
    "oy": "Shu oy",
    "qoldiq": "Kritik qoldiq",
    "sozlamalar": "Bildirishnoma sozlamalari",
}


def keyboard(url: str | None, lang: str) -> InlineKeyboardMarkup | None:
    if url is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=msg.t(lang, "more"), url=url)]]
    )


class AiogramSender:
    """``service.Sender``: Telegram xatolari doimiy (chat yo'q, bloklangan) va vaqtinchalikka ajratiladi."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(
        self, chat_id: int, text: str, url: str | None, lang: str = "uz"
    ) -> None:  # pragma: no cover — tarmoq
        try:
            # "Batafsil" tugmasi foydalanuvchi tilida (B6.4, A7).
            await self.bot.send_message(chat_id, text, reply_markup=keyboard(url, lang))
        except (TelegramForbiddenError, TelegramNotFound) as exc:
            raise service.SendError(type(exc).__name__, permanent=True) from exc
        except TelegramBadRequest as exc:
            # Matn uzun yoki tugma havolasi noto'g'ri — bizning xatoimiz; foydalanuvchining Telegram'i uzilmaydi (B6.4, A5).
            raise service.SendError(type(exc).__name__, final=True) from exc
        except TelegramRetryAfter as exc:
            raise service.SendError("retry_after", retry_after=float(exc.retry_after)) from exc
        except Exception as exc:
            raise service.SendError(type(exc).__name__, permanent=False) from exc


def build(engine: AsyncEngine, settings: Settings, clock: Callable[[], datetime]) -> Dispatcher:
    """Buyruqlar (testda ``Dispatcher`` handlerlari to'g'ridan-to'g'ri chaqiriladi)."""
    dp = Dispatcher()

    @dp.message(CommandStart(deep_link=True))
    async def start_link(message: Message, command: CommandObject) -> None:
        if message.from_user is None:  # pragma: no cover
            return
        result, org = await service.link(
            engine, command.args or "", message.from_user.id, message.chat.id, clock()
        )
        lang = msg.lang_of(message.from_user.language_code)
        key = {
            service.LinkResult.OK: "linked",
            service.LinkResult.EXPIRED: "link_expired",
            service.LinkResult.INVALID: "link_invalid",
            service.LinkResult.TAKEN: "link_taken",
        }[result]
        await message.answer(msg.t(lang, key, org=org or ""))

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user is None:  # pragma: no cover
            return
        people = await service.identities(engine, message.from_user.id)
        lang = msg.lang_of(people[0].language if people else message.from_user.language_code)
        await message.answer(msg.t(lang, "help" if people else "not_linked"))

    @dp.message(Command(*service.COMMANDS))
    async def commands(message: Message, command: CommandObject) -> None:
        if message.from_user is None:  # pragma: no cover
            return
        replies = await service.command(
            engine, message.from_user.id, command.command, clock(), settings.web_url
        )
        people = await service.identities(engine, message.from_user.id)
        lang = msg.lang_of(people[0].language if people else None)
        for reply in replies:
            await message.answer(
                reply.text,
                reply_markup=keyboard(service.page_url(settings.web_url, reply.path), lang),
            )

    return dp


async def deliver_loop(
    engine: AsyncEngine, sender: service.Sender, settings: Settings
) -> None:  # pragma: no cover
    while True:
        try:
            sent = await service.deliver(engine, sender, settings.web_url, datetime.now(UTC))
            if sent:
                _log.info("notifications_sent", sent=sent)
        except Exception as exc:
            _log.warning("deliver_loop_failed", error_code=type(exc).__name__)
        await asyncio.sleep(DELIVER_EVERY)


async def run(settings: Settings | None = None) -> None:  # pragma: no cover — jarayon
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.json_logs)
    check_settings(settings)
    if settings.telegram_bot_token is None:
        raise UnsafeConfiguration("UP_TELEGRAM_BOT_TOKEN berilmagan")
    engine = make_engine(settings.database_url)
    try:
        await check_role(engine, settings)
        bot = Bot(settings.telegram_bot_token.get_secret_value())
        await bot.set_my_commands(
            [BotCommand(command=k, description=v) for k, v in DESCRIPTIONS.items()]
        )
        dp = build(engine, settings, lambda: datetime.now(UTC))
        task = asyncio.create_task(deliver_loop(engine, AiogramSender(bot), settings))
        _log.info("bot_started")
        try:
            await dp.start_polling(bot, handle_signals=False)
        finally:
            task.cancel()
            await bot.session.close()
    finally:
        await engine.dispose()


def main() -> None:  # pragma: no cover
    asyncio.run(run())
