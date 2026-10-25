// "Maʼlumotlar holati" (M3) — B3.7.
import { useTranslation } from "react-i18next";

export function Status() {
  const { t } = useTranslation();
  return (
    <main>
      <h1>{t("pages.status.title")}</h1>
      <p>{t("pages.status.building")}</p>
    </main>
  );
}
