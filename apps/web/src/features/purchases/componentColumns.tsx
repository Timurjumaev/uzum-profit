// Xarajat komponentlari jadvali ustunlari (xarid va kargo sahifasi uchun umumiy): tur, summa, kurs (manbasi bilan —
// "bozor kursi, Markaziy bank emas" belgilanadi), so'mda, taqsimot, tovarlar; o'zgartirish tugmalari faqat `actions` bilan.
import { useTranslation } from "react-i18next";

import { Badge, Button, type Column } from "../../components/ui";
import type { CostComponent } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Actions = { onEdit: (c: CostComponent) => void; onDelete: (c: CostComponent) => void; deleting: string | null };

export function useComponentColumns(actions?: Actions): Column<CostComponent>[] {
  const { t } = useTranslation();
  const f = useFormat();
  const rateText = (c: CostComponent) => {
    if (c.error) return <Badge tone="negative">{c.error}</Badge>;
    if (c.applied_rate === null) return "—";
    return t("purchases.components.rateOn", {
      rate: f.number(c.applied_rate, { digits: 2, trim: true }),
      mode: t(`purchases.components.rateLabel.${c.rate_mode === "cbu" && c.rate_source === "market" ? "market" : c.rate_mode}`),
      date: c.rate_day ? f.date(c.rate_day) : "",
    });
  };
  return [
    { key: "kind", header: t("purchases.components.col.kind"), render: (c) => c.type_name ?? t(`purchases.components.kind.${c.kind}`) },
    { key: "amount", header: t("purchases.components.col.amount"), numeric: true, render: (c) => (c.currency === "UZS" ? f.money(c.amount, { unit: false }) : f.currency(c.amount, c.currency)) },
    { key: "rate", header: t("purchases.components.col.rate"), render: rateText },
    { key: "uzs", header: t("purchases.components.col.uzs"), numeric: true, render: (c) => (c.amount_uzs === null ? "—" : f.money(c.amount_uzs, { unit: false })) },
    { key: "allocation", header: t("purchases.components.col.allocation"), render: (c) => t(`purchases.components.allocation.${c.allocation}`) },
    {
      key: "lines",
      header: t("purchases.components.col.lines"),
      render: (c) => (c.lines === null ? t("purchases.components.allLines") : t("purchases.components.someLines", { count: c.lines.length })),
    },
    ...(actions
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (c: CostComponent) => {
              const name = c.type_name ?? t(`purchases.components.kind.${c.kind}`);
              return (
                <span className="expenses-actions">
                  <Button variant="ghost" onClick={() => actions.onEdit(c)} aria-label={`${t("purchases.components.edit")}: ${name}`}>
                    {t("purchases.components.edit")}
                  </Button>
                  <Button variant="ghost" loading={actions.deleting === c.id} onClick={() => actions.onDelete(c)} aria-label={`${t("purchases.components.delete")}: ${name}`}>
                    {t("purchases.components.delete")}
                  </Button>
                </span>
              );
            },
          },
        ]
      : []),
  ];
}
