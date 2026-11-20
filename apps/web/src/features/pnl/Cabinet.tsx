// "Uzum kabineti ko'rsatadigan" (B5.0f, F57): kabinet "Tahlil"dagi "Foyda" = tushum − faqat komissiya. Sotuvchi kabinet bilan
// solishtirganda farqni tushunishi uchun — haqiqiy sof foyda alohida. Hisoblash serverda.
import { useTranslation } from "react-i18next";

import { FormulaPopover, Kpi } from "../../components/ui";
import type { Pnl } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

export function Cabinet({ data }: { data: Pnl }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { cabinet, statement } = data;
  if (statement.lines === 0) return null;
  const title = t("pnl.cabinet.title");
  return (
    <section aria-labelledby="pnl-cabinet" className="pnl-cabinet">
      <h2 id="pnl-cabinet" className="h3">
        {title}{" "}
        <FormulaPopover metric={title} code="F57" formula={t("pnl.cabinet.formula")} source={t("pnl.cabinet.source")} />
      </h2>
      <div className="pnl-cabinet__grid">
        <Kpi label={t("pnl.cabinet.profit")} value={f.money(cabinet.profit)} note={t("pnl.cabinet.profitNote")} />
        <Kpi label={t("pnl.cabinet.net")} value={f.money(statement.net_profit)} note={t("pnl.cabinet.netNote")} />
        <Kpi label={t("pnl.cabinet.gap")} value={f.money(cabinet.gap)} note={t("pnl.cabinet.gapNote")} />
      </div>
    </section>
  );
}
