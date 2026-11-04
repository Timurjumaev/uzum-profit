// KPI sarhisob (ADR-043, M4): "Buyurtmadan sof foydagacha" yo'li va 4 guruh kartochka — buyurtmalar va tushum, Uzum
// xarajatlari va foyda, qaytarilgan va bekor qilingan, o'rtacha ko'rsatkichlar. Har kartochkada: qiymat, oldingi davrga
// nisbatan o'zgarish (pul va sonlarda nisbiy, ulushlarda — punkt; rang = yo'nalish × yaxshimi), oldingi davr qiymati,
// trend chizig'i va formula ("?"). Hamma raqam API'dan (`/dashboard` → `summary`), bu yerda hisob yo'q (tamoyil 4);
// yo'l chiziqlari kengligi — faqat chizish uchun nisbat.
import { Link } from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { FormulaPopover } from "../../components/ui";
import { changeTone, Sparkline } from "../../components/ui/Kpi";
import { cx } from "../../components/ui/cx";
import type { Dashboard } from "../../lib/api/types";
import type { Formatter } from "../../lib/format";
import { useFormat } from "../../lib/i18n";

type Summary = Dashboard["summary"];
type Card = Summary["groups"][number]["cards"][number];

/** Asosiy kartochkalar — ajratib ko'rsatiladi (tushum va sof foyda); sof foyda keng ekranda 2 ustun. */
const KEY_CARDS = new Set(["revenue", "net_profit"]);
const WIDE_CARDS = new Set(["net_profit"]);

export function formatValue(f: Formatter, unit: Card["unit"], value: string | null): string {
  if (value === null) return "—";
  if (unit === "money") return f.money(value);
  if (unit === "ratio") return f.percent(value);
  if (unit === "number") return f.number(value, { digits: 2 });
  return f.number(value);
}

function SummaryCard({ card, note }: { card: Card; note?: ReactNode }) {
  const { t } = useTranslation();
  const f = useFormat();
  const label = t(`home.kpi.cards.${card.key}.label`);
  const tone = card.change != null && card.good ? changeTone(card.change, card.good) : "neutral";
  const change = card.change == null ? null : card.unit === "ratio" ? f.points(card.change) : f.change(card.change);
  const points = card.series.filter((x): x is string => x !== null).map(Number);
  return (
    <li
      className={cx("home-card", `home-card--${card.unit}`, KEY_CARDS.has(card.key) && "home-card--key", WIDE_CARDS.has(card.key) && "home-card--wide", card.warn && "home-card--warn")}
      data-testid={`kpi-${card.key}`}
    >
      <div className="home-card__label label">
        {label}
        <FormulaPopover
          metric={label}
          code={card.formula}
          formula={t(`home.kpi.cards.${card.key}.formula`)}
          source={t(`home.kpi.cards.${card.key}.source`)}
        />
      </div>
      <p className="home-card__value num">{formatValue(f, card.unit, card.value)}</p>
      <p className="home-card__delta">
        {change && <span className={cx("home-card__change", `ui-text--${tone}`)}>{change}</span>}
        {card.previous !== null && (
          <span className="caption">{t("home.kpi.previous", { value: formatValue(f, card.unit, card.previous) })}</span>
        )}
      </p>
      {note}
      {card.warn && (
        <p className="home-card__warn caption">
          <TriangleAlert size={14} aria-hidden /> {t("home.kpi.warn")}{" "}
          <Link to="/settings" search={(prev) => prev} className="home-card__link">
            {t("home.kpi.warnAction")}
          </Link>
        </p>
      )}
      <Sparkline points={points} width={120} height={28} />
    </li>
  );
}

/** "Buyurtmadan sof foydagacha": yalpi buyurtmalar summasi → − bekor → − qaytarish → = tushum → − Uzum → = Uzumdan
 * keyin → sof foyda. Chiziq uzunligi — yalpi summaga nisbatan (chizish uchun). */
function Flow({ cards }: { cards: Map<string, Card> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const gross = Number(cards.get("gross_revenue")?.value ?? 0);
  if (!(gross > 0)) return null;
  const steps: { key: string; op: "" | "−" | "=" }[] = [
    { key: "gross_revenue", op: "" },
    { key: "cancel_revenue", op: "−" },
    { key: "return_revenue", op: "−" },
    { key: "revenue", op: "=" },
    { key: "uzum_costs", op: "−" },
    { key: "after_uzum", op: "=" },
    { key: "net_profit", op: "=" },
  ];
  return (
    <figure className="home-flow" aria-labelledby="home-flow-title">
      <figcaption id="home-flow-title" className="label">
        {t("home.kpi.flow.title")}
      </figcaption>
      <ol>
        {steps.map(({ key, op }) => {
          const card = cards.get(key);
          if (!card || card.value === null) return null;
          const value = Number(card.value);
          const width = Math.max(0, Math.min(1, Math.abs(value) / gross));
          return (
            <li key={key} className={cx("home-flow__step", `home-flow__step--${key}`, value < 0 && "is-negative")}>
              <span className="home-flow__op" aria-hidden>
                {op}
              </span>
              <span className="home-flow__name">{t(`home.kpi.flow.${key}`)}</span>
              <span className="home-flow__bar" aria-hidden>
                <span style={{ inlineSize: `${(width * 100).toFixed(2)}%` }} />
              </span>
              <span className="home-flow__value num">{f.money(card.value)}</span>
            </li>
          );
        })}
      </ol>
      {cards.get("net_profit") && <p className="caption">{t("home.kpi.flow.note")}</p>}
    </figure>
  );
}

export function KpiSummary({ data }: { data: Dashboard }) {
  const { t } = useTranslation();
  const f = useFormat();
  const s = data.summary;
  const cards = new Map(s.groups.flatMap((g) => g.cards.map((c) => [c.key, c] as const)));
  const { period, previous } = data.meta;
  const k = data.kpis;
  const uncovered = Number(k.uncovered_share) > 0 ? t("home.kpis.uncovered", { share: f.percent(k.uncovered_share) }) : null;
  return (
    <section aria-labelledby="home-kpi-title" className="home-kpi">
      <div className="home-kpi__head">
        <h2 id="home-kpi-title" className="h3">
          {t("home.kpi.title")}
        </h2>
        <p className="home-kpi__periods caption">
          <span className="home-kpi__period">
            {t("home.kpi.current")}: <strong>{f.period(period.start, period.end)}</strong>
          </span>
          {previous && (
            <span className="home-kpi__period">
              {t("home.kpi.previousPeriod")}: <strong>{f.period(previous.start, previous.end)}</strong>
            </span>
          )}
        </p>
      </div>
      <Flow cards={cards} />
      {s.groups.map((g) => (
        <section key={g.key} aria-labelledby={`home-kpi-${g.key}`} className={cx("home-kpi__group", `home-kpi__group--${g.key}`)}>
          <h3 id={`home-kpi-${g.key}`} className="home-kpi__group-title label">
            {t(`home.kpi.groups.${g.key}`)}
          </h3>
          <ul className="home-kpi__cards">
            {g.cards.map((card) => (
              <SummaryCard
                key={card.key}
                card={card}
                note={card.key === "margin" && uncovered ? <p className="caption home-card__note">{uncovered}</p> : undefined}
              />
            ))}
          </ul>
        </section>
      ))}
    </section>
  );
}
