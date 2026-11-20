"""Bot xabarlari matni (B6.2, 02 M15): navbatdagi bildirishnoma (``notifications.payload``) va buyruq javoblari.

Raqamlar API bilan bir xil hisobdan keladi (``upapi.notify``); bu yerda faqat ko'rsatish: so'm butun songa yaxlitlanadi va
minglar bo'sh joy bilan ajratiladi (ilovadagi kabi). Har xabar — matn va "Batafsil" uchun ilova sahifasi yo'li.
Tillar: ``uz-Latn`` (oʻ/gʻ — U+02BB, tutuq — U+02BC) va ``ru``; boshqasi — ``uz-Latn``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
        "daily": "📊 Kunlik xulosa, {day}",
        "today": "📊 Bugun, {day}",
        "week": "📊 Hafta: {start} – {end}",
        "month": "📊 Oy: {start} – {end}",
        "period": "📊 {start} – {end}",
        "orders": "Buyurtmalar: {n}",
        "revenue": "Tushum: {v}",
        "profit": "Sof foyda: {v}",
        "profit_expected": "  shundan kutilayotgan: {v} (Jarayondagi sotuvlar)",
        "profit_rate": "  bunday sotuvlarning {n}% i yakunlanadi",
        "unfinished": "Davr hali tugamagan — raqamlar oʻzgaradi.",
        "previous": "Oldingi toʻliq davr:",
        "canceled": "Bekorlar: {n} dona",
        "uncosted": "Tannarxsiz qatorlar: {n} — sof foydaga kirmagan",
        "fresh": "Maʼlumot: {at} holatiga",
        "stale": "Buyurtmalar hali yangilanmagan — raqamlar toʻliq emas",
        "stock_critical": "⚠️ Qoldiq kritik: {n} ta SKU — buyurtma berish kerak",
        "stock_critical_new": "⚠️ Qoldiq kritik: yangi {n} ta SKU (jami {total}) — buyurtma berish kerak",
        "ship_needed": "📦 Uzumga yuborish kerak: {n} ta SKU — Uzumdagi zaxira topshirish muddatiga yetmaydi, omborimda tovar bor (jami {total})",
        "ship_line": "• {name} — Uzumda ~{days} kunlik zaxira, yuborish: {qty} dona",
        "lost_goods": "🔎 Uzum yoʻqolgan deb belgilagan tovar: {n} ta SKU (jami {total}) — Uzum bilan bogʻlaning, kamomadni talab qiling",
        "lost_line": "• {name} — {qty} dona",
        "commission_changed": "💱 Uzum komissiyasi oʻzgardi: {n} ta SKU ({day})",
        "commission_line": "• {name} — {old}% → {new}%",
        "returns_spike_shop": "↩️ Qaytish keskin oshdi: {n} ta doʻkon (jami {total}) — oxirgi 7 kunda ulush 30 kunlikdan ≥ 2 barobar",
        "returns_spike_sku": "↩️ Qaytish keskin oshdi: {n} ta SKU (jami {total}) — oxirgi 7 kunda ulush 30 kunlikdan ≥ 2 barobar",
        "returns_line": "• {name} — {qty} ta qaytdi, ulush {share7}% (30 kunda {share30}%)",
        "days": "{n} kunga",
        "no_stock_critical": "Kritik qoldiq yoʻq.",
        "loss_sales": "🔻 Zarar bilan sotuv: {n} ta SKU (oxirgi {streak} ta sotuv zararda)",
        "loss_sales_new": "🔻 Zarar bilan sotuv: yangi {n} ta SKU (jami {total}; oxirgi {streak} ta sotuv zararda)",
        "uncosted_sales": "Tannarxsiz sotuvlar: {n} ta qator ({day}). Xaridni kiriting — sof foyda toʻliq boʻladi.",
        "uncosted_new": "Tannarxsiz yangi tovar sotildi ({day}): {n} ta SKU, {lines} ta qator. Xaridni kiriting — sof foyda toʻliq boʻladi.",
        "new_fine": "Yangi jarima: {v}",
        "receiving": "Postavka № {number}: {title} — joʻnatildi {shipped}, qabul qilindi {accepted} ({missing} dona kam)",
        "cargo_late": "🚚 Kargo kechikmoqda: {title}. Kutilgan sana {expected} ({n} kun oʻtdi). Keldimi? Belgilang, kelmagan boʻlsa — yetkazib beruvchi bilan bogʻlaning.",
        "uncounted": "Xarid keldi, {days} kundan beri sanalmagan: {title}. Sanang — Omborimda soni aniq boʻladi.",
        "sync_stale": "❗ Sinxron toʻxtadi: {shop}. Oxirgi yangilanish: {since}",
        "sync_invalid": "❗ Uzum kaliti yaroqsiz: {shop}. Sozlamalarda yangi kalit kiriting.",
        "sync_restored": "✅ Sinxron tiklandi: {shop}.",
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
        "daily": "📊 Итоги дня, {day}",
        "today": "📊 Сегодня, {day}",
        "week": "📊 Неделя: {start} – {end}",
        "month": "📊 Месяц: {start} – {end}",
        "period": "📊 {start} – {end}",
        "orders": "Заказы: {n}",
        "revenue": "Выручка: {v}",
        "profit": "Чистая прибыль: {v}",
        "profit_expected": "  из них ожидаемая: {v} (продажи в обработке)",
        "profit_rate": "  такие продажи завершаются в {n}% случаев",
        "unfinished": "Период ещё не закончился — цифры изменятся.",
        "previous": "Предыдущий полный период:",
        "canceled": "Отмены: {n} шт.",
        "uncosted": "Строк без себестоимости: {n} — не вошли в чистую прибыль",
        "fresh": "Данные на {at}",
        "stale": "Заказы ещё не обновились — цифры неполные",
        "stock_critical": "⚠️ Критический остаток: {n} SKU — пора заказывать",
        "stock_critical_new": "⚠️ Критический остаток: новых {n} SKU (всего {total}) — пора заказывать",
        "ship_needed": "📦 Пора отправлять на Uzum: {n} SKU — запаса на Uzum не хватит до срока передачи, на вашем складе товар есть (всего {total})",
        "ship_line": "• {name} — на Uzum запас ~{days} дн., отправить: {qty} шт.",
        "lost_goods": "🔎 Uzum отметил товар как потерянный: {n} SKU (всего {total}) — свяжитесь с Uzum, требуйте компенсацию",
        "lost_line": "• {name} — {qty} шт.",
        "commission_changed": "💱 Комиссия Uzum изменилась: {n} SKU ({day})",
        "commission_line": "• {name} — {old}% → {new}%",
        "returns_spike_shop": "↩️ Возвраты резко выросли: {n} магазинов (всего {total}) — доля за 7 дней ≥ 2× доли за 30 дней",
        "returns_spike_sku": "↩️ Возвраты резко выросли: {n} SKU (всего {total}) — доля за 7 дней ≥ 2× доли за 30 дней",
        "returns_line": "• {name} — возвратов {qty}, доля {share7}% (за 30 дней {share30}%)",
        "days": "на {n} дн.",
        "no_stock_critical": "Критических остатков нет.",
        "loss_sales": "🔻 Продажи в убыток: {n} SKU (последние {streak} продажи в убыток)",
        "loss_sales_new": "🔻 Продажи в убыток: новых {n} SKU (всего {total}; последние {streak} продажи в убыток)",
        "uncosted_sales": "Продажи без себестоимости: {n} строк ({day}). Внесите закупку — чистая прибыль станет полной.",
        "uncosted_new": "Продан новый товар без себестоимости ({day}): {n} SKU, {lines} строк. Внесите закупку — чистая прибыль станет полной.",
        "new_fine": "Новый штраф: {v}",
        "receiving": "Поставка № {number}: {title} — отправлено {shipped}, принято {accepted} (меньше на {missing} шт.)",
        "cargo_late": "🚚 Карго задерживается: {title}. Ожидали {expected} (прошло {n} дн.). Пришло? Отметьте, если нет — свяжитесь с поставщиком.",
        "uncounted": "Закупка пришла и не пересчитана {days} дн.: {title}. Пересчитайте — остаток на складе станет точным.",
        "sync_stale": "❗ Синхронизация остановилась: {shop}. Последнее обновление: {since}",
        "sync_invalid": "❗ Ключ Uzum недействителен: {shop}. Введите новый ключ в настройках.",
        "sync_restored": "✅ Синхронизация восстановлена: {shop}.",
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


def _percent(rate: str) -> int:
    return int((Decimal(rate) * 100).quantize(Decimal(1)))


def summary(
    data: dict[str, Any],
    lang: str,
    title: str,
    *,
    partial: bool = False,
    unfinished: bool = False,
) -> str:
    """Davr xulosasi. Sof foyda uch qismda (B6.4, A1): jami; shundan kutilayotgan (Jarayondagi sotuvlar, belgisiz
    taxmin emas) va R (F16 fakti); "HH:MM holatiga" — ilovada raqam keyin o'zgarishi mumkin.
    ``partial`` — buyruq: yangilik yo'q bo'lsa ogohlantirish; ``unfinished`` — davr hali tugamagan (izoh)."""
    start, end = data["start"], data["end"]
    head = t(lang, title, day=day(start), start=day(start), end=day(end))
    lines = [
        head,
        t(lang, "orders", n=data["orders"]),
        t(lang, "revenue", v=money(data["revenue"], lang)),
        t(lang, "profit", v=money(data["net_profit"], lang)),
    ]
    expected = data.get("net_profit_expected")
    if expected is not None and Decimal(expected) != 0:
        lines.append(t(lang, "profit_expected", v=money(expected, lang)))
        if data.get("rate") is not None:
            lines.append(t(lang, "profit_rate", n=_percent(data["rate"])))
    lines.append(t(lang, "canceled", n=data["canceled"]))
    if data.get("uncosted_lines"):
        lines.append(t(lang, "uncosted", n=data["uncosted_lines"]))
    if unfinished:
        lines.append(t(lang, "unfinished"))
    fresh = data.get("fresh_at")
    if fresh:
        lines.append(t(lang, "fresh", at=moment(fresh)))
    elif partial:
        lines.append(t(lang, "stale"))
    return "\n".join(lines)


def expired(event: str, payload: dict[str, Any], today: date) -> bool:
    """Xulosa o'z kunidan o'tib ketdimi (B6.4, A18–A21): kunlik — yaratilgan kuni (hisobot kunidan keyingi kun) tugagach
    yuborilmaydi (tinch soatda ertasi kunga surilgan xulosa o'tgan kunni "kecha" deb yubormasin); haftalik — keyingi
    haftaning oxirigacha."""
    if event == "daily_summary":
        return today > date.fromisoformat(payload["end"]) + timedelta(days=1)
    if event == "weekly_summary":
        return today > date.fromisoformat(payload["end"]) + timedelta(days=7)
    return False


def _skus(skus: list[dict[str, Any]], lang: str) -> list[str]:
    out = []
    for x in skus:
        name = x.get("title") or "—"
        out.append(f"• {name}" + (f" — {t(lang, 'days', n=x['days'])}" if x.get("days") else ""))
    return out


def _ship_skus(skus: list[dict[str, Any]], lang: str) -> list[str]:
    """B6.5: "• Nom — Uzumda N kun, yuborish: Q dona" (Uzumdagi zaxira va F54 rejasi / omborimdagi son)."""
    return [
        t(
            lang,
            "ship_line",
            name=x.get("title") or "—",
            days=Decimal(x["days"]).quantize(Decimal("0.1")),
            qty=x["qty"],
        )
        for x in skus
    ]


def notification(event: str, payload: dict[str, Any], lang: str, org: str | None = None) -> Message:
    """Navbatdagi bildirishnoma → xabar. Noma'lum hodisa — ``ValueError`` (yuborilmaydi, ``failed``)."""
    p = payload
    if event == "daily_summary":
        msg = Message(summary(p, lang, "daily"), "/")
    elif event == "weekly_summary":
        msg = Message(summary(p, lang, "week"), f"/pnl?from={p['start']}&to={p['end']}")
    elif event == "stock_critical":
        head = (
            t(lang, "stock_critical_new", n=p["count"], total=p["total"])
            if p.get("new")
            else t(lang, "stock_critical", n=p["count"])
        )
        msg = Message("\n".join([head, *_skus(p["skus"], lang)]), "/inventory")
    elif event == "ship_needed":
        head = t(lang, "ship_needed", n=p["count"], total=p["total"])
        msg = Message("\n".join([head, *_ship_skus(p["skus"], lang)]), "/dispatches")
    elif event == "lost_goods":
        head = t(lang, "lost_goods", n=p["count"], total=p["total"])
        lines = [t(lang, "lost_line", name=x.get("title") or "—", qty=x["qty"]) for x in p["skus"]]
        msg = Message("\n".join([head, *lines]), "/inventory")
    elif event == "returns_spike":
        head = t(lang, f"returns_spike_{p['level']}", n=p["count"], total=p["total"])
        lines = [
            t(
                lang,
                "returns_line",
                name=x.get("title") or "—",
                qty=x["returns"],
                share7=x["share7"],
                share30=x["share30"],
            )
            for x in p["items"]
        ]
        msg = Message("\n".join([head, *lines]), "/orders")
    elif event == "commission_changed":
        head = t(lang, "commission_changed", n=p["count"], day=day(p["day"]))
        lines = [
            t(lang, "commission_line", name=x.get("title") or "—", old=x["old"], new=x["new"])
            for x in p["skus"]
        ]
        msg = Message("\n".join([head, *lines]), "/products")
    elif event == "loss_sales":
        key = "loss_sales_new" if p.get("new") else "loss_sales"
        head = t(lang, key, n=p["count"], total=p.get("total", p["count"]), streak=p["streak"])
        msg = Message("\n".join([head, *_skus(p["skus"], lang)]), "/products")
    elif event == "uncosted_sales":
        if "skus" in p:  # B6.4 (A3): tannarxsiz yangi SKU
            head = t(lang, "uncosted_new", n=p["count"], lines=p["lines"], day=day(p["day"]))
            msg = Message("\n".join([head, *_skus(p["skus"], lang)]), "/orders")
        else:
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
    elif event == "cargo_late":
        msg = Message(
            t(
                lang,
                "cargo_late",
                title=p.get("title") or "—",
                expected=day(p["expected"]),
                n=p["days_late"],
            ),
            f"/purchases/{p['purchase_id']}",
        )
    elif event == "uncounted_purchase":
        msg = Message(
            t(lang, "uncounted", days=p["days"], title=p.get("title") or "—"),
            f"/purchases/{p['purchase_id']}",
        )
    elif event == "sync_stopped":
        if p["reason"] == "restored":  # B6.4 (A4): bitta "tiklandi" xabari
            msg = Message(t(lang, "sync_restored", shop=p["shop"]), "/status")
        elif p["reason"] == "key_invalid":
            msg = Message(t(lang, "sync_invalid", shop=p["shop"]), "/settings")
        else:
            since = moment(p["since"]) if p.get("since") else "—"
            msg = Message(t(lang, "sync_stale", shop=p["shop"], since=since), "/status")
    else:
        raise ValueError(f"noma'lum hodisa: {event}")
    return Message(f"{msg.text}\n\n— {org}", msg.path) if org else msg
