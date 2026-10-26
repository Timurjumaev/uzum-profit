// "Maʼlumotlar holati" (M3, tamoyil 8: "ma'lumot yo'q" ≠ "sinxron ishlamayapti"): har do'kon × ma'lumot turi — oxirgi
// muvaffaqiyatli sinxron, olingan yozuvlar, xato matni; akkaunt (kalit) holati va kvota. Yuqorida — umumiy holat va
// "Hozir yangilash". Uzilish banneri karkasda (har sahifada, `OutageBanner`).
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, syncQuery } from "../../app/query";
import { useRefreshSync } from "../../app/useRefreshSync";
import { Badge, Banner, Button, DataTable, EmptyState, Skeleton, StatusPill, type Column, type Tone } from "../../components/ui";
import { useFormat } from "../../lib/i18n";
import { syncSummary, type SyncStatus } from "../../lib/sync";

type KindRow = SyncStatus["shops"][number]["kinds"][number];

/** Oxirgi ish holati (API: running / ok / warning / error / skipped) → belgi. */
const RUN_TONE: Record<string, Tone> = { running: "info", ok: "positive", warning: "warning", error: "negative", skipped: "neutral" };
const ACCOUNT_TONE: Record<string, Tone> = {
  active: "positive",
  invalid: "negative",
  disconnected: "neutral",
  waf_blocked: "warning",
  quota_exhausted: "warning",
};

function KindTable({ shop }: { shop: SyncStatus["shops"][number] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const name = shop.alias || shop.name;
  const columns: Column<KindRow>[] = [
    { key: "kind", header: t("status.table.kind"), render: (r) => t(`sync.kinds.${r.kind}`, { defaultValue: r.kind }) },
    {
      key: "state",
      header: t("status.table.state"),
      render: (r) =>
        r.status ? (
          <StatusPill tone={RUN_TONE[r.status] ?? "neutral"}>{t(`status.run.${r.status}`, { defaultValue: r.status })}</StatusPill>
        ) : (
          <StatusPill>{t("status.run.none")}</StatusPill>
        ),
    },
    {
      key: "success",
      header: t("status.table.success"),
      render: (r) => (r.last_success_at ? f.relative(r.last_success_at) : t("sync.kindNever")),
    },
    {
      key: "records",
      header: t("status.table.records"),
      numeric: true,
      render: (r) =>
        r.fetched === null ? "—" : r.total ? t("ui.progress", { done: f.number(r.fetched), total: f.number(r.total) }) : f.number(r.fetched),
    },
    { key: "error", header: t("status.table.error"), render: (r) => r.error ?? "—" },
  ];
  return (
    <section className="status-shop" aria-labelledby={`status-${shop.id}`}>
      <div className="status-shop__head">
        <h2 id={`status-${shop.id}`}>{name}</h2>
        {!shop.active && <Badge>{t("status.inactive")}</Badge>}
        {shop.history_status && <Badge tone="info">{t("status.history", { period: shop.history_status })}</Badge>}
        {shop.errors_24h > 0 && <Badge tone="warning">{t("status.errors24h", { count: shop.errors_24h })}</Badge>}
        {shop.first_sale_on && <span className="caption">{t("status.firstSale", { date: f.date(shop.first_sale_on) })}</span>}
      </div>
      <DataTable
        caption={`${name}: ${t("status.title")}`}
        density="compact"
        columns={columns}
        rows={shop.kinds}
        rowKey={(r) => r.kind}
        empty={t("status.noRuns")}
      />
    </section>
  );
}

export function Status() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const query = useQuery(syncQuery(org.id));
  const refresh = useRefreshSync(org.id);
  const status = query.data;
  const summary = status ? syncSummary(status) : null;
  return (
    <section className="status">
      <header className="status__head">
        <div>
          <h1>{t("status.title")}</h1>
          <p className="muted">{summary?.at ? t("sync.updated", { ago: f.relative(summary.at) }) : t("status.lead")}</p>
        </div>
        <Button variant="primary" loading={refresh.isPending} disabled={status?.outage.active} onClick={() => refresh.mutate()}>
          {t("sync.refresh")}
        </Button>
      </header>

      {query.isError && <Banner tone="negative" title={errorText(query.error, t)} />}
      {summary && summary.state !== "fresh" && summary.state !== "outage" && (
        <Banner tone={summary.tone === "negative" ? "negative" : "warning"} title={t(`sync.${summary.state}`, { ago: summary.at ? f.relative(summary.at) : "" })}>
          <p>{t(`sync.${summary.state}Text`)}</p>
        </Banner>
      )}
      {query.isPending && <Skeleton label={t("common.loading")} lines={5} />}

      {status && status.accounts.length > 0 && (
        <section aria-labelledby="status-accounts">
          <h2 id="status-accounts">{t("status.accounts")}</h2>
          <ul className="status-accounts">
            {status.accounts.map((a) => (
              <li key={a.id}>
                <StatusPill tone={ACCOUNT_TONE[a.status] ?? "neutral"}>{t(`status.account.${a.status}`, { defaultValue: a.status })}</StatusPill>
                {a.quota_remaining !== null && <span className="caption">{t("status.quota", { value: f.number(a.quota_remaining) })}</span>}
                {a.checked_at && <span className="caption">{t("status.checked", { ago: f.relative(a.checked_at) })}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {status && status.shops.length === 0 && <EmptyState title={t("status.noShops")} text={t("status.noShopsText")} />}
      {status?.shops.map((shop) => <KindTable key={shop.id} shop={shop} />)}
    </section>
  );
}
