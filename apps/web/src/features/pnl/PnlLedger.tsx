// Foyda va zarar hisob varag'i (M5, 04 §6.1 + §7.4): to'liq qatorlar (Uzum xarajatlari turlari, o'z xarajatlari
// toifalari, yalpi foyda) va ustunlar: joriy davr, tushumga nisbatan, oldingi davr, farq, o'zgarish. Qator bosilsa —
// drill-down. Uzum bonusi (bepul logistika) haqiqiy hisobga hech narsa qo'shmaydi — ADR-031.
// Tor ekranda (< 640 px) faqat joriy summa va o'zgarish qoladi (gorizontal skroll yo'q).
import { useTranslation } from "react-i18next";

import { FormulaPopover } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";
import { Change } from "../home/Change";
import type { PnlLine } from "./model";

type Props = { lines: PnlLine[]; onRow: (line: PnlLine) => void };

export function PnlLedger({ lines, onRow }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const percent = (v: string | null) => (v === null ? "—" : f.percent(v));
  return (
    <table className="ui-ledger pnl-ledger">
      <caption className="ui-visually-hidden">{t("pnl.caption")}</caption>
      <thead>
        <tr>
          <td aria-hidden />
          <th scope="col">{t("pnl.col.line")}</th>
          <th scope="col" className="num">
            {t("pnl.col.amount")}
          </th>
          <th scope="col" className="num pnl-wide">
            {t("pnl.col.share")}
          </th>
          <th scope="col" className="num pnl-wide">
            {t("pnl.col.previous")}
          </th>
          <th scope="col" className="num pnl-wide">
            {t("pnl.col.diff")}
          </th>
          <td aria-hidden />
        </tr>
      </thead>
      <tbody>
        {lines.map((line) => (
          <tr key={line.key} className={cx(line.kind !== "row" && `is-${line.kind}`)}>
            <td className="ui-ledger__op" aria-hidden>
              {line.op}
            </td>
            <th scope="row" className="ui-ledger__label">
              <button type="button" className="ui-ledger__link" onClick={() => onRow(line)}>
                {line.label}
              </button>
              {line.formula && (
                <FormulaPopover
                  metric={line.label}
                  code={t(`home.formula.${line.formula}.code`)}
                  formula={t(`home.formula.${line.formula}.formula`)}
                  source={t(`home.formula.${line.formula}.source`)}
                />
              )}
            </th>
            <td className="ui-ledger__amount num">{f.money(line.amount, { unit: false })}</td>
            <td className="num pnl-wide">{percent(line.share)}</td>
            <td className="num pnl-wide">{f.money(line.previous, { unit: false })}</td>
            <td className="num pnl-wide">{f.money(line.diff, { unit: false })}</td>
            <td className="ui-ledger__change">
              <Change value={line.change} direction={line.direction} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
