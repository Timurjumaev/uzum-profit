// Yorug'/qorong'i rejim (04 §4.2): standart — tizim sozlamasi (CSS `prefers-color-scheme`); foydalanuvchi tanlasa
// `<html data-theme>` va `localStorage` (`up.theme`). Sahifa yuklanishida miltillamasligi uchun shu qoida
// `public/theme-init.js` da ham (React'dan oldin, CSP: inline skript yo'q).
import { useCallback, useSyncExternalStore } from "react";

import { colors, type Theme } from "../styles/tokens";

export type ThemeChoice = Theme | "system";
export const THEME_KEY = "up.theme";

function storedChoice(): ThemeChoice {
  try {
    const value = globalThis.localStorage?.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemTheme(): Theme {
  return globalThis.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Tanlovni qo'llash: `data-theme`, brauzer paneli rangi (`theme-color`), saqlash. */
export function applyTheme(choice: ThemeChoice): Theme {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  try {
    if (choice === "system") globalThis.localStorage?.removeItem(THEME_KEY);
    else globalThis.localStorage?.setItem(THEME_KEY, choice);
  } catch {
    // saqlanmasa — faqat shu sahifada
  }
  const theme = choice === "system" ? systemTheme() : choice;
  // Brauzer paneli rangi: tanlangan mavzu yoki (tizim) har meta o'z `media` si bo'yicha.
  document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
    const own = meta.getAttribute("media")?.includes("dark") ? "dark" : "light";
    meta.setAttribute("content", colors[choice === "system" ? own : choice]["bg-page"]);
  });
  listeners.forEach((fn) => fn());
  return theme;
}

const listeners = new Set<() => void>();

function subscribe(fn: () => void) {
  listeners.add(fn);
  const media = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
  media?.addEventListener("change", fn);
  return () => {
    listeners.delete(fn);
    media?.removeEventListener("change", fn);
  };
}

function snapshot(): string {
  const choice = storedChoice();
  return `${choice}:${choice === "system" ? systemTheme() : choice}`;
}

/** Joriy tanlov va amaldagi mavzu (tizim o'zgarsa ham yangilanadi). */
export function useTheme(): { choice: ThemeChoice; theme: Theme; setTheme: (choice: ThemeChoice) => void } {
  const [choice, theme] = useSyncExternalStore(subscribe, snapshot, () => "system:light").split(":") as [
    ThemeChoice,
    Theme,
  ];
  const setTheme = useCallback((next: ThemeChoice) => void applyTheme(next), []);
  return { choice, theme, setTheme };
}
