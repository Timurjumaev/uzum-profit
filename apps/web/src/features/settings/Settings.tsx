// Sozlamalar (M16, B4.8). Hozircha birinchi bo'lim — Uzum bonus davrlari (ADR-031).
// Keyingi bo'limlar (soliq, tannarx usuli, muddatlar, do'konlar) keyin shu sahifaga qo'shiladi.
import { useSuspenseQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { currentOrg, meQuery } from "../../app/query";
import { FeeWaivers } from "./FeeWaivers";

export function Settings() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const canManage = org.role === "owner" || org.role === "manager";

  return (
    <section className="settings">
      <header className="settings__head">
        <h1 className="h2">{t("nav.settings")}</h1>
      </header>
      <FeeWaivers orgId={org.id} canManage={canManage} />
    </section>
  );
}
