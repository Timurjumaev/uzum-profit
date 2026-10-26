// Foyda va zarar (M5, B4.2). Maket — 04 §7.4: yuqorida hisob varag'i to'liq (ustunlar: joriy, tushumga nisbatan,
// oldingi davr, farq), ostida sharshara va kutilayotgan blok (F16), keyin kesimlar (oylar / do'konlar / SKU).
// Tannarx qamrovi < 100% — sariq banner (F15); bepul logistika davri — "Standart tarif bo'yicha foyda" (F40).
// Hamma raqam API'dan (`/pnl`), drill-down — bosh sahifadagi `Drill` (sotuvlar, Uzum toifasi, o'z xarajatlari).
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useSearch } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, meQuery, pnlQuery, syncQuery } from "../../app/query";
import { pnlSearch } from "../../app/search";
import { WaterfallChart } from "../../components/charts";
import { Banner, Button, EmptyState, Skeleton } from "../../components/ui";
import { useFormat } from "../../lib/i18n";
import { syncSummary } from "../../lib/sync";
import { Drill } from "../home/Drill";
import { rowLabel } from "../home/model";
import { Breakdown } from "./Breakdown";
import { pnlLines, waterfallSteps, type PnlLine, type View } from "./model";
import { Pending } from "./Pending";
import { PnlLedger } from "./PnlLedger";

export function Pnl() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  // Bola marshrutga ota marshrutning xom qidiruvi ham keladi — qiymat shu yerda ham tekshiriladi (app/search).
  const view: View = pnlSearch(useSearch({ strict: false }) as Record<string, unknown>).view ?? "month";
  const params = useMemo(
    () => ({ shops: filters.shops, start: filters.range.start, end: filters.range.end }),
    [filters.shops, filters.range.start, filters.range.end],
  );
  const query = useQuery({ ...pnlQuery(org.id, params, view), placeholderData: keepPreviousData });
  const sync = useQuery(syncQuery(org.id));
  const [drill, setDrill] = useState<PnlLine | null>(null);

  const data = query.data;
  const lines = useMemo(() => (data ? pnlLines(data.rows, (code) => rowLabel(code, t), t("terms.grossProfit")) : []), [data, t]);
  const steps = useMemo(() => (data ? waterfallSteps(data.statement, (key) => t(`pnl.waterfall.${key}`)) : []), [data, t]);

  if (query.isError && !data) {
    return (
      <section className="pnl">
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  }
  if (!data) {
    return (
      <section className="pnl" aria-busy>
        <h1 className="ui-visually-hidden">{t("nav.pnl")}</h1>
        <Skeleton label={t("common.loading")} lines={10} />
      </section>
    );
  }

  const s = data.statement;
  const summary = sync.data ? syncSummary(sync.data) : null;
  const emptyState = summary?.state === "never" ? "never" : summary && summary.state !== "fresh" ? "partial" : "none";
  const { period: current, previous } = data.meta;
  const std = data.standard;
  return (
    <section className="pnl" aria-busy={query.isPlaceholderData || undefined}>
      <header className="pnl__head">
        <h1 className="h2">{t("pnl.title", { period: f.period(current.start, current.end) })}</h1>
        {previous && <p className="caption">{t("pnl.previousNote", { period: f.period(previous.start, previous.end) })}</p>}
      </header>
      {filters.compare === "lastYear" && <Banner tone="info" title={t("home.lastYearSoon")} />}
      {s.lines === 0 && (
        <EmptyState
          title={t(`home.empty.${emptyState}`)}
          text={t(`home.empty.${emptyState}Text`)}
          action={
            emptyState === "none" ? undefined : (
              <Link to="/status" search={(prev) => prev} className="ui-btn ui-btn--secondary ui-btn--md">
                {t("home.empty.status")}
              </Link>
            )
          }
        />
      )}
      {s.uncovered.lines > 0 && (
        <Banner
          tone="warning"
          title={t("home.coverage.title")}
          action={
            <Link to="/products" search={(prev) => prev} className="ui-btn ui-btn--secondary ui-btn--md">
              {t("home.coverage.action")}
            </Link>
          }
        >
          {t("pnl.coverageText", { value: f.number(s.uncovered.lines), amount: f.money(s.uncovered.revenue) })}
        </Banner>
      )}
      {data.recalculated > 0 && <Banner tone="info" title={t("pnl.recalculated", { value: f.number(data.recalculated) })} />}

      <div className="pnl-ledger-box">
        <PnlLedger data={data} lines={lines} onRow={setDrill} />
        {std && (
          <p className="caption">
            {t("pnl.standard.note", { amount: f.money(std.logistics), lines: f.number(std.lines) })}
            {std.unpriced_lines > 0 && <> {t("pnl.standard.unpriced", { value: f.number(std.unpriced_lines) })}</>}
          </p>
        )}
      </div>

      <div className="pnl__row">
        <WaterfallChart title={t("pnl.waterfall.title")} steps={s.lines === 0 ? [] : steps} />
        <Pending orgId={org.id} data={data} />
      </div>

      <Breakdown orgId={org.id} data={data} view={view} busy={query.isPlaceholderData} />
      <Drill orgId={org.id} params={params} row={drill} onClose={() => setDrill(null)} />
    </section>
  );
}
