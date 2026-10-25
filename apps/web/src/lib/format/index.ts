// Formatlash (04 §8.4) — ilovada son, pul, foiz va sana faqat shu yerdan; `toLocaleString`/`Intl` to'g'ridan
// ishlatilmaydi (eslint). Guruh ajratgich U+00A0 (satrga bo'linmaydi), kasr — vergul, manfiy — U+2212.
// API pul va nisbatlarni satrda beradi ("123456.00", "0.125000") — float'siz, satr ustida yaxlitlanadi.

export type Lang = "uz-Latn" | "uz-Cyrl" | "ru";
export type Numeric = string | number | bigint;

export const NBSP = "\u00A0";
export const MINUS = "−";
const NARROW = "\u202F"; // raqam va birlik orasida (04 §2: shriftda tekshirilgan)

const MONTHS: Record<Lang, string[]> = {
  "uz-Latn": ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"],
  "uz-Cyrl": ["январ", "феврал", "март", "апрел", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"],
  // Rus: "23 октября" — qaratqich kelishigi.
  ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
};

// Bosh kelishik (kalendar sarlavhasi: "oktabr 2026", "октябрь 2026").
const MONTHS_NOMINATIVE: Record<Lang, string[]> = {
  "uz-Latn": MONTHS["uz-Latn"],
  "uz-Cyrl": MONTHS["uz-Cyrl"],
  ru: ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
};

const WEEKDAYS: Record<Lang, string[]> = {
  "uz-Latn": ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"],
  "uz-Cyrl": ["Ду", "Се", "Чо", "Па", "Жу", "Ша", "Як"],
  ru: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
};

const SOM: Record<Lang, string> = { "uz-Latn": "soʻm", "uz-Cyrl": "сўм", ru: "сум" };
const CURRENCY: Record<string, string> = { USD: "$", CNY: "¥", EUR: "€", RUB: "₽" };
const COMPACT: Record<Lang, [string, string, string]> = {
  "uz-Latn": ["ming", "mln", "mlrd"],
  "uz-Cyrl": ["минг", "млн", "млрд"],
  ru: ["тыс.", "млн", "млрд"],
};

// --- Sonlar (satr ustida, aniq) -------------------------------------------------------------------

type Parsed = { negative: boolean; int: string; frac: string };

function parse(value: Numeric): Parsed {
  let text = typeof value === "number" ? numberText(value) : String(value);
  text = text.trim().replace(MINUS, "-");
  const match = /^([+-])?(\d*)(?:\.(\d*))?$/.exec(text);
  if (!match || (match[2] === "" && !match[3])) throw new RangeError(`son emas: ${String(value)}`);
  return { negative: match[1] === "-", int: match[2].replace(/^0+(?=\d)/, "") || "0", frac: match[3] ?? "" };
}

function numberText(value: number): string {
  if (!Number.isFinite(value)) throw new RangeError(`son emas: ${value}`);
  // Eksponentsiz yozuv (1e21 dan katta pul bo'lmaydi; kichik kasrlar 20 xonagacha).
  return Math.abs(value) >= 1e21 ? BigInt(Math.round(value)).toString() : value.toFixed(20).replace(/\.?0+$/, "");
}

/** ROUND_HALF_UP (backend `upcore.money` bilan bir xil), `digits` xonagacha. */
function round(p: Parsed, digits: number): Parsed {
  const frac = p.frac.padEnd(digits + 1, "0");
  let units = BigInt(p.int + frac.slice(0, digits));
  if (frac[digits] >= "5") units += 1n;
  const text = units.toString().padStart(digits + 1, "0");
  const int = digits ? text.slice(0, -digits) : text;
  return { negative: p.negative && units !== 0n, int, frac: digits ? text.slice(-digits) : "" };
}

function group(int: string): string {
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

type NumberOptions = {
  /** Kasr xonalari (standart 0). */
  digits?: number;
  /** Kasrdagi oxirgi nollarni tashlash ("1,50" → "1,5"). */
  trim?: boolean;
  /** Musbatda "+" belgisi (o'zgarishlar uchun). */
  sign?: boolean;
};

/** `1 234 567`, `1 234,5`, `−312 400`. */
export function formatNumber(value: Numeric, { digits = 0, trim = false, sign = false }: NumberOptions = {}): string {
  const p = round(parse(value), digits);
  let frac = p.frac;
  if (trim) frac = frac.replace(/0+$/, "");
  const prefix = p.negative ? MINUS : sign && (p.int !== "0" || /[1-9]/.test(frac)) ? "+" : "";
  return prefix + group(p.int) + (frac ? `,${frac}` : "");
}

/** Pul (so'm): `48 357 200 soʻm`; jadvalda `unit: false` — valyutasiz. Tiyinlar ko'rsatilmaydi. */
export function formatMoney(value: Numeric, lang: Lang, { unit = true }: { unit?: boolean } = {}): string {
  const text = formatNumber(value);
  return unit ? `${text}${NBSP}${SOM[lang]}` : text;
}

/** Boshqa valyuta: `142,50 $`, `1 000 ¥` (CNY, RUB — butun; USD, EUR — 2 xona). */
export function formatCurrency(value: Numeric, currency: string): string {
  const digits = currency === "USD" || currency === "EUR" ? 2 : 0;
  return `${formatNumber(value, { digits })}${NBSP}${CURRENCY[currency] ?? currency}`;
}

/** Ixcham: `850 ming`, `1,2 mln`, `3,4 mlrd` (1 000 dan kichik — to'liq). */
export function formatCompact(value: Numeric, lang: Lang): string {
  const p = parse(value);
  const size = p.int.length;
  if (size <= 3) return formatNumber(value);
  const [thousand, million, billion] = COMPACT[lang];
  const [power, word] = size > 9 ? [9, billion] : size > 6 ? [6, million] : [3, thousand];
  const shifted: Parsed = {
    negative: p.negative,
    int: p.int.slice(0, size - power),
    frac: p.int.slice(size - power) + p.frac,
  };
  const digits = power === 3 ? 0 : 1;
  const r = round(shifted, digits);
  const frac = r.frac.replace(/0+$/, "");
  return `${r.negative ? MINUS : ""}${group(r.int)}${frac ? `,${frac}` : ""}${NBSP}${word}`;
}

/** Ulush (API: "0.125000") → `12,5%`. `digits` — foizdagi kasr xonalari (oxirgi nollar tashlanadi). */
export function formatPercent(ratio: Numeric, { digits = 1, sign = false }: { digits?: number; sign?: boolean } = {}): string {
  const p = parse(ratio);
  const frac = p.frac.padEnd(2, "0");
  const percent = `${p.negative ? "-" : ""}${p.int}${frac.slice(0, 2)}.${frac.slice(2)}`;
  return `${formatNumber(percent, { digits, trim: true, sign })}%`;
}

/** O'zgarish: `▲ 12,4%` / `▼ 3,1%`; nol — `0%`. Rang ma'nosi (yaxshi/yomon) chaqiruvchida. */
export function formatChange(ratio: Numeric): string {
  const text = formatPercent(ratio);
  if (text.startsWith(MINUS)) return `▼${NARROW}${text.slice(1)}`;
  return text === "0%" ? text : `▲${NARROW}${text}`;
}

// --- Sanalar (Toshkent, F1) -------------------------------------------------------------------------

type Ymd = { y: number; m: number; d: number };

/** "2026-10-23" yoki `Date` (Toshkent sanasi, UTC+5, yozgi vaqt yo'q). */
function ymd(value: string | Date): Ymd {
  if (typeof value === "string") {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    if (!match) throw new RangeError(`sana emas: ${value}`);
    if (value.length === 10) return { y: +match[1], m: +match[2], d: +match[3] };
    value = new Date(value);
  }
  const local = new Date(value.getTime() + 5 * 3_600_000);
  return { y: local.getUTCFullYear(), m: local.getUTCMonth() + 1, d: local.getUTCDate() };
}

const pad = (n: number) => String(n).padStart(2, "0");

/** `23.10.2026` (hamma tilda). */
export function formatDate(value: string | Date): string {
  const { y, m, d } = ymd(value);
  return `${pad(d)}.${pad(m)}.${y}`;
}

/** Matnda: `23-oktabr` / `23 октября`; `withYear` — `23-oktabr 2025`. */
export function formatDay(value: string | Date, lang: Lang, { withYear = false }: { withYear?: boolean } = {}): string {
  const { y, m, d } = ymd(value);
  const month = MONTHS[lang][m - 1];
  const text = lang === "ru" ? `${d}${NBSP}${month}` : `${d}-${month}`;
  return withYear ? `${text} ${y}` : text;
}

/** Davr: `1–31-oktabr`, `28-sentabr – 3-oktabr`, yillar boshqa bo'lsa — yil bilan; rus: `1–31 октября`. */
export function formatPeriod(start: string | Date, end: string | Date, lang: Lang): string {
  const a = ymd(start);
  const b = ymd(end);
  if (a.y === b.y && a.m === b.m) {
    if (a.d === b.d) return formatDay(start, lang);
    const month = MONTHS[lang][a.m - 1];
    return lang === "ru" ? `${a.d}–${b.d}${NBSP}${month}` : `${a.d}–${b.d}-${month}`;
  }
  const withYear = a.y !== b.y;
  return `${formatDay(start, lang, { withYear })} – ${formatDay(end, lang, { withYear })}`;
}

/** Oy va yil: `oktabr 2026` / `октябрь 2026`. */
export function formatMonth(value: string | Date, lang: Lang): string {
  const { y, m } = ymd(value);
  return `${MONTHS_NOMINATIVE[lang][m - 1]} ${y}`;
}

/** Hafta kunining qisqa nomi (Du … Ya; dushanbadan). */
export function formatWeekday(value: string | Date, lang: Lang): string {
  const { y, m, d } = ymd(value);
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0 — yakshanba
  return WEEKDAYS[lang][(day + 6) % 7];
}

const UNITS: Record<Lang, { now: string; ago: (n: number, unit: "minute" | "hour" | "day") => string }> = {
  "uz-Latn": {
    now: "hozirgina",
    ago: (n, unit) => `${n} ${{ minute: "daqiqa", hour: "soat", day: "kun" }[unit]} oldin`,
  },
  "uz-Cyrl": {
    now: "ҳозиргина",
    ago: (n, unit) => `${n} ${{ minute: "дақиқа", hour: "соат", day: "кун" }[unit]} олдин`,
  },
  ru: {
    now: "только что",
    ago: (n, unit) => {
      const forms = { minute: ["минуту", "минуты", "минут"], hour: ["час", "часа", "часов"], day: ["день", "дня", "дней"] }[unit];
      return `${n} ${forms[ruPlural(n)]} назад`;
    },
  },
};

/** Rus ko'plik shakli: 1 минуту, 2 минуты, 5 минут, 21 минуту, 11 минут. */
export function ruPlural(n: number): 0 | 1 | 2 {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 0;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 1;
  return 2;
}

/** `3 daqiqa oldin` (ma'lumot yangiligi, 02 tamoyil 8); 7 kundan eski — sana. */
export function formatRelative(value: string | Date, lang: Lang, now: Date = new Date()): string {
  const then = typeof value === "string" ? new Date(value) : value;
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
  const units = UNITS[lang];
  if (seconds < 60) return units.now;
  if (seconds < 3600) return units.ago(Math.floor(seconds / 60), "minute");
  if (seconds < 86_400) return units.ago(Math.floor(seconds / 3600), "hour");
  if (seconds < 7 * 86_400) return units.ago(Math.floor(seconds / 86_400), "day");
  return formatDate(then);
}

/** Tilga bog'langan formatlovchilar (komponentlar `useFormat()` orqali oladi — `lib/i18n`). */
export function formatterFor(lang: Lang) {
  return {
    lang,
    number: formatNumber,
    money: (value: Numeric, options?: { unit?: boolean }) => formatMoney(value, lang, options),
    currency: formatCurrency,
    compact: (value: Numeric) => formatCompact(value, lang),
    percent: formatPercent,
    change: formatChange,
    date: formatDate,
    day: (value: string | Date) => formatDay(value, lang),
    period: (start: string | Date, end: string | Date) => formatPeriod(start, end, lang),
    weekday: (value: string | Date) => formatWeekday(value, lang),
    month: (value: string | Date) => formatMonth(value, lang),
    relative: (value: string | Date, now?: Date) => formatRelative(value, lang, now),
  };
}

export type Formatter = ReturnType<typeof formatterFor>;

// --- Kiritilgan sonni o'qish (MoneyInput, NumberInput — 04 §5) -----------------------------------

/** "1 234,5", "1234.5", "1 234 567", "−312 400", "1.234.567,50" → "1234.5" (API uchun nuqtali satr); son emas — `null`.
 * Bo'shliqlar (oddiy, U+00A0, U+202F) va apostrof guruh ajratgich; vergul yoki nuqta — oxirgisi kasr (bitta bo'lsa
 * va undan keyin 3 dan boshqa raqam bo'lsa ham kasr; "1.234.567" kabi bir nechta nuqta — guruh). */
export function parseNumber(input: string): string | null {
  let text = input.trim().replace(/[\s\u00A0\u202F'ʼ’]/g, "").replace(MINUS, "-");
  if (!text) return null;
  const negative = text.startsWith("-");
  if (negative || text.startsWith("+")) text = text.slice(1);
  const separators = text.match(/[.,]/g) ?? [];
  let int = text;
  let frac = "";
  if (separators.length > 0) {
    const last = Math.max(text.lastIndexOf("."), text.lastIndexOf(","));
    const lastSep = text[last];
    const sameKind = separators.every((s) => s === lastSep);
    if (!sameKind && separators.filter((sep) => sep === lastSep).length > 1) return null; // "1,2,3.4.5"
    if (sameKind && separators.length > 1) {
      int = text.replaceAll(lastSep, ""); // 1.234.567 — hammasi guruh
    } else {
      int = text.slice(0, last).replace(/[.,]/g, "");
      frac = text.slice(last + 1);
    }
  }
  if (!/^\d+$/.test(int || "0") || !/^\d*$/.test(frac) || (!int && !frac)) return null;
  const digits = (int || "0").replace(/^0+(?=\d)/, "") + (frac ? `.${frac}` : "");
  return negative && /[1-9]/.test(digits) ? `-${digits}` : digits;
}
