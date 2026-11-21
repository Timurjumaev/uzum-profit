// "Yordam" havolasi (B8.14): Telegram yordam chati (`UP_SUPPORT_URL`, API `/config`). Berilmagan yoki yuklanmagan bo'lsa — hech narsa
// ko'rsatilmaydi (kirish sahifasi `/config` kechiksa ham bloklanmaydi). Tashqi havola: yangi oynada, `noopener`.
import { useQuery } from "@tanstack/react-query";
import { LifeBuoy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { publicConfigQuery } from "../../app/query";

export function SupportLink() {
  const { t } = useTranslation();
  const { data } = useQuery(publicConfigQuery);
  if (!data?.support_url) return null;
  return (
    <a className="support-link" href={data.support_url} target="_blank" rel="noopener noreferrer">
      <LifeBuoy size={16} aria-hidden />
      {t("shell.support")}
    </a>
  );
}
