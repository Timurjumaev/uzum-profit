// Davr tanlash (04 §5): tayyor davrlar (Bugun … Hammasi) + kalendar (birinchi bosish — boshlanish, ikkinchi —
// tugash). Qiymat — "YYYY-MM-DD" juftligi; URL bilan bog'lash — chaqiruvchida (B3.5 topbar).
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { addMonths, matchPreset, monthGrid, presetRange, PRESETS, todayTashkent, type IsoDate, type Range } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { cx } from "./cx";
import { Popover } from "./Popover";

export type DateRangePickerProps = {
  value: Range;
  onChange: (range: Range) => void;
  /** Eng birinchi ma'lumot sanasi ("Hammasi" uchun). */
  first?: IsoDate;
  /** Bugun (testlar uchun; standart — Toshkent sanasi). */
  today?: IsoDate;
};

export function DateRangePicker({ value, onChange, first, today = todayTashkent() }: DateRangePickerProps) {
  const { t } = useTranslation();
  const f = useFormat();
  const preset = matchPreset(value, today, first);
  const label = preset ? `${t(`ui.presets.${preset}`)} · ${f.period(value.start, value.end)}` : f.period(value.start, value.end);
  return (
    <Popover
      trigger={
        <>
          <Calendar size={16} aria-hidden />
          {label}
        </>
      }
      label={`${t("ui.period")}: ${label}`}
    >
      {(close) => (
        <Panel
          value={value}
          today={today}
          first={first}
          onPick={(range) => {
            onChange(range);
            close();
          }}
        />
      )}
    </Popover>
  );
}

function Panel({ value, today, first, onPick }: { value: Range; today: IsoDate; first?: IsoDate; onPick: (r: Range) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [month, setMonth] = useState(value.end.slice(0, 7) + "-01");
  const [start, setStart] = useState<IsoDate | null>(null);
  const weekdays = monthGrid("2026-10-01")[1].map((d) => f.weekday(d!)); // dushanbadan boshlanadigan to'liq hafta
  const pick = (day: IsoDate) => {
    if (start === null) {
      setStart(day);
      return;
    }
    onPick(day < start ? { start: day, end: start } : { start, end: day });
  };
  const inRange = (day: IsoDate) =>
    start === null ? day >= value.start && day <= value.end : day === start;
  return (
    <div className="ui-daterange">
      <ul className="ui-daterange__presets">
        {PRESETS.map((p) => (
          <li key={p}>
            <button type="button" className="ui-btn ui-btn--ghost ui-btn--sm" onClick={() => onPick(presetRange(p, today, first))}>
              {t(`ui.presets.${p}`)}
            </button>
          </li>
        ))}
      </ul>
      <div className="ui-calendar">
        <div className="ui-calendar__head">
          <button type="button" className="ui-icon-btn" onClick={() => setMonth(addMonths(month, -1))} aria-label={t("ui.prevMonth")}>
            <ChevronLeft size={16} aria-hidden />
          </button>
          <span aria-live="polite">{f.month(month)}</span>
          <button type="button" className="ui-icon-btn" onClick={() => setMonth(addMonths(month, 1))} aria-label={t("ui.nextMonth")}>
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
        <table className="ui-calendar__grid">
          <thead>
            <tr>
              {weekdays.map((w) => (
                <th key={w} scope="col">
                  {w}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {monthGrid(month).map((week, i) => (
              <tr key={i}>
                {week.map((day, j) => (
                  <td key={j}>
                    {day && (
                      <button
                        type="button"
                        className={cx(
                          "ui-calendar__day",
                          inRange(day) && "is-selected",
                          inRange(day) && (start !== null || day === value.start || day === value.end) && "is-edge",
                          day === today && "is-today",
                        )}
                        disabled={day > today}
                        aria-pressed={inRange(day)}
                        aria-label={f.day(day)}
                        onClick={() => pick(day)}
                      >
                        {Number(day.slice(8))}
                      </button>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
