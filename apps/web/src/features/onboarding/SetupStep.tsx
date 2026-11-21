// 5-qadam: soliq, Uzum to'lov jadvali va tannarx usuli (M2 4-qadam, B8.12) — Sozlamalardagi bilan bir xil bo'limlar (bitta manba).
// Hamma maydon ixtiyoriy-to'ldiriladi: hozir bo'sh qoldirib, keyin Sozlamalardan qaytish mumkin ("Sozlash N/6" Bosh sahifada eslatadi).
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { settingsQuery } from "../../app/query";
import { Banner, Button, Skeleton } from "../../components/ui";
import { CostMethod } from "../settings/CostMethod";
import { Payouts } from "../settings/Payouts";
import { TaxProfiles } from "../settings/TaxProfiles";

export function SetupStep({ orgId, canManage, onDone }: { orgId: string; canManage: boolean; onDone: () => void }) {
  const { t } = useTranslation();
  const query = useQuery(settingsQuery(orgId));
  const data = query.data;
  return (
    <div className="onb__form onb__form--wide">
      <h2>{t("onboarding.setup.title")}</h2>
      <p className="muted">{t("onboarding.setup.lead")}</p>
      {query.isError && <Banner tone="negative" title={errorText(query.error, t)} />}
      {!data && !query.isError && <Skeleton label={t("common.loading")} lines={6} />}
      {data && (
        <>
          <TaxProfiles orgId={orgId} data={data} canManage={canManage} />
          <Payouts orgId={orgId} data={data} canManage={canManage} />
          <CostMethod orgId={orgId} value={data.cost_method} canManage={canManage} />
        </>
      )}
      <div className="onb__actions">
        <Button variant="primary" size="lg" onClick={onDone}>
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
