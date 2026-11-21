// 5-qadam: Telegram (M2 6-qadam, B6.6, A13): kunlik xulosa va ogohlantirishlar telefonga keladi. Ixtiyoriy — "Keyinroq ulayman";
// ulanmasa Bosh sahifada yopib qo'yiladigan taklif chiqadi.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui";
import { TelegramInvite } from "../telegram/TelegramInvite";

export function TelegramStep({ orgId, onDone }: { orgId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const [linked, setLinked] = useState(false);
  return (
    <div className="onb__form">
      <h2>{t("onboarding.telegram.title")}</h2>
      <p className="muted">{t("onboarding.telegram.lead")}</p>
      <TelegramInvite orgId={orgId} onLinked={() => setLinked(true)} />
      <div className="onb__actions">
        <Button variant={linked ? "primary" : "ghost"} size="lg" onClick={onDone}>
          {linked ? t("onboarding.telegram.finish") : t("onboarding.telegram.skip")}
        </Button>
      </div>
    </div>
  );
}
