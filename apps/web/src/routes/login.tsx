// Kirish (M1) — telefon va Telegram kodi, B3.7.
import { useTranslation } from "react-i18next";

export function Login() {
  const { t } = useTranslation();
  return (
    <main>
      <h1>{t("app.name")}</h1>
      <p>{t("pages.login.building")}</p>
    </main>
  );
}
