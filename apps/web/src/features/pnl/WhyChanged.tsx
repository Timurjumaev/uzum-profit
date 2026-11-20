// "Nega o'zgardi" (B5.6, F56): sof foyda farqi omillarga — hajm, narx, komissiya, logistika, tannarx, reklama, boshqa Uzum
// xarajatlari, o'z xarajatlari, soliq. Omillar yig'indisi = farq (server hisoblaydi; bu yerda faqat ko'rsatish).
import { useTranslation } from "react-i18next";

import { FormulaPopover } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { Pnl } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

const sign = (value: string) => (Number(value) < 0 ? "negative" : "positive");

export function WhyChanged({ data }: { data: Pnl }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { why } = data;
  const rows = why.factors.filter((x) => Number(x.amount) !== 0).sort((a, b) => Math.abs(Number(b.amount)) - Math.abs(Number(a.amount)));
  const max = Math.max(1, ...rows.map((x) => Math.abs(Number(x.amount))));
  const title = t("pnl.why.title");
  return (
    <section aria-labelledby="pnl-why" className="pnl-why">
      <h2 id="pnl-why" className="h3">
        {title}{" "}
        <FormulaPopover metric={title} code="F56" formula={t("pnl.why.formula")} source={t("pnl.why.source")} />
      </h2>
      {data.previous.lines === 0 ? (
        <p className="muted">{t("pnl.why.noPrevious")}</p>
      ) : rows.length === 0 ? (
        <p className="muted">{t("pnl.why.same")}</p>
      ) : (
        <>
          <p className="pnl-why__total">
            <span className="label">{t("pnl.why.total")}</span>{" "}
            <strong className={cx("kpi", `ui-text--${sign(why.diff)}`)}>{f.money(why.diff)}</strong>
          </p>
          <ul className="pnl-why__list">
            {rows.map((x) => (
              <li key={x.code} className="pnl-why__row">
                <span className="pnl-why__name">{t(`pnl.why.code.${x.code}`)}</span>
                <span className="pnl-why__bar" aria-hidden>
                  <span className={cx("pnl-why__fill", `is-${sign(x.amount)}`)} style={{ inlineSize: `${(Math.abs(Number(x.amount)) / max) * 100}%` }} />
                </span>
                <strong className={`ui-text--${sign(x.amount)}`}>{f.money(x.amount)}</strong>
              </li>
            ))}
          </ul>
          <p className="caption">{t("pnl.why.note")}</p>
        </>
      )}
    </section>
  );
}
