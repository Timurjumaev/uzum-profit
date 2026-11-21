// "Qurilmalarim" (M1, B8.0a): kirgan qurilmalar ro'yxati, bittasini yoki "boshqa hammasini" tugatish. Joriy qurilma
// belgilanadi va uni bu yerdan tugatib bo'lmaydi (chiqish — foydalanuvchi menyusida).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MonitorSmartphone } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { revokeOtherSessions, revokeSession, sessionsKey, sessionsQuery } from "../../app/query";
import { Badge, Button, useToast } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { Confirm } from "./Confirm";

export function Devices() {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuery(sessionsQuery);
  const [asking, setAsking] = useState(false);
  const done = async (message: string) => {
    await client.invalidateQueries({ queryKey: sessionsKey });
    toast.show(message, "positive");
  };
  const one = useMutation({
    mutationFn: revokeSession,
    onSuccess: () => done(t("settings.devices.revoked")),
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const others = useMutation({
    mutationFn: revokeOtherSessions,
    onSuccess: async () => {
      setAsking(false);
      await done(t("settings.devices.revokedOthers"));
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const items = query.data ?? [];
  const hasOthers = items.some((s) => !s.current);
  return (
    <section className="settings-section devices" aria-labelledby="settings-devices">
      <h2 id="settings-devices" className="h3">
        <MonitorSmartphone size={20} aria-hidden className="full-export__icon" /> {t("settings.devices.title")}
      </h2>
      <p className="caption">{t("settings.devices.lead")}</p>
      {items.length > 0 && (
        <ul className="full-export__list">
          {items.map((s) => (
            <li key={s.id} className="full-export__item">
              <strong>{s.device ?? t("settings.devices.unknown")}</strong>
              {s.current && <Badge tone="positive">{t("settings.devices.current")}</Badge>}
              <span className="caption">{t("settings.devices.since", { when: formatDate(s.created_at) })}</span>
              {!s.current && (
                <Button size="sm" variant="secondary" loading={one.isPending && one.variables === s.id} onClick={() => one.mutate(s.id)}>
                  {t("settings.devices.end")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {hasOthers && (
        <div className="settings-section__row">
          <Button variant="destructive" onClick={() => setAsking(true)}>
            {t("settings.devices.endOthers")}
          </Button>
        </div>
      )}
      {asking && (
        <Confirm title={t("settings.devices.confirmTitle")} action={t("settings.devices.endOthers")} loading={others.isPending} onConfirm={() => others.mutate()} onClose={() => setAsking(false)}>
          {t("settings.devices.confirmText")}
        </Confirm>
      )}
    </section>
  );
}
