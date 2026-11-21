// Reja-fakt (M12, B5.8; F59): oylik maqsad — tushum, sof foyda, dona — butun tashkilot yoki bitta do'kon bo'yicha. Fakt, oy
// oxiri prognozi (Bosh sahifadagi bilan bitta hisob), bajarilish % va holat API'dan (`/goals`): bu yerda hisoblanmaydi
// (tamoyil 4). Maqsad Sozlamalar ruxsati bilan belgilanadi (ruxsat yo'q — server rad etadi, xabar chiqadi).
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, deleteGoal, goalsQuery, meQuery, setGoal } from "../../app/query";
import { Badge, Banner, Button, EmptyState, NumberInput, ProgressBar, Select, Skeleton, useToast, type Tone } from "../../components/ui";
import type { Goal } from "../../lib/api/types";
import { addMonths } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";

export const METRICS = ["revenue", "net_profit", "units"] as const;
type Metric = (typeof METRICS)[number];

const TONE: Record<Goal["status"], Tone> = { on_track: "positive", ahead: "info", behind: "negative", unknown: "neutral" };
const ORG = "";

const firstOfMonth = (iso: string) => `${iso.slice(0, 7)}-01`;

export function GoalsPage() {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const [month, setMonth] = useState<string | null>(null);
  const query = useQuery(goalsQuery(org.id, month));
  const data = query.data;
  const shown = data?.month ?? month;
  const [scope, setScope] = useState(ORG);
  const [metric, setMetric] = useState<Metric>("revenue");
  const [target, setTarget] = useState<string | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: ["orgs", org.id, "goals"] });
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const save = useMutation({
    mutationFn: () => setGoal(org.id, { month: shown ?? firstOfMonth(new Date().toISOString()), metric, target: target!, shop_id: scope === ORG ? null : scope }),
    onSuccess: async () => {
      toast.show(t("goals.saved"), "positive");
      setTarget(null);
      await refresh();
    },
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (id: string) => deleteGoal(org.id, id), onSuccess: refresh, onError: fail });
  const monthLabel = shown ? f.month(shown) : "";
  const shopName = (id: string | null) => (id === null ? t("goals.org") : (data?.shops.find((s) => s.id === id)?.name ?? t("goals.org")));
  const value = (g: Goal, v: string) => (g.metric === "units" ? t("goals.units", { value: f.number(v) }) : f.money(v));
  const groups = new Map<string | null, Goal[]>();
  for (const g of data?.goals ?? []) groups.set(g.shop_id, [...(groups.get(g.shop_id) ?? []), g]);
  const scopes = [...groups.keys()].sort((a, b) => (a === null ? -1 : b === null ? 1 : shopName(a).localeCompare(shopName(b))));
  const move = (delta: number) => shown && setMonth(addMonths(shown, delta));
  return (
    <section className="goals">
      <header className="goals__head">
        <h1 className="h2">{t("goals.title")}</h1>
        <div className="goals__month" role="group" aria-label={t("goals.month")}>
          <Button variant="ghost" size="sm" aria-label={t("goals.prev")} onClick={() => move(-1)} disabled={!shown}>
            ‹
          </Button>
          <strong data-testid="goals-month">{monthLabel}</strong>
          <Button variant="ghost" size="sm" aria-label={t("goals.next")} onClick={() => move(1)} disabled={!shown}>
            ›
          </Button>
        </div>
      </header>
      <p className="caption">{t("goals.lead")}</p>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={4} />
      ) : (
        <>
          {scopes.length === 0 ? (
            <EmptyState title={t("goals.empty")} text={t("goals.emptyText")} />
          ) : (
            scopes.map((key) => (
              <section key={key ?? ORG} className="goals__scope" aria-label={shopName(key)}>
                <h2 className="h3">{shopName(key)}</h2>
                {groups.get(key)!.map((g) => (
                  <article key={g.id} className="goals__card" data-testid={`goal-${g.metric}`}>
                    <ProgressBar value={Number(g.fact)} max={Number(g.target)} label={t(`goals.metric.${g.metric}`)} detail={`${value(g, g.fact)} / ${value(g, g.target)} · ${f.number(g.percent, { digits: 1, trim: true })}%`} />
                    <p className="caption goals__forecast">
                      {g.forecast === null ? t("goals.noForecast") : t("goals.forecast", { value: value(g, g.forecast), percent: f.number(g.forecast_percent ?? "0", { digits: 1, trim: true }) })}
                      <Badge tone={TONE[g.status]}>{t(`goals.status.${g.status}`)}</Badge>
                      <Button variant="ghost" size="sm" aria-label={t("goals.delete", { metric: t(`goals.metric.${g.metric}`) })} onClick={() => remove.mutate(g.id)}>
                        ✕
                      </Button>
                    </p>
                  </article>
                ))}
              </section>
            ))
          )}
          <form
            className="goals__form"
            onSubmit={(e) => {
              e.preventDefault();
              if (target !== null && Number(target) > 0) save.mutate();
            }}
          >
            <h2 className="h3">{t("goals.setTitle")}</h2>
            <Select label={t("goals.scope")} value={scope} onValueChange={setScope} options={[{ value: ORG, label: t("goals.org") }, ...data.shops.map((s) => ({ value: s.id, label: s.name }))]} />
            <Select label={t("goals.metricLabel")} value={metric} onValueChange={(v) => setMetric(v as Metric)} options={METRICS.map((m) => ({ value: m, label: t(`goals.metric.${m}`) }))} />
            <NumberInput label={t("goals.target")} value={target} onValueChange={setTarget} digits={metric === "units" ? 0 : undefined} />
            <Button type="submit" disabled={target === null || !(Number(target) > 0) || save.isPending}>
              {t("goals.save")}
            </Button>
          </form>
        </>
      )}
    </section>
  );
}
