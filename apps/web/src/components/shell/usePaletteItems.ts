// Ctrl+K manbalari: sahifalar (menyu bilan bir xil ro'yxat — `nav.ts`) va tezkor amallar (mavzu, til).
// Sahifaga o'tganda joriy davr va do'kon filtrlari saqlanadi.
import { useNavigate } from "@tanstack/react-router";
import { Languages, Moon, Palette } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { LANGS, setLanguage } from "../../lib/i18n";
import { useTheme, type ThemeChoice } from "../../lib/theme";
import type { PaletteItem } from "./CommandPalette";
import { NAV_ALL } from "./nav";

const THEMES: readonly ThemeChoice[] = ["system", "light", "dark"];

export function usePaletteItems(): PaletteItem[] {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { setTheme } = useTheme();
  return useMemo(() => {
    const pages: PaletteItem[] = NAV_ALL.map((n) => ({
      id: `page:${n.key}`,
      group: "page",
      label: t(`nav.${n.key}`),
      icon: n.icon,
      run: () => void navigate({ to: n.to, search: (prev: Record<string, unknown>) => prev }),
    }));
    const themes: PaletteItem[] = THEMES.map((choice) => ({
      id: `theme:${choice}`,
      group: "action",
      label: t("shell.setTheme", { theme: t(`shell.themes.${choice}`) }),
      icon: choice === "dark" ? Moon : Palette,
      run: () => setTheme(choice),
    }));
    const languages: PaletteItem[] = LANGS.map((lang) => ({
      id: `lang:${lang}`,
      group: "action",
      label: t("shell.setLanguage", { language: t(`languages.${lang}`) }),
      icon: Languages,
      run: () => void setLanguage(i18n, lang),
    }));
    return [...pages, ...themes, ...languages];
    // i18n.language — til almashganda yorliqlar qayta tuziladi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, i18n.language, navigate, setTheme]);
}
