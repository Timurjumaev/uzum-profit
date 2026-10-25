// Jadval (04 §5): sarlavha 12/500, qator 13 px, balandlik 36 (zich 32, keng 44); raqamlar o'ngga, tabular, qatorga
// bo'linmaydi; birinchi ustun gorizontal skrollda qotadi; jami qatori `rule` bilan. Ustun tanlash, saqlangan
// ko'rinish, eksport va 500+ qatorda virtual — B4.3 (Mahsulotlar) da shu komponentga qo'shiladi.
import type { ReactNode } from "react";

import { cx } from "./cx";

export type Column<T> = {
  key: string;
  header: string;
  numeric?: boolean;
  render: (row: T) => ReactNode;
};

export type DataTableProps<T> = {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  total?: Record<string, ReactNode>;
  density?: "compact" | "normal" | "comfortable";
  empty?: ReactNode;
};

export function DataTable<T>({ caption, columns, rows, rowKey, total, density = "normal", empty }: DataTableProps<T>) {
  return (
    <div className="ui-table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table className={cx("ui-table", `ui-table--${density}`)}>
        <caption className="ui-visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cx(c.numeric && "num")}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty && (
            <tr>
              <td colSpan={columns.length}>{empty}</td>
            </tr>
          )}
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c, i) =>
                i === 0 ? (
                  <th key={c.key} scope="row" className={cx(c.numeric && "num")}>
                    {c.render(row)}
                  </th>
                ) : (
                  <td key={c.key} className={cx(c.numeric && "num")}>
                    {c.render(row)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
        {total && (
          <tfoot>
            <tr>
              {columns.map((c, i) =>
                i === 0 ? (
                  <th key={c.key} scope="row">
                    {total[c.key]}
                  </th>
                ) : (
                  <td key={c.key} className={cx(c.numeric && "num")}>
                    {total[c.key]}
                  </td>
                ),
              )}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
