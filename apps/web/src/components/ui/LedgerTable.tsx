// Hisob varag'i (04 §6.1): operator ustuni (−, =), summa tabular, oraliq summa ustida `rule`, yakun ostida
// `rule-double`; qator bosilsa (yoki Enter) — drill-down (chaqiruvchi Drawer ochadi).
import type { ReactNode } from "react";

import { useFormat } from "../../lib/i18n";
import { cx } from "./cx";

export type LedgerRow = {
  key: string;
  label: string;
  /** API satri ("−37284000.00" kabi ishora bilan). */
  amount: string;
  op?: "" | "+" | "−" | "=";
  kind?: "row" | "subtotal" | "total";
  extra?: ReactNode;
};

export type LedgerTableProps = {
  caption: string;
  rows: LedgerRow[];
  onRowClick?: (row: LedgerRow) => void;
};

export function LedgerTable({ caption, rows, onRowClick }: LedgerTableProps) {
  const f = useFormat();
  return (
    <table className="ui-ledger">
      <caption className="ui-visually-hidden">{caption}</caption>
      <tbody>
        {rows.map((row) => {
          const amount = f.money(row.amount, { unit: false });
          return (
            <tr key={row.key} className={cx(row.kind && row.kind !== "row" && `is-${row.kind}`)}>
              <td className="ui-ledger__op" aria-hidden>
                {row.op}
              </td>
              <th scope="row" className="ui-ledger__label">
                {onRowClick ? (
                  <button type="button" className="ui-ledger__link" onClick={() => onRowClick(row)}>
                    {row.label}
                  </button>
                ) : (
                  row.label
                )}
                {row.extra}
              </th>
              <td className="ui-ledger__amount num">{amount}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
