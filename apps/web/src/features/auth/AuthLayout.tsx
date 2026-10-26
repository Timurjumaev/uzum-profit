// Kirish va taklif sahifalari uchun karkas: markazda kartochka, yuqorida til tanlash (kirishdan oldin ham kerak).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Logo } from "../../components/shell/Logo";
import { Select } from "../../components/ui";
import { LANGS, setLanguage, type Lang } from "../../lib/i18n";

export function AuthLayout({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  const { t, i18n } = useTranslation();
  return (
    <main className="auth">
      <div className="auth__lang">
        <Select
          label={t("common.language")}
          value={i18n.language}
          onValueChange={(v) => void setLanguage(i18n, v as Lang)}
          options={LANGS.map((value) => ({ value, label: t(`languages.${value}`) }))}
        />
      </div>
      <div className="auth__card">
        <div className="auth__brand">
          <Logo />
          <span>{t("app.name")}</span>
        </div>
        <h1>{title}</h1>
        {lead && <p className="muted">{lead}</p>}
        {children}
      </div>
    </main>
  );
}
