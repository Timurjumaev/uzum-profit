// Bosh sahifa (M4) — B4.1. Hozircha karkas: kim kirgani va tashkilotlar.
import { useSuspenseQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { meQuery } from "../app/query";

export function Home() {
  const { t } = useTranslation();
  const { data } = useSuspenseQuery(meQuery);
  return (
    <section>
      <h1>{t("app.name")}</h1>
      <p>{t("pages.home.building")}</p>
      <ul aria-label={t("common.orgs")}>
        {data.orgs.map((org) => (
          <li key={org.id}>{org.name}</li>
        ))}
      </ul>
    </section>
  );
}
