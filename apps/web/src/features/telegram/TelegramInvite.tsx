// Telegram'ni ulashga chorlash (B6.6, A13): bir martalik havola (15 daqiqa) + QR; ulanish `GET /notifications/settings` ni 3 soniyada
// bir so'rab kutiladi — `telegram_linked` bo'lishi bilan tasdiq chiqadi. Onboarding oxirida va Bosh sahifa taklifida bitta komponent.
import { useMutation, useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { notificationSettingsQuery, telegramLink } from "../../app/query";
import { Banner, Button } from "../../components/ui";
import { QrCode } from "./QrCode";

export const LINK_POLL_MS = 3000;

export function TelegramInvite({ orgId, onLinked }: { orgId: string; onLinked?: () => void }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);
  const create = useMutation({ mutationFn: () => telegramLink(orgId), onSuccess: (out) => setUrl(out.url) });
  const settings = useQuery({ ...notificationSettingsQuery(orgId), refetchInterval: url ? LINK_POLL_MS : false });
  const linked = settings.data?.telegram_linked === true;
  useEffect(() => {
    if (linked) onLinked?.();
    // onLinked har renderda yangi bo'lishi mumkin — faqat ulanish holatiga bog'liq.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linked]);
  if (linked) {
    return (
      <Banner tone="positive" title={t("telegramInvite.linked")}>
        {t("telegramInvite.linkedText")}
      </Banner>
    );
  }
  return (
    <div className="tg-invite">
      {create.isError && <Banner tone="negative" title={errorText(create.error, t)} />}
      {url === null ? (
        <>
          <p className="muted">{t("telegramInvite.lead")}</p>
          <Button variant="primary" size="lg" icon={<Send size={18} aria-hidden />} loading={create.isPending} onClick={() => create.mutate()}>
            {t("telegramInvite.connect")}
          </Button>
        </>
      ) : (
        <div className="tg-invite__link">
          <QrCode text={url} label={t("telegramInvite.qrLabel")} />
          <div className="tg-invite__side">
            <a className="ui-btn ui-btn--primary ui-btn--lg" href={url} target="_blank" rel="noopener noreferrer">
              {t("telegramInvite.open")}
            </a>
            <p className="caption">{t("telegramInvite.scan")}</p>
            <p className="caption" role="status">
              {t("telegramInvite.waiting")}
            </p>
            <p className="caption">{t("telegramInvite.expires")}</p>
          </div>
        </div>
      )}
    </div>
  );
}
