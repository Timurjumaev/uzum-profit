// Ogohlantirish chegaralari (ADR-043): bekor va qaytarish ulushi shu chegaradan oshsa, bosh sahifadagi kartochka
// ogohlantirish rangida ko'rsatiladi. Kodda standart chegara yo'q (tamoyil 2) — bo'sh maydon ogohlantirishni o'chiradi.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { setAlertSettings } from "../../app/query";
import { Banner, Button, NumberInput } from "../../components/ui";
import type { AlertsIn, Settings } from "../../lib/api/types";
import { alertValid, percentToShare, shareToPercent } from "./model";
import { useSettingsMutation } from "./useSettingsMutation";

const KEYS = ["cancel_share", "return_share"] as const;

export function AlertSettings({ orgId, data, canManage }: { orgId: string; data: Settings["alerts"]; canManage: boolean }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Record<(typeof KEYS)[number], string | null>>(() => ({
    cancel_share: shareToPercent(data.cancel_share),
    return_share: shareToPercent(data.return_share),
  }));
  const save = useSettingsMutation(orgId, (body: AlertsIn) => setAlertSettings(orgId, body), "settings.alerts.saved");
  const valid = KEYS.every((k) => alertValid(draft[k]));
  return (
    <section className="settings-section" aria-labelledby="settings-alerts">
      <h2 id="settings-alerts" className="h3">
        {t("settings.alerts.title")}
      </h2>
      <p className="caption">{t("settings.alerts.lead")}</p>
      <form
        className="settings-form settings-form--grid"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save.mutate({ cancel_share: percentToShare(draft.cancel_share), return_share: percentToShare(draft.return_share) });
        }}
      >
        <fieldset className="settings-fieldset" disabled={!canManage}>
          <legend className="label">{t("settings.alerts.legend")}</legend>
          {KEYS.map((k) => (
            <NumberInput
              key={k}
              label={t(`settings.alerts.${k}`)}
              suffix="%"
              optional
              value={draft[k]}
              onValueChange={(v) => setDraft((d) => ({ ...d, [k]: v }))}
            />
          ))}
        </fieldset>
        {!valid && <Banner tone="warning" title={t("settings.alerts.invalid")} />}
        {canManage && (
          <div className="settings-section__row">
            <Button type="submit" variant="primary" disabled={!valid} loading={save.isPending}>
              {t("settings.save")}
            </Button>
          </div>
        )}
      </form>
    </section>
  );
}
