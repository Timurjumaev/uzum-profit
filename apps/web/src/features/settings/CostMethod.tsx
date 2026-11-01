// Tannarx usuli (F21): FIFO yoki o'rtacha. O'zgarsa o'tgan sotuvlar tannarxi qayta hisoblanadi — tasdiq so'raladi.
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { setCostMethod } from "../../app/query";
import { Button, Select } from "../../components/ui";
import type { Settings } from "../../lib/api/types";
import { Confirm } from "./Confirm";
import { useSettingsMutation } from "./useSettingsMutation";

type Method = Settings["cost_method"];

export function CostMethod({ orgId, value, canManage }: { orgId: string; value: Method; canManage: boolean }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<Method>(value);
  const [asking, setAsking] = useState(false);
  const save = useSettingsMutation(orgId, (m: Method) => setCostMethod(orgId, m), "settings.cost.saved", () => setAsking(false));
  const changed = draft !== value;
  return (
    <section className="settings-section" aria-labelledby="settings-cost">
      <h2 id="settings-cost" className="h3">
        {t("settings.cost.title")}
      </h2>
      <p className="caption">{t("settings.cost.lead")}</p>
      <Link to="/opening" className="settings-section__link">
        {t("settings.cost.opening")}
      </Link>
      <div className="settings-section__row">
        <Select
          label={t("settings.cost.method")}
          value={draft}
          disabled={!canManage}
          onValueChange={(v) => setDraft(v as Method)}
          options={[
            { value: "fifo", label: t("settings.cost.fifo") },
            { value: "average", label: t("settings.cost.average") },
          ]}
          help={t(`settings.cost.help.${draft}`)}
        />
        {canManage && (
          <Button variant="primary" disabled={!changed} onClick={() => setAsking(true)}>
            {t("settings.save")}
          </Button>
        )}
      </div>
      {asking && (
        <Confirm title={t("settings.cost.confirmTitle")} action={t("settings.cost.confirm")} destructive={false} loading={save.isPending} onConfirm={() => save.mutate(draft)} onClose={() => setAsking(false)}>
          {t("settings.cost.confirmText", { method: t(`settings.cost.${draft}`) })}
        </Confirm>
      )}
    </section>
  );
}
