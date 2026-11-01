// Drill-down (M4: "har qator bosilsa — manba yozuvlar"): o'ngdan Drawer. Sotuv qatorlari (tushum, komissiya, logistika,
// Uzum to'lovi, tannarx), Uzum toifasi xarajatlari yoki o'z xarajatlari; boshqa qatorlar boshqalardan hisoblanadi —
// faqat formula. Yig'indi (jami) — API qatoridan, yozuvlardan UI qayta hisoblamaydi (tamoyil 4).
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { expensesPage, salesPage, type ReportParams } from "../../app/query";
import { Badge, Button, DataTable, Drawer, Skeleton, type Column } from "../../components/ui";
import type { Expenses, Sale } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { negate, type HomeRow } from "./model";

type Props = { orgId: string; params: ReportParams; row: HomeRow | null; onClose: () => void };

/** Sotuv qatorining qaysi maydoni P&L qatorini tashkil qiladi. */
const SALE_FIELD = { revenue: "revenue", commission: "commission", logistics: "logistics", payout: "payout", cogs: "cogs" } as const;
type SaleField = (typeof SALE_FIELD)[keyof typeof SALE_FIELD];

function More({ hasMore, loading, onMore }: { hasMore: boolean; loading: boolean; onMore: () => void }) {
  const { t } = useTranslation();
  if (!hasMore) return null;
  return (
    <Button variant="secondary" loading={loading} onClick={onMore}>
      {t("home.drill.loadMore")}
    </Button>
  );
}

function Failure({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return <p role="alert">{errorText(error, t)}</p>;
}

function SalesBody({ orgId, params, field }: { orgId: string; params: ReportParams; field: SaleField }) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useInfiniteQuery({
    queryKey: ["orgs", orgId, "drill", "sales", params],
    queryFn: ({ pageParam }) => salesPage(orgId, params, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  if (query.isError) return <Failure error={query.error} />;
  if (query.isPending) return <Skeleton label={t("home.drill.loading")} lines={5} />;
  const items = query.data.pages.flatMap((p) => p.items);
  const columns: Column<Sale>[] = [
    { key: "day", header: t("home.drill.day"), render: (r) => f.date(r.day) },
    {
      key: "sku",
      header: t("home.drill.sku"),
      render: (r) => r.sku_title ?? t("home.drill.unlinked"),
    },
    { key: "units", header: t("home.drill.units"), numeric: true, render: (r) => f.number(r.amount) },
    {
      key: "value",
      header: t(`terms.${field}`),
      numeric: true,
      render: (r) => {
        const value = r[field];
        return (
          <>
            {r.cost_flags.length > 0 && field === "cogs" && <Badge tone="warning">{t("home.drill.estimated")}</Badge>} {value === null ? "—" : f.money(value, { unit: false })}
          </>
        );
      },
    },
  ];
  return (
    <>
      <DataTable caption={t("home.drill.sales")} density="compact" columns={columns} rows={items} rowKey={(r) => r.id} empty={t("home.drill.empty")} />
      <More hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onMore={() => void query.fetchNextPage()} />
    </>
  );
}

function UzumBody({ orgId, params, category }: { orgId: string; params: ReportParams; category: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useInfiniteQuery({
    queryKey: ["orgs", orgId, "drill", "uzum", category, params],
    queryFn: ({ pageParam }) => expensesPage(orgId, params, category, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  if (query.isError) return <Failure error={query.error} />;
  if (query.isPending) return <Skeleton label={t("home.drill.loading")} lines={5} />;
  const items = query.data.pages.flatMap((p) => p.items);
  const columns: Column<Expenses["items"][number]>[] = [
    { key: "day", header: t("home.drill.day"), render: (r) => f.date(r.day) },
    { key: "name", header: t("home.drill.name"), render: (r) => r.name ?? r.raw_code ?? r.code ?? "—" },
    // Chiqim — minus (hisob varag'idagi kabi), kirim (kompensatsiya) — plyus.
    { key: "amount", header: t("home.drill.amount"), numeric: true, render: (r) => f.money(r.type === "OUTCOME" ? negate(r.amount) : r.amount, { unit: false }) },
  ];
  return (
    <>
      <DataTable caption={t(`home.expense.${category}`, { defaultValue: category })} density="compact" columns={columns} rows={items} rowKey={(r) => r.id} empty={t("home.drill.empty")} />
      <More hasMore={query.hasNextPage} loading={query.isFetchingNextPage} onMore={() => void query.fetchNextPage()} />
    </>
  );
}

function OwnBody({ orgId, params, category }: { orgId: string; params: ReportParams; category: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useQuery({
    queryKey: ["orgs", orgId, "drill", "own", params],
    queryFn: () => expensesPage(orgId, params, null, null),
  });
  if (query.isError) return <Failure error={query.error} />;
  if (query.isPending) return <Skeleton label={t("home.drill.loading")} lines={4} />;
  const items = query.data.own_items.filter((x) => x.category === category);
  const columns: Column<Expenses["own_items"][number]>[] = [
    { key: "period", header: t("home.drill.period"), render: (r) => f.period(r.start_on, r.end_on) },
    { key: "note", header: t("home.drill.note"), render: (r) => r.note ?? "—" },
    { key: "amount", header: t("home.drill.amountInPeriod"), numeric: true, render: (r) => f.money(r.in_period, { unit: false }) },
  ];
  return (
    <>
      <p className="caption">{t("home.drill.onlyOwnPeriod")}</p>
      <DataTable caption={category} density="compact" columns={columns} rows={items} rowKey={(r) => r.id} empty={t("home.drill.empty")} />
    </>
  );
}

export function Drill({ orgId, params, row, onClose }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  if (!row) return null;
  const source = row.source;
  return (
    <Drawer open title={row.label} onClose={onClose}>
      <div className="home-drill">
        <p className="home-drill__total">
          <span className="label">{t("home.drill.total")}</span>
          <span className="kpi num">{f.money(row.amount)}</span>
        </p>
        {row.formula && (
          <p className="caption">
            {t(`home.formula.${row.formula}.code`)}: {t(`home.formula.${row.formula}.formula`)}. {t(`home.formula.${row.formula}.source`)}.
          </p>
        )}
        {source.type === "sales" && <SalesBody orgId={orgId} params={params} field={SALE_FIELD[row.key as keyof typeof SALE_FIELD]} />}
        {source.type === "uzum" && <UzumBody orgId={orgId} params={params} category={source.category!} />}
        {source.type === "own" && <OwnBody orgId={orgId} params={params} category={source.category!} />}
        {source.type === "none" && <p>{t("home.drill.calculated")}</p>}
      </div>
    </Drawer>
  );
}
