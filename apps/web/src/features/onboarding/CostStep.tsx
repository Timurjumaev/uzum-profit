// 6-qadam: tannarx (M2 5-qadam, B8.12): Excel (B7.1) yoki keyinroq Mahsulotlar / Ochilish jadvalidan. Tannarxsiz foyda ko'rinmaydi —
// shu sababli bu qadam eng muhimi; "Keyinroq" bosilsa Bosh sahifada "tannarx yo'q" ogohlantirishi va "Sozlash N/6" eslatib turadi.
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui";
import { CostImport } from "../opening/CostImport";

export function CostStep({ orgId, onDone }: { orgId: string; onDone: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="onb__form onb__form--wide">
      <h2>{t("onboarding.cost.title")}</h2>
      <p className="muted">{t("onboarding.cost.lead")}</p>
      <CostImport orgId={orgId} />
      <p className="caption">
        {t("onboarding.cost.table")}{" "}
        <Link to="/opening" className="settings-section__link">
          {t("onboarding.cost.openTable")}
        </Link>
      </p>
      <div className="onb__actions">
        <Button variant="primary" size="lg" onClick={onDone}>
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
