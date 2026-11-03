// Foyda va zarar hisob varag'i (M5, 04 §6.1 + §7.4; ADR-037): to'liq qatorlar (Uzum xarajatlari turlari, o'z xarajatlari
// toifalari, yalpi foyda) va ustunlar: yakunlangan (Yakunlangan sotuvlar), kutilayotgan (Jarayondagi sotuvlar), jami, tushumga
// nisbatan, oldingi davr, farq, o'zgarish (jami bo'yicha). Qator bosilsa — drill-down. Uzum xarajatlari API bergandek
// (ADR-035), Uzum hali yozmagan logistika taxmini "≈" bilan belgilanadi (tamoyil 9).
// O'rta ekranda (< 1100 px) solishtirish ustunlari yashiriladi; tor ekranda (< 640 px) bitta pul ustuni — `part`
// (gorizontal skroll yo'q).
import { useTranslation } from "react-i18next";

import { FormulaPopover } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";
import { Change } from "../home/Change";
import type { Part, PnlLine } from "./model";

type Props = { lines: PnlLine[]; part: Part; onRow: (line: PnlLine) => void };

export function PnlLedger({ lines, part, onRow }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const percent = (v: string | null) => (v === null ? "—" : f.percent(v));
  const money = (line: PnlLine, value: string, mark: boolean) => (
    <>
      {mark && line.estimated && (
        <abbr className="pnl-estimated" title={t("pnl.estimatedMark")}>
          ≈{" "}
        </abbr>
      )}
      {f.money(value, { unit: false })}
    </>
  );
  return (
    <table className="ui-ledger pnl-ledger" data-part={part}>
      <caption className="ui-visually-hidden">{t("pnl.caption")}</caption>
      <thead>
        <tr>
          <td aria-hidden />
          <th scope="col">{t("pnl.col.line")}</th>
          <th scope="col" className="num" data-part="done">
            {t("pnl.col.done")}
          </th>
          <th scope="col" className="num" data-part="processing">
            {t("pnl.col.processing")}
          </th>
          <th scope="col" className="num" data-part="total">
            {t("pnl.col.total")}
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
          <td aria-hidden data-part="total" />
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
            <td className="ui-ledger__amount num" data-part="done">
              {money(line, line.done, false)}
            </td>
            <td className="ui-ledger__amount num pnl-expected-cell" data-part="processing">
              {money(line, line.processing, true)}
            </td>
            <td className="ui-ledger__amount num pnl-total-cell" data-part="total">
              {money(line, line.amount, true)}
            </td>
            <td className="num pnl-wide">{percent(line.share)}</td>
            <td className="num pnl-wide">{f.money(line.previous, { unit: false })}</td>
            <td className="num pnl-wide">{f.money(line.diff, { unit: false })}</td>
            <td className="ui-ledger__change" data-part="total">
              <Change value={line.change} direction={line.direction} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
