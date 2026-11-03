// Foyda va zarar (M5, ADR-037) — "qanday hisoblandi": hisob varag'i to'liq, har qator uch ustunda — yakunlangan (Yakunlangan
// sotuvlar), kutilayotgan (Jarayondagi sotuvlar), jami — va oldingi davr bilan solishtirish; ostida sharshara (jami) va
// kutilayotgan sof foyda bloki (F16), keyin kesimlar (oylar / do'konlar / SKU). Maket — 04 §7.4. Tannarx qamrovi < 100%
// — sariq banner (F15). Uzum xarajatlari API bergandek (ADR-035), Uzum hali yozmagan logistika — taxminiy (F5, "≈").
// Hamma raqam API'dan (`/pnl`), drill-down — `home/Drill` (sotuvlar, Uzum toifasi, o'z xarajatlari).
import { keepPreviousData, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useSearch } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, meQuery, pnlQuery, syncQuery } from "../../app/query";
import { pnlSearch } from "../../app/search";
import { WaterfallChart } from "../../components/charts";
import { Banner, Button, EmptyState, Skeleton, PageHelp, Segmented } from "../../components/ui";
import { useFormat } from "../../lib/i18n";
import { syncSummary } from "../../lib/sync";
import { Drill } from "../home/Drill";
import { rowLabel } from "../home/model";
import { Breakdown } from "./Breakdown";
import { Expected } from "./Expected";
import { PARTS, pnlLines, waterfallSteps, type Part, type PnlLine, type View } from "./model";
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
  const [part, setPart] = useState<Part>("total"); // tor ekranda ko'rinadigan pul ustuni

  const data = query.data;
  const lines = useMemo(() => {
    if (!data) return [];
    // Taxminiy qismli qatorlar (≈): kutilayotgan logistika (F5) va Uzum xarajatlari — kutilayotgan reklama (F42).
    const estimates = new Map<string, string>(
      Object.entries(data.statement.uzum_estimated)
        .filter(([, amount]) => Number(amount) !== 0)
        .map(([category, amount]) => [`uzum:${category}`, amount]),
    );
    if (Number(data.statement.logistics_estimated) !== 0) estimates.set("logistics", data.statement.logistics_estimated);
    return pnlLines(data.rows, (code) => rowLabel(code, t), t("terms.grossProfit")).map((l) =>
      estimates.has(l.key) ? { ...l, estimated: true, estimate: l.key === "logistics" ? undefined : estimates.get(l.key) } : l,
    );
  }, [data, t]);
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
  return (
    <section className="pnl" aria-busy={query.isPlaceholderData || undefined}>
      <header className="pnl__head">
        <div className="page-title">
          <h1 className="h2">{t("pnl.title", { period: f.period(current.start, current.end) })}</h1>
          <PageHelp page="pnl" />
        </div>
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
        <p className="caption pnl-ledger-box__note">{t("pnl.partsNote")}</p>
        <Segmented
          label={t("pnl.partLabel")}
          className="pnl-parts"
          value={part}
          onChange={setPart}
          options={PARTS.map((p) => ({ value: p, label: t(`pnl.col.${p}`) }))}
        />
        <PnlLedger lines={lines} part={part} onRow={setDrill} />
        {s.logistics_estimated_units > 0 && (
          <p className="caption">
            {t("pnl.logisticsEstimated", { amount: f.money(s.logistics_estimated), units: f.number(s.logistics_estimated_units) })}
          </p>
        )}
        {s.logistics_missing_lines > 0 && <p className="caption">{t("pnl.logisticsMissing", { value: f.number(s.logistics_missing_lines) })}</p>}
        {Number(s.uzum_estimated.advertising ?? 0) !== 0 && (
          <p className="caption">{t("pnl.adsEstimated", { amount: f.money(s.uzum_estimated.advertising!) })}</p>
        )}
      </div>

      <div className="pnl__row">
        <WaterfallChart title={t("pnl.waterfall.title")} steps={s.lines === 0 ? [] : steps} />
        <Expected orgId={org.id} data={data} />
      </div>

      <Breakdown orgId={org.id} data={data} view={view} busy={query.isPlaceholderData} />
      <Drill orgId={org.id} params={params} row={drill} onClose={() => setDrill(null)} />
    </section>
  );
}
