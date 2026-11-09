// Uzum xarajatlari (M8, F9): toifalar bo'yicha ishorali yig'indi (kompensatsiya ayiriladi), oylar trendi, eng katta
// jarimalar va ro'yxat (toifa filtri bilan; P&L'ga kirmaganlari — sababi bilan). Yig'indi = P&L dagi F9.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { expensesListQuery, type ReportParams } from "../../app/query";
import { StackedBarChart, type SeriesInput } from "../../components/charts";
import { Badge, Banner, DataTable, EmptyState, ExportButton, FormulaPopover, Kpi, Pagination, Select, usePageSize, type Column } from "../../components/ui";
import type { Expenses, UzumExpenseItem } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

function useCategory() {
  const { t } = useTranslation();
  return (code: string) => t(`home.expense.${code}`, { defaultValue: code });
}

export function UzumExpenses({ orgId, params, data, page }: { orgId: string; params: ReportParams; data: Expenses; page: number | undefined }) {
  const { t } = useTranslation();
  const f = useFormat();
  const label = useCategory();
  const [category, setCategory] = useState("");
  const navigate = useNavigate();
  const [size, setSize] = usePageSize();
  const list = useQuery({ ...expensesListQuery(orgId, params, category, page, size), placeholderData: keepPreviousData });
  const goPage = (next: number | undefined) =>
    void navigate({ to: "/expenses", search: (prev) => ({ ...prev, page: next && next > 1 ? next : undefined }), replace: true });
  // So'ralgan sahifa oxirgisidan oshib ketgan bo'lsa API oxirgisini beradi — URL ham shunga o'tadi.
  const shown = list.data?.page;
  useEffect(() => {
    if (shown !== undefined && !list.isPlaceholderData && shown !== (page ?? 1)) goPage(shown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, list.isPlaceholderData, page]);
  if (data.uzum.length === 0 && data.items.length === 0) return <EmptyState title={t("expenses.uzum.empty")} text={t("expenses.uzum.emptyText")} />;

  const ordered = [...data.uzum].sort((a, b) => Number(b.amount) - Number(a.amount));
  const keys = ordered.map((c) => c.category);
  // 04 §4.3: 8 ta kategoriya rangi; undan ko'p toifa bo'lsa qolganlari "Boshqa" rangida (hech biri yashirilmaydi).
  const series: SeriesInput[] = keys.map((key, i) => ({
    key,
    name: label(key),
    color: i < 8 ? i + 1 : "other",
    values: data.by_month.map((m) => m.categories[key] ?? "0"),
  }));
  const share = (amount: string) => (Number(data.uzum_total) > 0 ? f.percent(String(Number(amount) / Number(data.uzum_total))) : "—");
  const catColumns: Column<Expenses["uzum"][number]>[] = [
    { key: "category", header: t("expenses.col.category"), render: (r) => label(r.category) },
    { key: "amount", header: t("expenses.col.amount"), numeric: true, render: (r) => f.money(r.amount, { unit: false }) },
    { key: "share", header: t("expenses.col.share"), numeric: true, render: (r) => share(r.amount) },
  ];
  const fineColumns: Column<UzumExpenseItem>[] = [
    { key: "day", header: t("home.drill.day"), render: (r) => f.date(r.day) },
    { key: "name", header: t("home.drill.name"), render: (r) => r.name ?? r.raw_code ?? r.code ?? "—" },
    { key: "amount", header: t("expenses.col.amount"), numeric: true, render: (r) => f.money(r.amount, { unit: false }) },
  ];
  const rows = list.data?.items ?? [];
  const listColumns: Column<UzumExpenseItem>[] = [
    // ADR-039: buyurtmaga bog'liq reklama P&L'da buyurtma kuniga yoziladi — ikkala sana.
    { key: "day", header: t("home.drill.day"), render: (r) => (r.order_date ? `${f.date(r.day)} · ${t("home.drill.orderDate", { date: f.date(r.order_date) })}` : f.date(r.day)) },
    { key: "category", header: t("expenses.col.category"), render: (r) => label(r.category) },
    {
      key: "name",
      header: t("home.drill.name"),
      render: (r) => (
        <>
          {r.name ?? r.raw_code ?? r.code ?? "—"}
          {!r.in_pnl && (
            <>
              {" "}
              <Badge tone="warning">{t("expenses.uzum.notInPnl")}</Badge>
            </>
          )}
        </>
      ),
    },
    { key: "amount", header: t("expenses.col.amount"), numeric: true, render: (r) => f.money(r.amount, { unit: false }) },
  ];
  const help = <FormulaPopover metric={t("terms.uzumExpenses")} code={t("home.formula.uzumExpenses.code")} formula={t("home.formula.uzumExpenses.formula")} source={t("home.formula.uzumExpenses.source")} />;
  return (
    <div className="expenses-uzum">
      <div className="orders-kpis">
        <Kpi label={t("terms.uzumExpenses")} value={f.money(data.uzum_total)} good="down" help={help} note={t("expenses.uzum.totalNote")} />
      </div>
      <StackedBarChart title={t("expenses.uzum.trend")} x={data.by_month.map((m) => m.month)} series={series} xKind="month" />
      <div className="orders-analysis__tables">
        <section aria-labelledby="expenses-cats">
          <h2 id="expenses-cats" className="h3">
            {t("expenses.uzum.byCategory")}
          </h2>
          <DataTable caption={t("expenses.uzum.byCategory")} density="compact" columns={catColumns} rows={ordered} rowKey={(r) => r.category} total={{ category: t("home.drill.total"), amount: f.money(data.uzum_total, { unit: false }) }} />
        </section>
        <section aria-labelledby="expenses-fines">
          <h2 id="expenses-fines" className="h3">
            {t("expenses.uzum.fines")}
          </h2>
          <DataTable caption={t("expenses.uzum.fines")} density="compact" columns={fineColumns} rows={data.fines} rowKey={(r) => r.id} empty={t("expenses.uzum.noFines")} />
        </section>
      </div>
      <section aria-labelledby="expenses-list" className="expenses-list">
        <h2 id="expenses-list" className="h3">
          {t("expenses.uzum.list")}
        </h2>
        <Select
          label={t("expenses.col.category")}
          value={category}
          onValueChange={(v) => {
            setCategory(v);
            goPage(undefined);
          }}
          options={[{ value: "", label: t("orders.group.all") }, ...keys.map((k) => ({ value: k, label: label(k) }))]}
        />
        <ExportButton orgId={orgId} table="expenses" query={{ start: params.start, end: params.end, shop: params.shops, category }} />
        {list.isError ? (
          <Banner tone="negative" title={errorText(list.error, t)} />
        ) : (
          <>
            <DataTable caption={t("expenses.uzum.list")} density="compact" columns={listColumns} rows={rows} rowKey={(r) => r.id} empty={t("home.drill.empty")} />
            {list.data && (
              <Pagination
                page={list.data.page}
                pages={list.data.pages}
                total={list.data.total}
                size={size}
                onPage={goPage}
                onSize={(n) => {
                  setSize(n);
                  goPage(undefined);
                }}
              />
            )}
          </>
        )}
      </section>
    </div>
  );
}
