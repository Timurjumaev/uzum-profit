// Jadval (04 §5): sarlavha 12/500, qator 13 px, balandlik 36 (zich 32, keng 44); raqamlar o'ngga, tabular, qatorga
// bo'linmaydi; birinchi ustun gorizontal skrollda qotadi; jami qatori `rule` bilan. Saralanadigan ustun — sarlavhada
// tugma (`aria-sort`, ikon + yo'nalish matni); 500+ qatorda virtual skroll (faqat ko'rinadigan qatorlar chiziladi,
// qator balandligi qat'iy). Ustun tanlash va saqlangan ko'rinish — sahifa darajasida (`features/products`),
// eksport — B4.10.
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cx } from "./cx";

export type Column<T> = {
  key: string;
  header: string;
  numeric?: boolean;
  render: (row: T) => ReactNode;
  /** Sarlavha yonidagi "?" (FormulaPopover) — saralash tugmasidan tashqarida. */
  help?: ReactNode;
  /** Saralash kaliti (`onSort` ga beriladi); yo'q bo'lsa ustun saralanmaydi. */
  sortKey?: string;
};

export type SortState = { key: string; desc: boolean };

export type DataTableProps<T> = {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  total?: Record<string, ReactNode>;
  density?: "compact" | "normal" | "comfortable";
  empty?: ReactNode;
  sort?: SortState;
  onSort?: (sortKey: string) => void;
  /** Shundan ko'p qatorda virtual skroll (standart 500). */
  virtualFrom?: number;
};

const ROW_HEIGHT = { compact: 32, normal: 36, comfortable: 44 } as const;
const OVERSCAN = 8;
const FALLBACK_VIEWPORT = 600; // o'lchov yo'q muhit (test): ~17 qator

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  total,
  density = "normal",
  empty,
  sort,
  onSort,
  virtualFrom = 500,
}: DataTableProps<T>) {
  const { t } = useTranslation();
  const wrap = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(FALLBACK_VIEWPORT);
  const virtual = rows.length > virtualFrom;
  const height = ROW_HEIGHT[density];
  let from = 0;
  let to = rows.length;
  if (virtual) {
    from = Math.max(0, Math.floor(scrollTop / height) - OVERSCAN);
    to = Math.min(rows.length, Math.ceil((scrollTop + viewport) / height) + OVERSCAN);
  }
  // Ko'rinadigan balandlik o'lchanadi (o'lchov yo'q muhit — standart qiymat).
  useLayoutEffect(() => {
    if (virtual && wrap.current?.clientHeight) setViewport(wrap.current.clientHeight);
  }, [virtual]);
  const shown = virtual ? rows.slice(from, to) : rows;
  return (
    <div
      ref={wrap}
      className={cx("ui-table-wrap", virtual && "ui-table-wrap--virtual")}
      tabIndex={0}
      role="region"
      aria-label={caption}
      onScroll={virtual ? (e) => setScrollTop(e.currentTarget.scrollTop) : undefined}
    >
      <table className={cx("ui-table", `ui-table--${density}`)} aria-rowcount={virtual ? rows.length + 1 : undefined}>
        <caption className="ui-visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => {
              const sorted = sort && c.sortKey !== undefined && sort.key === c.sortKey ? (sort.desc ? "descending" : "ascending") : undefined;
              return (
                <th key={c.key} scope="col" className={cx(c.numeric && "num")} aria-sort={c.sortKey !== undefined ? (sorted ?? "none") : undefined}>
                  {c.sortKey !== undefined && onSort ? (
                    <button type="button" className="ui-sort" onClick={() => onSort(c.sortKey!)} title={t("ui.sortBy", { name: c.header })}>
                      {c.header}
                      {sorted === "ascending" ? (
                        <ArrowUp size={14} aria-label={t("ui.ascending")} />
                      ) : sorted === "descending" ? (
                        <ArrowDown size={14} aria-label={t("ui.descending")} />
                      ) : (
                        <ChevronsUpDown size={14} aria-hidden />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                  {c.help}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty && (
            <tr>
              <td colSpan={columns.length}>{empty}</td>
            </tr>
          )}
          {virtual && from > 0 && (
            <tr aria-hidden className="ui-table__spacer" style={{ height: from * height }}>
              <td colSpan={columns.length} />
            </tr>
          )}
          {shown.map((row, n) => (
            <tr key={rowKey(row)} aria-rowindex={virtual ? from + n + 2 : undefined}>
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
          {virtual && to < rows.length && (
            <tr aria-hidden className="ui-table__spacer" style={{ height: (rows.length - to) * height }}>
              <td colSpan={columns.length} />
            </tr>
          )}
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
