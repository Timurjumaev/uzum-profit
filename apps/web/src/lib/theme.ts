// Yorug'/qorong'i rejim (04 §4.2, ADR-048): standart — **yorug'** (Temur: asosiy ko'rinish yorug'); foydalanuvchi tanlasa
// (yorug' / qorong'i / tizim) `<html data-theme>` va `localStorage` (`up.theme`); "tizim" — CSS `prefers-color-scheme`. Sahifa yuklanishida miltillamasligi uchun shu qoida
// `public/theme-init.js` da ham (React'dan oldin, CSP: inline skript yo'q).
import { useCallback, useSyncExternalStore } from "react";

import { colors, type Theme } from "../styles/tokens";

export type ThemeChoice = Theme | "system";
export const THEME_KEY = "up.theme";

function storedChoice(): ThemeChoice {
  try {
    const value = globalThis.localStorage?.getItem(THEME_KEY);
    return value === "light" || value === "dark" || value === "system" ? value : "light";
  } catch {
    return "light";
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
    globalThis.localStorage?.setItem(THEME_KEY, choice); // "system" ham saqlanadi (yo'qligi — standart yorug')
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
  const [choice, theme] = useSyncExternalStore(subscribe, snapshot, () => "light:light").split(":") as [
    ThemeChoice,
    Theme,
  ];
  const setTheme = useCallback((next: ThemeChoice) => void applyTheme(next), []);
  return { choice, theme, setTheme };
}
