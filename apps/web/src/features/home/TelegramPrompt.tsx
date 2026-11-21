// Bosh sahifadagi taklif (B6.6, A13): Telegram ulanmagan bo'lsa — bitta yopib qo'yiladigan blok. "Ulash" — oyna (havola va QR).
// Yopish foydalanuvchi brauzerida eslab qolinadi (shaxsiy qulaylik; ruxsat yo'q bo'lsa — har safar chiqadi).
import { useQuery } from "@tanstack/react-query";
import { Send, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { notificationSettingsQuery } from "../../app/query";
import { Button, Dialog } from "../../components/ui";
import { TelegramInvite } from "../telegram/TelegramInvite";

export const DISMISS_KEY = "up.telegramPrompt.dismissed";

function dismissed(): boolean {
  try {
    return globalThis.localStorage?.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export function TelegramPrompt({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const settings = useQuery(notificationSettingsQuery(orgId));
  const [hidden, setHidden] = useState(dismissed);
  const [open, setOpen] = useState(false);
  if (settings.data?.telegram_linked !== false || (hidden && !open)) return null;
  const close = () => {
    setHidden(true);
    try {
      globalThis.localStorage?.setItem(DISMISS_KEY, "1");
    } catch {
      /* brauzer saqlashga ruxsat bermasa — shunchaki shu sessiyada yashiriladi */
    }
  };
  return (
    <aside className="tg-prompt" aria-label={t("telegramInvite.promptTitle")}>
      <span className="tg-prompt__icon" aria-hidden>
        <Send size={22} />
      </span>
      <div className="tg-prompt__text">
        <strong>{t("telegramInvite.promptTitle")}</strong>
        <span className="muted">{t("telegramInvite.promptText")}</span>
      </div>
      <Button variant="primary" onClick={() => setOpen(true)}>
        {t("telegramInvite.connect")}
      </Button>
      <button type="button" className="ui-icon-btn" onClick={close} aria-label={t("telegramInvite.later")}>
        <X size={18} aria-hidden />
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} title={t("telegramInvite.title")}>
        <TelegramInvite orgId={orgId} />
      </Dialog>
    </aside>
  );
}
