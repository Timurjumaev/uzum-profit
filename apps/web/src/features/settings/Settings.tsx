// Sozlamalar (M16, B4.8): bo'limlar ketma-ket — tannarx usuli, soliq profili, Uzum to'lov jadvali, muddatlar va qamrov,
// do'konlar, Uzum bonuslari. O'qish — egasi, menejer, buxgalter; yozish — egasi va menejer (do'konlar — faqat egasi).
// Hamma raqam va qoida serverdan (`/settings`); bu yerda faqat kiritish (tamoyil 4).
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, settingsQuery } from "../../app/query";
import { Banner, Button, Skeleton, PageHelp } from "../../components/ui";
import { CostMethod } from "./CostMethod";
import { FeeWaivers } from "./FeeWaivers";
import { InventorySettings } from "./InventorySettings";
import { Payouts } from "./Payouts";
import { Shops } from "./Shops";
import { TaxProfiles } from "./TaxProfiles";

const MANAGE_ROLES = ["owner", "manager"];

export function Settings() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const query = useQuery(settingsQuery(org.id));
  const canManage = MANAGE_ROLES.includes(org.role);
  const data = query.data;
  return (
    <section className="settings">
      <header className="settings__head">
        <div className="page-title">
          <h1 className="h2">{t("nav.settings")}</h1>
          <PageHelp page="settings" />
        </div>
      </header>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={8} />
      ) : (
        <>
          {!canManage && (
            <Banner tone="info" title={t("settings.readOnly")}>
              {t("settings.readOnlyText")}
            </Banner>
          )}
          <CostMethod orgId={org.id} value={data.cost_method} canManage={canManage} />
          <TaxProfiles orgId={org.id} data={data} canManage={canManage} />
          <Payouts orgId={org.id} data={data} canManage={canManage} />
          <InventorySettings orgId={org.id} data={data.inventory} canManage={canManage} />
          <Shops orgId={org.id} canEdit={org.role === "owner"} />
          <FeeWaivers orgId={org.id} canManage={canManage} />
        </>
      )}
    </section>
  );
}
