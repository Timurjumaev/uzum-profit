// O'zbek yozuvi (04 §8.3): lotin → kirill (uz-Cyrl tarjimasi avtomatik), kirill → lotin va qidiruv normallashtirish.
// Lotinda oʻ/gʻ — U+02BB, tutuq — U+02BC. Qoidaga tushmaydigan so'zlar (ruscha o'zlashmalar: sentabr → сентябр) —
// `WORDS` lug'atida; tarjimadagi butun matn tuzatishlari — `messages/uz-Cyrl.fixes.ts`.

export const OKINA = "ʻ"; // ʻ
export const TUTUQ = "ʼ"; // ʼ

const APOSTROPHES = /['‘’`ʻʼ]/g;

/** So'z darajasidagi istisnolar (kichik harfda, lotin → kirill). Tarjimada ishlatilsa — shu yerga qo'shiladi. */
const WORDS: Record<string, string> = {
  sentabr: "сентябр",
  oktabr: "октябр",
  iyun: "июн",
  iyul: "июл",
  noyabr: "ноябр",
  dekabr: "декабр",
  mln: "млн",
  mlrd: "млрд",
  kompensatsiya: "компенсация",
  kompensatsiyalar: "компенсациялар",
};

/** Kirillga o'girilmaydigan nomlar va qisqartmalar. */
const KEEP = new Set([
  "uzum", "profit", "roi", "drr", "sku", "id", "telegram", "api", "fifo", "cbu", "abc", "xyz",
  "x", "xx", "xxx", // telefon namunasi: +998 XX XXX XX XX
]);

const LAT_PAIRS: Array<[string, string]> = [
  [`o${OKINA}`, "ў"],
  [`g${OKINA}`, "ғ"],
  ["sh", "ш"],
  ["ch", "ч"],
  ["yo", "ё"],
  ["yu", "ю"],
  ["ya", "я"],
  ["ye", "е"],
];

const LAT_SINGLE: Record<string, string> = {
  a: "а", b: "б", d: "д", f: "ф", g: "г", h: "ҳ", i: "и", j: "ж", k: "к", l: "л", m: "м", n: "н", o: "о",
  p: "п", q: "қ", r: "р", s: "с", t: "т", u: "у", v: "в", x: "х", y: "й", z: "з", [TUTUQ]: "ъ",
};

const VOWELS = new Set("aeiouAEIOU");

function isUpper(ch: string): boolean {
  return ch !== ch.toLowerCase();
}

function caseLike(source: string, target: string): string {
  if (!isUpper(source[0])) return target;
  // "SH" → "Ш", "Sh" → "Ш": birinchi harf katta bo'lsa — katta.
  return target[0].toUpperCase() + target.slice(1);
}

function wordToCyrillic(word: string): string {
  const lower = word.toLowerCase();
  if (KEEP.has(lower)) return word;
  // Nom + qo'shimcha: "Telegramʼda" → "Telegramʼда".
  const cut = word.indexOf(TUTUQ);
  if (cut > 0 && KEEP.has(lower.slice(0, cut))) return word.slice(0, cut + 1) + wordToCyrillic(word.slice(cut + 1));
  const fixed = WORDS[lower];
  if (fixed) return isUpper(word[0]) ? fixed[0].toUpperCase() + fixed.slice(1) : fixed;
  let out = "";
  for (let i = 0; i < word.length; ) {
    // "yoʻq" — й + ў (yo + ʻ emas).
    const pair = LAT_PAIRS.find(
      ([lat]) =>
        word.slice(i, i + lat.length).toLowerCase() === lat && !(lat === "yo" && word[i + 2] === OKINA),
    );
    if (pair) {
      out += caseLike(word.slice(i, i + pair[0].length), pair[1]);
      i += pair[0].length;
      continue;
    }
    const ch = word[i];
    if (ch === "e" || ch === "E") {
      // So'z boshida va unlidan keyin — э, aks holda — е.
      const cyr = i === 0 || VOWELS.has(word[i - 1]) ? "э" : "е";
      out += isUpper(ch) ? cyr.toUpperCase() : cyr;
    } else {
      const cyr = LAT_SINGLE[ch.toLowerCase()];
      out += cyr === undefined ? ch : isUpper(ch) ? cyr.toUpperCase() : cyr;
    }
    i += 1;
  }
  return out;
}

/** Lotin → kirill. `{{...}}` (i18next o'zgaruvchilari) va `<...>` (teglar) o'zgarmaydi. */
export function toCyrillic(text: string): string {
  return text
    .split(/(\{\{[^}]*\}\}|<[^>]*>)/)
    .map((part, i) =>
      i % 2 === 1 ? part : part.replace(new RegExp(`[A-Za-z${OKINA}${TUTUQ}]+`, "g"), wordToCyrillic),
    )
    .join("");
}

const CYR_TO_LAT: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", ғ: `g${OKINA}`, д: "d", е: "e", ё: "yo", ж: "j", з: "z", и: "i", й: "y",
  к: "k", қ: "q", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ў: `o${OKINA}`,
  ф: "f", х: "x", ҳ: "h", ц: "ts", ч: "ch", ш: "sh", щ: "sh", ъ: TUTUQ, ы: "i", ь: "", э: "e", ю: "yu",
  я: "ya",
};

/** Kirill → lotin (o'zbek va rus kirillidagi matn uchun; qidiruv va solishtirish). */
export function toLatin(text: string): string {
  let out = "";
  for (const ch of text) {
    const lower = ch.toLowerCase();
    const lat = CYR_TO_LAT[lower];
    if (lat === undefined) out += ch;
    else out += ch !== lower && lat ? lat[0].toUpperCase() + lat.slice(1) : lat;
  }
  return out;
}

/** Qidiruv kaliti (04 §8.3): kirill → lotin, kichik harf, apostrof turlari bitta belgi, ortiqcha bo'shliq yo'q.
 * "Ғалла", "G'alla", "gʻalla" — bir xil kalit. */
export function searchKey(text: string): string {
  return toLatin(text.normalize("NFC"))
    .toLowerCase()
    .replace(APOSTROPHES, "'")
    .replace(/\s+/g, " ")
    .trim();
}

/** Oddiy `'` ni UI yozuviga (04 §8.3): oʻ/gʻ — U+02BB, qolgan joyda — tutuq U+02BC. */
export function uzApostrophes(text: string): string {
  return text.replace(/([oOgG])['‘’`]/g, `$1${OKINA}`).replace(/['‘’`]/g, TUTUQ);
}
