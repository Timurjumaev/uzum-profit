// Standart yetkazish muddatlari (F25) va ABC qamrov kunlari (F27). Muddat — tarix yo'q bosqich uchun (tarix bor bo'lsa
// oxirgi 5 xarid medianasi ishlatiladi); hammasi bo'sh — sozlanmagan (muddat tarixdan, tarix yo'q bo'lsa noma'lum).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { setInventorySettings } from "../../app/query";
import { Banner, Button, NumberInput } from "../../components/ui";
import type { InventorySettingsIn, Settings } from "../../lib/api/types";
import { coverDraft, inventoryBody, inventoryState, leadDraft, type CoverDraft, type LeadDraft } from "./model";
import { useSettingsMutation } from "./useSettingsMutation";

export function InventorySettings({ orgId, data, canManage }: { orgId: string; data: Settings["inventory"]; canManage: boolean }) {
  const { t } = useTranslation();
  const [lead, setLead] = useState<LeadDraft>(() => leadDraft(data));
  const [cover, setCover] = useState<CoverDraft>(() => coverDraft(data));
  const [epoch, setEpoch] = useState(0); // kiritish maydonlari o'z matnini saqlaydi — qaytarilganda qayta yaratiladi
  const save = useSettingsMutation(orgId, (body: InventorySettingsIn) => setInventorySettings(orgId, body), "settings.inventory.saved");
  const reset = useSettingsMutation(orgId, () => setInventorySettings(orgId, {}), "settings.inventory.resetDone", () => {
    setLead(Object.fromEntries(data.stages.map((s) => [s, null])));
    setCover({ A: String(data.cover_defaults.A), B: String(data.cover_defaults.B), C: String(data.cover_defaults.C) });
    setEpoch((n) => n + 1);
  });
  const state = inventoryState(lead, cover);
  return (
    <section className="settings-section" aria-labelledby="settings-inventory">
      <h2 id="settings-inventory" className="h3">
        {t("settings.inventory.title")}
      </h2>
      <p className="caption">{t("settings.inventory.lead")}</p>
      <form
        className="settings-form settings-form--grid"
        onSubmit={(e) => {
          e.preventDefault();
          if (state === "ok") save.mutate(inventoryBody(lead, cover));
        }}
      >
        <fieldset key={`lead-${epoch}`} className="settings-fieldset" disabled={!canManage}>
          <legend className="label">{t("settings.inventory.leadLegend")}</legend>
          {data.stages.map((stage) => (
            <NumberInput key={stage} label={t(`settings.inventory.stage.${stage}`)} suffix={t("settings.inventory.days")} digits={0} optional value={lead[stage] ?? null} onValueChange={(v) => setLead((d) => ({ ...d, [stage]: v }))} />
          ))}
        </fieldset>
        <fieldset key={`cover-${epoch}`} className="settings-fieldset" disabled={!canManage}>
          <legend className="label">{t("settings.inventory.coverLegend")}</legend>
          {(["A", "B", "C"] as const).map((k) => (
            <NumberInput key={k} label={t("settings.inventory.cover", { abc: k })} suffix={t("settings.inventory.days")} digits={0} value={cover[k]} onValueChange={(v) => setCover((d) => ({ ...d, [k]: v }))} />
          ))}
        </fieldset>
        {state === "partial" && <Banner tone="warning" title={t("settings.inventory.partial")} />}
        {state === "invalid" && <Banner tone="warning" title={t("settings.inventory.invalid")} />}
        {canManage && (
          <div className="settings-section__row">
            <Button type="submit" variant="primary" disabled={state !== "ok"} loading={save.isPending}>
              {t("settings.save")}
            </Button>
            <Button variant="ghost" loading={reset.isPending} onClick={() => reset.mutate(undefined)}>
              {t("settings.inventory.reset")}
            </Button>
          </div>
        )}
      </form>
    </section>
  );
}
