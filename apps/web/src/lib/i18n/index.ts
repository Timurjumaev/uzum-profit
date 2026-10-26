// i18n (03 §9, 04 §8): i18next, tillar uz-Latn (asosiy), uz-Cyrl (uz-Latn'dan avtomatik), ru. Tanlov — brauzerda
// (`localStorage`), bo'lmasa brauzer tili. Formatlash — `useFormat()` (`lib/format`, joriy til bilan).
import i18next, { type i18n as I18n } from "i18next";
import { useMemo } from "react";
import { initReactI18next, useTranslation } from "react-i18next";

import { formatterFor, type Formatter, type Lang } from "../format";
import { ru } from "./messages/ru";
import { uzCyrlFixes } from "./messages/uz-Cyrl.fixes";
import { uzLatn, type Messages } from "./messages/uz-Latn";
import { toCyrillic } from "./translit";

export type { Lang };
export const LANGS: readonly Lang[] = ["uz-Latn", "uz-Cyrl", "ru"];
export const DEFAULT_LANG: Lang = "uz-Latn";
const STORAGE_KEY = "up.lang";

type Tree = { [key: string]: string | Tree };

/** Daraxtdagi har matnga `fn` (kalit yo'li bilan). */
function mapTree(tree: Tree, fn: (text: string, path: string) => string, prefix = ""): Tree {
  return Object.fromEntries(
    Object.entries(tree).map(([key, value]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return [key, typeof value === "string" ? fn(value, path) : mapTree(value, fn, path)];
    }),
  );
}

/** uz-Latn → uz-Cyrl: transliteratsiya + qo'lda tuzatishlar. */
export function buildCyrillic(source: Messages, fixes: Record<string, string> = uzCyrlFixes): Messages {
  return mapTree(source, (text, path) => fixes[path] ?? toCyrillic(text)) as Messages;
}

export const resources = {
  "uz-Latn": { translation: uzLatn },
  "uz-Cyrl": { translation: buildCyrillic(uzLatn) },
  ru: { translation: ru },
};

export function isLang(value: unknown): value is Lang {
  return typeof value === "string" && (LANGS as readonly string[]).includes(value);
}

/** Foydalanuvchi qo'lda tanlagan til (`null` — hali tanlamagan). */
export function storedLang(): Lang | null {
  try {
    const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
    return isLang(saved) ? saved : null;
  } catch {
    return null;
  }
}

/** Saqlangan tanlov → brauzer tili (ru*) → uz-Latn. `localStorage` yopiq bo'lishi mumkin (maxfiy oyna). */
export function detectLang(): Lang {
  try {
    const saved = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // saqlash yopiq — brauzer tiliga qaraymiz
  }
  const browser = globalThis.navigator?.language ?? "";
  return browser.toLowerCase().startsWith("ru") ? "ru" : DEFAULT_LANG;
}

export function createI18n(lang: Lang = detectLang()): I18n {
  const instance = i18next.createInstance();
  void instance.use(initReactI18next).init({
    resources,
    lng: lang,
    fallbackLng: DEFAULT_LANG,
    supportedLngs: [...LANGS],
    interpolation: { escapeValue: false }, // React o'zi xavfsiz qiladi
    initAsync: false,
    returnNull: false,
  });
  syncDocument(lang);
  return instance;
}

function syncDocument(lang: Lang) {
  if (globalThis.document) globalThis.document.documentElement.lang = lang;
}

export async function setLanguage(instance: I18n, lang: Lang): Promise<void> {
  // Tanlov avval yoziladi, keyin til almashadi: almashuv davomida boshqa kod (profil tilini qo'llash) "tanlov yo'q"
  // deb o'ylab, uni ustidan yozib yubormasin.
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, lang);
  } catch {
    // saqlanmasa — faqat shu sessiyada
  }
  await instance.changeLanguage(lang);
  syncDocument(lang);
}

export function currentLang(instance: I18n): Lang {
  return isLang(instance.language) ? instance.language : DEFAULT_LANG;
}

/** Joriy tilga bog'langan formatlovchi (04 §8.4). */
export function useFormat(): Formatter {
  const { i18n } = useTranslation();
  const lang = currentLang(i18n);
  return useMemo(() => formatterFor(lang), [lang]);
}
