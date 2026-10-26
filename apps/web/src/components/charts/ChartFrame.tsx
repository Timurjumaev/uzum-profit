// Grafik ramkasi (04 §5, §5.1, §11): sarlavha, "Grafik | Jadval" almashtirgich (har grafikda; yengil ranglar —
// slot 3–5 — fonga < 3:1 bo'lgani uchun jadval majburiy, §4.4), legenda (≥ 2 seriya — doim), ekran o'quvchi uchun
// matnli tavsif (`role="img"`), bo'sh holat.
import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { cx } from "../ui/cx";
import { DataTable } from "../ui/DataTable";
import { EmptyState } from "../ui/Feedback";
import { cssColor } from "./palette";
import type { LegendItem, TableSpec } from "./types";

export type ChartScale = { from: string; to: string; minLabel: string; maxLabel: string };

export type ChartFrameProps = {
  title: string;
  /** Ekran o'quvchi uchun qisqa tavsif: nechta nuqta, eng yuqori/past qiymat. */
  summary: string;
  legend?: LegendItem[];
  /** Ketma-ket shkala (issiqlik xaritalari): rang gradienti va chekka yorliqlari. */
  scale?: ChartScale;
  table: TableSpec;
  empty?: boolean;
  children: ReactNode;
};

type View = "chart" | "table";
const VIEWS: View[] = ["chart", "table"];

function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="chart-legend">
      {items.map((item) => (
        <li key={item.key}>
          <i
            className={cx("chart-legend__mark", `chart-legend__mark--${item.shape}`)}
            style={{ background: item.color === "gradient" ? undefined : cssColor(item.color) }}
            aria-hidden
          />
          {item.name}
        </li>
      ))}
    </ul>
  );
}

export function ChartFrame({ title, summary, legend, scale, table, empty = false, children }: ChartFrameProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>("chart");
  const name = useId();
  return (
    <figure className="chart-frame">
      <figcaption className="chart-frame__head">
        <h3>{title}</h3>
        {!empty && (
          <fieldset className="ui-segmented chart-frame__views">
            <legend className="ui-visually-hidden">{t("charts.view.label")}</legend>
            {VIEWS.map((v) => (
              <label key={v} className={cx("ui-segmented__item", view === v && "is-checked")}>
                <input type="radio" name={name} value={v} checked={view === v} onChange={() => setView(v)} />
                {t(`charts.view.${v}`)}
              </label>
            ))}
          </fieldset>
        )}
      </figcaption>
      {empty ? (
        <EmptyState title={t("charts.empty")} />
      ) : view === "table" ? (
        <DataTable
          caption={title}
          density="compact"
          columns={table.head.map((header, i) => ({ key: String(i), header, numeric: i > 0, render: (row: string[]) => row[i] }))}
          rows={table.rows}
          rowKey={(row) => row[0]}
          total={table.foot && Object.fromEntries(table.foot.map((cell, i) => [String(i), cell]))}
        />
      ) : (
        <>
          {legend && legend.length >= 2 && <Legend items={legend} />}
          <div role="img" aria-label={`${title}. ${summary}`}>
            {children}
          </div>
          {scale && (
            <div className="chart-scale" aria-hidden>
              <span>{scale.minLabel}</span>
              <i style={{ background: `linear-gradient(to right, ${scale.from}, ${scale.to})` }} />
              <span>{scale.maxLabel}</span>
            </div>
          )}
        </>
      )}
    </figure>
  );
}
