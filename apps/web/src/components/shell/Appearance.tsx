// Ko'rinish sozlamalari: mavzu (tizim / yorug' / qorong'i, B3.3) va til (B3.2). Foydalanuvchi menyusida va mobil
// "Yana" panelida. Tilni profil (`user.language`) bilan bog'lash — B3.7.
import { useTranslation } from "react-i18next";

import { LANGS, setLanguage, type Lang } from "../../lib/i18n";
import { useTheme, type ThemeChoice } from "../../lib/theme";
import { Select } from "../ui";

const THEMES: readonly ThemeChoice[] = ["system", "light", "dark"];

export function Appearance() {
  const { t, i18n } = useTranslation();
  const { choice, setTheme } = useTheme();
  return (
    <div className="appearance">
      <Select
        label={t("shell.theme")}
        value={choice}
        onValueChange={(v) => setTheme(v as ThemeChoice)}
        options={THEMES.map((value) => ({ value, label: t(`shell.themes.${value}`) }))}
      />
      <Select
        label={t("common.language")}
        value={i18n.language}
        onValueChange={(v) => void setLanguage(i18n, v as Lang)}
        options={LANGS.map((value) => ({ value, label: t(`languages.${value}`) }))}
      />
    </div>
  );
}
