"""Bot xabarlari matni (B6.2, 02 M15): navbatdagi bildirishnoma (``notifications.payload``) va buyruq javoblari.

Raqamlar API bilan bir xil hisobdan keladi (``upapi.notify``); bu yerda faqat ko'rsatish: so'm butun songa yaxlitlanadi va
minglar bo'sh joy bilan ajratiladi (ilovadagi kabi). Har xabar — matn va "Batafsil" uchun ilova sahifasi yo'li.
Tillar: ``uz-Latn`` (oʻ/gʻ — U+02BB, tutuq — U+02BC) va ``ru``; boshqasi — ``uz-Latn``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

TASHKENT = ZoneInfo("Asia/Tashkent")


@dataclass(frozen=True)
class Message:
    text: str
    path: str | None  # ilova sahifasi ("Batafsil")


def lang_of(language: str | None) -> str:
    return "ru" if language == "ru" else "uz"


def money(value: str | Decimal, lang: str) -> str:
    n = int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    digits = f"{abs(n):,}".replace(",", " ")
    sign = "−" if n < 0 else ""
    return f"{sign}{digits} {'сум' if lang == 'ru' else 'soʻm'}"


def day(value: str | date) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return d.strftime("%d.%m.%Y")


def moment(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(TASHKENT).strftime("%d.%m %H:%M")


T: dict[str, dict[str, str]] = {
    "uz": {
        "yesterday": "📊 Kecha, {day}",
        "today": "📊 Bugun, {day}",
        "week": "📊 Hafta: {start} – {end}",
        "month": "📊 Oy: {start} – {end}",
        "period": "📊 {start} – {end}",
        "orders": "Buyurtmalar: {n}",
        "revenue": "Tushum: {v}",
        "profit": "Sof foyda: {v}",
        "canceled": "Bekorlar: {n} dona",
        "uncosted": "Tannarxsiz qatorlar: {n} — sof foydaga kirmagan",
        "fresh": "Maʼlumot: {at} holatiga",
        "stale": "Buyurtmalar hali yangilanmagan — raqamlar toʻliq emas",
        "stock_critical": "⚠️ Qoldiq kritik: {n} ta SKU — buyurtma berish kerak",
        "days": "{n} kunga",
        "no_stock_critical": "Kritik qoldiq yoʻq.",
        "loss_sales": "🔻 Zarar bilan sotuv: {n} ta SKU (oxirgi {streak} ta sotuv zararda)",
        "uncosted_sales": "Tannarxsiz sotuvlar: {n} ta qator ({day}). Xaridni kiriting — sof foyda toʻliq boʻladi.",
        "new_fine": "Yangi jarima: {v}",
        "receiving": "Postavka № {number}: {title} — joʻnatildi {shipped}, qabul qilindi {accepted} ({missing} dona kam)",
        "uncounted": "Xarid keldi, {days} kundan beri sanalmagan: {title}. Sanang — Omborimda soni aniq boʻladi.",
        "sync_stale": "❗ Sinxron toʻxtadi: {shop}. Oxirgi yangilanish: {since}",
        "sync_invalid": "❗ Uzum kaliti yaroqsiz: {shop}. Sozlamalarda yangi kalit kiriting.",
        "more": "Batafsil",
        "not_linked": "Bu Telegram hali ulanmagan. Ilovada Sozlamalar → Bildirishnomalar → «Telegramʼni ulash» tugmasini bosing.",
        "linked": "✅ Telegram ulandi: {org}. Bildirishnomalar shu yerga keladi. Buyruqlar: /bugun /kecha /hafta /oy /qoldiq /sozlamalar",
        "link_expired": "Havola eskirgan. Ilovada «Telegramʼni ulash» tugmasini qayta bosing.",
        "link_invalid": "Havola notoʻgʻri yoki ishlatilgan. Ilovada «Telegramʼni ulash» tugmasini qayta bosing.",
        "link_taken": "Bu Telegram boshqa foydalanuvchiga ulangan. Avval oʻsha akkauntda uzing.",
        "no_access": "Bu maʼlumot sizning rolingizda koʻrinmaydi.",
        "settings": "Bildirishnoma sozlamalari: vaqt, chegaralar va tinch soatlar — ilovada.",
        "help": "Buyruqlar: /bugun — bugun, /kecha — kecha, /hafta — shu hafta, /oy — shu oy, /qoldiq — kritik qoldiq, /sozlamalar — sozlamalar.",
    },
    "ru": {
        "yesterday": "📊 Вчера, {day}",
        "today": "📊 Сегодня, {day}",
        "week": "📊 Неделя: {start} – {end}",
        "month": "📊 Месяц: {start} – {end}",
        "period": "📊 {start} – {end}",
        "orders": "Заказы: {n}",
        "revenue": "Выручка: {v}",
        "profit": "Чистая прибыль: {v}",
        "canceled": "Отмены: {n} шт.",
        "uncosted": "Строк без себестоимости: {n} — не вошли в чистую прибыль",
        "fresh": "Данные на {at}",
        "stale": "Заказы ещё не обновились — цифры неполные",
        "stock_critical": "⚠️ Критический остаток: {n} SKU — пора заказывать",
        "days": "на {n} дн.",
        "no_stock_critical": "Критических остатков нет.",
        "loss_sales": "🔻 Продажи в убыток: {n} SKU (последние {streak} продажи в убыток)",
        "uncosted_sales": "Продажи без себестоимости: {n} строк ({day}). Внесите закупку — чистая прибыль станет полной.",
        "new_fine": "Новый штраф: {v}",
        "receiving": "Поставка № {number}: {title} — отправлено {shipped}, принято {accepted} (меньше на {missing} шт.)",
        "uncounted": "Закупка пришла и не пересчитана {days} дн.: {title}. Пересчитайте — остаток на складе станет точным.",
        "sync_stale": "❗ Синхронизация остановилась: {shop}. Последнее обновление: {since}",
        "sync_invalid": "❗ Ключ Uzum недействителен: {shop}. Введите новый ключ в настройках.",
        "more": "Подробнее",
        "not_linked": "Этот Telegram ещё не подключён. В приложении: Настройки → Уведомления → «Подключить Telegram».",
        "linked": "✅ Telegram подключён: {org}. Уведомления будут приходить сюда. Команды: /bugun /kecha /hafta /oy /qoldiq /sozlamalar",
        "link_expired": "Ссылка устарела. Нажмите «Подключить Telegram» в приложении ещё раз.",
        "link_invalid": "Ссылка неверна или уже использована. Нажмите «Подключить Telegram» в приложении ещё раз.",
        "link_taken": "Этот Telegram подключён к другому пользователю. Сначала отключите его там.",
        "no_access": "Эти данные недоступны для вашей роли.",
        "settings": "Настройки уведомлений: время, пороги и тихие часы — в приложении.",
        "help": "Команды: /bugun — сегодня, /kecha — вчера, /hafta — эта неделя, /oy — этот месяц, /qoldiq — критический остаток, /sozlamalar — настройки.",
    },
}


def t(lang: str, key: str, **kw: Any) -> str:
    return T[lang][key].format(**kw)


def summary(data: dict[str, Any], lang: str, title: str, *, partial: bool = False) -> str:
    start, end = data["start"], data["end"]
    head = t(lang, title, day=day(start), start=day(start), end=day(end))
    lines = [
        head,
        t(lang, "orders", n=data["orders"]),
        t(lang, "revenue", v=money(data["revenue"], lang)),
        t(lang, "profit", v=money(data["net_profit"], lang)),
        t(lang, "canceled", n=data["canceled"]),
    ]
    if data.get("uncosted_lines"):
        lines.append(t(lang, "uncosted", n=data["uncosted_lines"]))
    if partial:
        fresh = data.get("fresh_at")
        lines.append(t(lang, "fresh", at=moment(fresh)) if fresh else t(lang, "stale"))
    return "\n".join(lines)


def _skus(skus: list[dict[str, Any]], lang: str) -> list[str]:
    out = []
    for x in skus:
        name = x.get("title") or "—"
        out.append(f"• {name}" + (f" — {t(lang, 'days', n=x['days'])}" if x.get("days") else ""))
    return out


def notification(event: str, payload: dict[str, Any], lang: str, org: str | None = None) -> Message:
    """Navbatdagi bildirishnoma → xabar. Noma'lum hodisa — ``ValueError`` (yuborilmaydi, ``failed``)."""
    p = payload
    if event == "daily_summary":
        msg = Message(summary(p, lang, "yesterday"), "/")
    elif event == "weekly_summary":
        msg = Message(summary(p, lang, "week"), f"/pnl?from={p['start']}&to={p['end']}")
    elif event == "stock_critical":
        msg = Message(
            "\n".join([t(lang, "stock_critical", n=p["count"]), *_skus(p["skus"], lang)]),
            "/inventory",
        )
    elif event == "loss_sales":
        text = "\n".join(
            [t(lang, "loss_sales", n=p["count"], streak=p["streak"]), *_skus(p["skus"], lang)]
        )
        msg = Message(text, "/products")
    elif event == "uncosted_sales":
        msg = Message(t(lang, "uncosted_sales", n=p["lines"], day=day(p["day"])), "/orders")
    elif event == "new_fine":
        detail = ", ".join(x for x in (p.get("name"), p.get("shop"), day(p["on"])) if x)
        msg = Message(f"{t(lang, 'new_fine', v=money(p['amount'], lang))}\n{detail}", "/expenses")
    elif event == "receiving_shortage":
        text = t(
            lang,
            "receiving",
            number=p.get("invoice_number") or "—",
            title=p.get("title") or "—",
            shipped=p["shipped"],
            accepted=p["accepted"],
            missing=p["missing"],
        )
        msg = Message(text, "/receiving")
    elif event == "uncounted_purchase":
        msg = Message(
            t(lang, "uncounted", days=p["days"], title=p.get("title") or "—"),
            f"/purchases/{p['purchase_id']}",
        )
    elif event == "sync_stopped":
        if p["reason"] == "key_invalid":
            msg = Message(t(lang, "sync_invalid", shop=p["shop"]), "/settings")
        else:
            since = moment(p["since"]) if p.get("since") else "—"
            msg = Message(t(lang, "sync_stale", shop=p["shop"], since=since), "/status")
    else:
        raise ValueError(f"noma'lum hodisa: {event}")
    return Message(f"{msg.text}\n\n— {org}", msg.path) if org else msg
