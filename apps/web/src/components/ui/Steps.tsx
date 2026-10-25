// Stepper (onboarding) va Timeline (Partiya yo'li, 04 §6.2): bajarilgan — to'la nuqta va sana, joriy — yarim
// (o'tgan kunlar va kutilgan sana), kelajak — bo'sh; kechikishda ikon + matn. Mobilda vertikal (CSS).
import { Check, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useFormat } from "../../lib/i18n";
import { cx } from "./cx";

export type StepState = "done" | "current" | "upcoming";

export function Stepper({ steps, label }: { steps: Array<{ label: string; state: StepState }>; label: string }) {
  return (
    <ol className="ui-stepper" aria-label={label}>
      {steps.map((s, i) => (
        <li key={s.label} className={`is-${s.state}`} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="ui-stepper__dot" aria-hidden>
            {s.state === "done" ? <Check size={14} /> : i + 1}
          </span>
          <span>{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export type Stage = {
  label: string;
  state: StepState;
  /** Bajarilgan sana. */
  date?: string;
  /** Joriy bosqich: necha kun o'tdi va kutilgan sana (F25). */
  days?: number;
  expected?: string;
  delayed?: boolean;
};

export function Timeline({ stages, label }: { stages: Stage[]; label: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  return (
    <ol className="ui-timeline" aria-label={label}>
      {stages.map((s) => (
        <li key={s.label} className={cx(`is-${s.state}`, s.delayed && "is-delayed")} aria-current={s.state === "current" ? "step" : undefined}>
          <span className="ui-timeline__dot" aria-hidden />
          <span className="ui-timeline__label">{s.label}</span>
          <span className="ui-visually-hidden">{t(`ui.status.${s.state}`)}</span>
          {s.date && <span className="caption num">{f.date(s.date).slice(0, 5)}</span>}
          {s.state === "current" && s.days !== undefined && (
            <span className="caption">{t("ui.daysPassed", { count: s.days })}</span>
          )}
          {s.expected && <span className="caption">{t("ui.expected", { date: f.date(s.expected).slice(0, 5) })}</span>}
          {s.delayed && (
            <span className="ui-text--warning caption">
              <TriangleAlert size={14} aria-hidden /> {t("ui.status.delayed")}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
