// Hisob varag'i (04 §6.1) — bosh sahifaning asosiy elementi: sof foyda (hero), uning ostida tushumdan sof foydagacha
// vertikal hisob. Qator bosilsa — drill-down (`Drill`). Mobilda yig'ilgan: tushum, Uzum to'lovi, sof foyda + "Hammasi".
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Banner, Button, FormulaPopover, LedgerTable, PageHelp, type LedgerRow } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { Dashboard } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { Change } from "./Change";
import { homeRows, rowLabel, type HomeRow } from "./model";

type Props = {
  data: Dashboard;
  onRow: (row: HomeRow) => void;
  /** "Tannarx kiritish" harakati (tannarx qamrovi < 100%). */
  costAction: ReactNode;
};

export function Ledger({ data, onRow, costAction }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const [expanded, setExpanded] = useState(false);

  const rows = useMemo(() => homeRows(data.rows, (code) => rowLabel(code, t)), [data.rows, t]);
  const net = rows.find((r) => r.key === "net_profit");

  const ledgerRows: LedgerRow[] = rows.map((row) => ({
    ...row,
    extra: row.formula ? (
      <FormulaPopover
        metric={row.label}
        code={t(`home.formula.${row.formula}.code`)}
        formula={t(`home.formula.${row.formula}.formula`)}
        source={t(`home.formula.${row.formula}.source`)}
      />
    ) : undefined,
    trailing: <Change value={row.change} direction={row.direction} />,
  }));

  const tone = net && Number(net.amount) < 0 ? "negative" : "positive";
  const { period: current, previous: prev } = data.meta;
  return (
    <section className="home-ledger" aria-labelledby="home-title">
      <div className="home-ledger__head">
        <div className="page-title">
          <h1 id="home-title" className="h2">
            {t("home.heroTitle", { period: f.period(current.start, current.end) })}
          </h1>
          <PageHelp page="home" />
        </div>
        <p className={cx("hero", `ui-text--${tone}`)} data-testid="net-profit">
          {net ? f.money(net.amount) : "—"}
        </p>
        {net?.change != null && (
          <p className="home-ledger__vs">
            <Change value={net.change} direction="income" />{" "}
            <span className="caption">{prev ? t("home.vsPrevious", { period: f.period(prev.start, prev.end) }) : ""}</span>
          </p>
        )}
      </div>
      <LedgerTable
        caption={t("home.ledger.caption")}
        rows={ledgerRows}
        compact={!expanded}
        onRowClick={(row) => onRow(rows.find((r) => r.key === row.key)!)}
      />
      <Button variant="ghost" className="home-ledger__toggle" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
        {expanded ? t("home.ledger.showLess") : t("home.ledger.showAll")}
      </Button>
      {data.attention.uncosted_lines > 0 && (
        <Banner tone="warning" title={t("home.coverage.title")} action={costAction}>
          {t("home.coverage.text", { value: f.number(data.attention.uncosted_lines), amount: f.money(data.attention.uncosted_revenue) })}
        </Banner>
      )}
    </section>
  );
}
