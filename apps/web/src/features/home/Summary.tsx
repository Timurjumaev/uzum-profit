// Uch raqam (ADR-037, M4) — bosh sahifaning asosiy elementi: tanlangan davr uchun Yakunlangan sof foyda (Yakunlangan
// sotuvlar) + Kutilayotgan sof foyda (Jarayondagi sotuvlar, F16) = Jami sof foyda (F12). Har ikki qism bir xil formula
// bilan: tushum − komissiya − logistika − tannarx − xarajatlar ulushi − soliq. Hisob varag'i (qatorlar) — Foyda
// sahifasida. Hamma raqam API'dan (`/dashboard`), bu yerda hisob yo'q (tamoyil 4).
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Banner, FormulaPopover, PageHelp } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { Dashboard } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { term } from "../../lib/i18n/glossary";
import { Change } from "./Change";
import { negate } from "./model";

const tone = (value: string) => (Number(value) < 0 ? "negative" : "positive");

type CardProps = {
  kind: "done" | "expected" | "total";
  /** Kartochka oldidagi amal belgisi (tenglama: yakunlangan + kutilayotgan = jami). */
  op?: "+" | "=";
  label: string;
  help: ReactNode;
  amount: string;
  testId: string;
  children?: ReactNode;
};

function Card({ kind, op, label, help, amount, testId, children }: CardProps) {
  const f = useFormat();
  return (
    <li className={cx("home-sum", `home-sum--${kind}`)}>
      {op && (
        <span className="home-sum__op" aria-hidden>
          {op}
        </span>
      )}
      <h2 className="home-sum__label label">
        {label}
        {help}
      </h2>
      <p className={cx("kpi", "num", "home-sum__amount", `ui-text--${tone(amount)}`)} data-testid={testId}>
        {f.money(amount)}
      </p>
      {children}
    </li>
  );
}

type Props = {
  data: Dashboard;
  /** "Tannarx kiritish" harakati (tannarx qamrovi < 100%). */
  costAction: ReactNode;
};

export function Summary({ data, costAction }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const s = data.statement;
  const e = data.expected;
  const net = data.rows.find((r) => r.code === "net_profit");
  const { period: current, previous: prev } = data.meta;
  const help = (key: "netDone" | "netExpected" | "netTotal", metric: string) => (
    <FormulaPopover
      metric={metric}
      code={t(`home.formula.${key}.code`)}
      formula={t(`home.formula.${key}.formula`)}
      source={t(`home.formula.${key}.source`)}
      estimatedReason={key === "netExpected" ? t("home.formula.netExpected.estimated") : undefined}
    />
  );
  const labels = { done: t(term("netDone")), expected: t(term("netExpected")), total: t("home.summary.total") };
  return (
    <section className="home-summary" aria-labelledby="home-title">
      <div className="page-title">
        <h1 id="home-title" className="h2">
          {t("home.heroTitle", { period: f.period(current.start, current.end) })}
        </h1>
        <PageHelp page="home" />
      </div>
      <ol className="home-summary__cards">
        <Card kind="done" label={labels.done} help={help("netDone", labels.done)} amount={s.net_profit_done} testId="net-done">
          <p className="caption">
            {s.units_done > 0
              ? t("home.summary.doneNote", { units: f.number(s.units_done), revenue: f.money(s.revenue_done) })
              : t("home.summary.doneEmpty")}
          </p>
          {Number(s.idle_expenses) !== 0 && (
            <p className="caption">{t("home.summary.idle", { amount: f.money(negate(s.idle_expenses)) })}</p>
          )}
        </Card>
        <Card kind="expected" op="+" label={labels.expected} help={help("netExpected", labels.expected)} amount={e.net_profit} testId="net-expected">
          {e.units > 0 ? (
            <>
              <p className="caption">{t("home.summary.expectedNote", { units: f.number(e.units), revenue: f.money(e.revenue) })}</p>
              <p className="caption">{e.rate === null ? t("home.summary.noRate") : t("home.summary.rate", { rate: f.percent(e.rate) })}</p>
              {e.logistics_estimated_units > 0 && (
                <p className="caption">{t("home.summary.logistics", { units: f.number(e.logistics_estimated_units) })}</p>
              )}
              {Number(e.uzum_estimated.advertising ?? 0) !== 0 && (
                <p className="caption">{t("home.summary.ads", { amount: f.money(e.uzum_estimated.advertising!) })}</p>
              )}
            </>
          ) : (
            <p className="caption">{t("home.summary.expectedEmpty")}</p>
          )}
        </Card>
        <Card kind="total" op="=" label={labels.total} help={help("netTotal", labels.total)} amount={s.net_profit} testId="net-profit">
          {net?.change != null && (
            <p className="home-summary__vs">
              <Change value={net.change} direction="income" />{" "}
              <span className="caption">{prev ? t("home.vsPrevious", { period: f.period(prev.start, prev.end) }) : ""}</span>
            </p>
          )}
          {s.margin !== null && <p className="caption">{t("home.summary.margin", { value: f.percent(s.margin) })}</p>}
        </Card>
      </ol>
      <Link to="/pnl" search={(prev) => prev} className="home-summary__how">
        {t("home.summary.how")}
      </Link>
      {data.attention.uncosted_lines > 0 && (
        <Banner tone="warning" title={t("home.coverage.title")} action={costAction}>
          {t("home.coverage.text", { value: f.number(data.attention.uncosted_lines), amount: f.money(data.attention.uncosted_revenue) })}
        </Banner>
      )}
    </section>
  );
}
