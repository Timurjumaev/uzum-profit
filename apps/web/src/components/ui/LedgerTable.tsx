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
  /** Oldingi davrga nisbatan o'zgarish katagi (to'rtinchi ustun; hech bir qatorda bo'lmasa ustun chizilmaydi). */
  trailing?: ReactNode;
  /** Tor ekranda (mobil, yig'ilgan ko'rinish) yashiriladigan qator — `compact` bilan birga. */
  compactHidden?: boolean;
};

export type LedgerTableProps = {
  caption: string;
  rows: LedgerRow[];
  onRowClick?: (row: LedgerRow) => void;
  /** Mobilda `compactHidden` qatorlar yashirin (CSS, < 640 px); "Hammasi" bosilganda `false`. */
  compact?: boolean;
};

export function LedgerTable({ caption, rows, onRowClick, compact = false }: LedgerTableProps) {
  const f = useFormat();
  const hasTrailing = rows.some((r) => r.trailing !== undefined);
  return (
    <table className="ui-ledger" data-compact={compact || undefined}>
      <caption className="ui-visually-hidden">{caption}</caption>
      <tbody>
        {rows.map((row) => {
          const amount = f.money(row.amount, { unit: false });
          return (
            <tr key={row.key} className={cx(row.kind && row.kind !== "row" && `is-${row.kind}`, row.compactHidden && "is-compact-hidden")}>
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
              {hasTrailing && <td className="ui-ledger__change">{row.trailing}</td>}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
