// O'z xarajatlarim (M8, F10): summa [boshlanish; tugash] kunlariga teng taqsimlanadi — bir martalik (bir kun),
// amortizatsiya (davr, masalan printer 12 oyga) yoki takroriy (har oy shu kuni, N oy). Qo'shish, tahrirlash va
// o'chirish — egasi va menejer (`manage_settings`); buxgalter ko'radi. P&L bu xarajatlarni darhol hisobga oladi.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createOwnExpense, deleteOwnExpense, ownCategoriesQuery, shopsQuery, updateOwnExpense } from "../../app/query";
import { Badge, Banner, Button, DataTable, Dialog, EmptyState, FormulaPopover, Kpi, MoneyInput, NumberInput, Select, TextInput, useToast, type Column } from "../../components/ui";
import type { Expenses, OwnExpenseItem } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Mode = "once" | "period" | "monthly";
type Draft = { category: string; newCategory: string; amount: string | null; mode: Mode; start: string; end: string; months: string | null; shop: string; note: string };

const NEW = "__new";
const ORG = "";

function useRefresh(orgId: string) {
  const client = useQueryClient();
  return () => Promise.all(["expenses", "pnl", "dashboard", "skus", "sku"].map((key) => client.invalidateQueries({ queryKey: ["orgs", orgId, key] })));
}

function draftOf(row: OwnExpenseItem | null): Draft {
  if (!row) return { category: "", newCategory: "", amount: null, mode: "once", start: "", end: "", months: "3", shop: ORG, note: "" };
  return {
    category: row.category,
    newCategory: "",
    amount: row.amount,
    mode: row.start_on === row.end_on ? "once" : "period",
    start: row.start_on,
    end: row.end_on,
    months: "3",
    shop: row.shop_id ?? ORG,
    note: row.note ?? "",
  };
}

type Props = { orgId: string; data: Expenses; canManage: boolean };

export function OwnExpenses({ orgId, data, canManage }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const refresh = useRefresh(orgId);
  const shops = useQuery(shopsQuery(orgId));
  const [editing, setEditing] = useState<OwnExpenseItem | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => deleteOwnExpense(orgId, id),
    onSuccess: async () => {
      await refresh();
      toast.show(t("expenses.own.deleted"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const scope = (r: OwnExpenseItem) => {
    if (r.scope === "org") return t("expenses.own.scope.org");
    if (r.scope === "item") return t("expenses.own.scope.item");
    const shop = shops.data?.find((s) => s.id === r.shop_id);
    return shop ? (shop.alias ?? shop.name) : t("expenses.own.scope.shop");
  };
  const columns: Column<OwnExpenseItem>[] = [
    { key: "period", header: t("home.drill.period"), render: (r) => f.period(r.start_on, r.end_on) },
    {
      key: "category",
      header: t("expenses.col.category"),
      render: (r) => (
        <>
          {r.category}
          {r.recurrence === "monthly" && (
            <>
              {" "}
              <Badge tone="info">{t("expenses.own.monthly")}</Badge>
            </>
          )}
        </>
      ),
    },
    { key: "scope", header: t("expenses.own.scopeCol"), render: scope },
    { key: "note", header: t("home.drill.note"), render: (r) => r.note ?? "—" },
    { key: "amount", header: t("expenses.own.fullAmount"), numeric: true, render: (r) => f.money(r.amount, { unit: false }) },
    { key: "in_period", header: t("home.drill.amountInPeriod"), numeric: true, render: (r) => f.money(r.in_period, { unit: false }) },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (r: OwnExpenseItem) => (
              <span className="expenses-actions">
                <Button variant="ghost" onClick={() => setEditing(r)} aria-label={`${t("expenses.own.edit")}: ${r.category} ${f.period(r.start_on, r.end_on)}`}>
                  {t("expenses.own.edit")}
                </Button>
                <Button variant="ghost" loading={remove.isPending && remove.variables === r.id} onClick={() => remove.mutate(r.id)} aria-label={`${t("expenses.own.delete")}: ${r.category} ${f.period(r.start_on, r.end_on)}`}>
                  {t("expenses.own.delete")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];
  const help = <FormulaPopover metric={t("terms.ownExpenses")} code={t("home.formula.ownExpenses.code")} formula={t("home.formula.ownExpenses.formula")} source={t("home.formula.ownExpenses.source")} />;
  return (
    <div className="expenses-own">
      <div className="orders-kpis">
        <Kpi label={t("terms.ownExpenses")} value={f.money(data.own_total)} good="down" help={help} note={t("expenses.own.totalNote")} />
      </div>
      {canManage && (
        <div>
          <Button onClick={() => setEditing("new")}>{t("expenses.own.add")}</Button>
        </div>
      )}
      {data.own_items.length === 0 ? (
        <EmptyState title={t("expenses.own.empty")} text={t("expenses.own.emptyText")} />
      ) : (
        <>
          <DataTable
            caption={t("expenses.own.byCategory")}
            density="compact"
            columns={[
              { key: "category", header: t("expenses.col.category"), render: (r: Expenses["own"][number]) => r.category },
              { key: "amount", header: t("home.drill.amountInPeriod"), numeric: true, render: (r: Expenses["own"][number]) => f.money(r.amount, { unit: false }) },
            ]}
            rows={data.own}
            rowKey={(r) => r.category}
          />
          <DataTable caption={t("expenses.own.list")} density="compact" columns={columns} rows={data.own_items} rowKey={(r) => r.id} />
        </>
      )}
      {editing && <OwnForm orgId={orgId} row={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function OwnForm({ orgId, row, onClose }: { orgId: string; row: OwnExpenseItem | null; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const refresh = useRefresh(orgId);
  const categories = useQuery(ownCategoriesQuery(orgId));
  const shops = useQuery(shopsQuery(orgId));
  const [draft, setDraft] = useState(() => draftOf(row));
  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }));
  const editing = row !== null;
  const category = (draft.category === NEW ? draft.newCategory : draft.category).trim();
  const end = draft.mode === "period" ? draft.end : draft.mode === "once" ? draft.start : draft.start;
  const valid = category !== "" && draft.amount !== null && Number(draft.amount) > 0 && draft.start !== "" && end >= draft.start && (draft.mode !== "monthly" || Number(draft.months) >= 2);
  const save = useMutation({
    mutationFn: async () => {
      const shop_id = draft.shop === ORG ? null : draft.shop;
      const note = draft.note.trim() === "" ? null : draft.note.trim();
      if (row) {
        await updateOwnExpense(orgId, row.id, { category, amount: draft.amount!, start_on: draft.start, end_on: end, shop_id, note });
        return;
      }
      await createOwnExpense(orgId, {
        category,
        amount: draft.amount!,
        start_on: draft.start,
        end_on: draft.mode === "period" ? end : null,
        shop_id,
        note,
        repeat_months: draft.mode === "monthly" ? Number(draft.months) : 1,
      });
    },
    onSuccess: async () => {
      await refresh();
      toast.show(t("expenses.own.saved"), "positive");
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const options = [...(categories.data?.items ?? []), ...(row && !(categories.data?.items ?? []).includes(row.category) ? [row.category] : [])];
  const modes: Mode[] = editing ? ["once", "period"] : ["once", "period", "monthly"];
  return (
    <Dialog
      open
      title={editing ? t("expenses.own.editTitle") : t("expenses.own.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("products.link.cancel")}
          </Button>
          <Button type="submit" form="own-expense-form" disabled={!valid} loading={save.isPending}>
            {t("products.link.save")}
          </Button>
        </>
      }
    >
      <form id="own-expense-form" className="expenses-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <Select
          label={t("expenses.col.category")}
          value={draft.category}
          onValueChange={(category) => patch({ category })}
          options={[{ value: "", label: t("expenses.own.pickCategory"), disabled: true }, ...options.map((c) => ({ value: c, label: c })), { value: NEW, label: t("expenses.own.newCategory") }]}
        />
        {draft.category === NEW && <TextInput label={t("expenses.own.newCategoryName")} value={draft.newCategory} onValueChange={(newCategory) => patch({ newCategory })} maxLength={60} />}
        <MoneyInput label={t("expenses.own.amountLabel", { mode: t(`expenses.own.mode.${draft.mode}.short`) })} value={draft.amount} onValueChange={(amount) => patch({ amount })} />
        <fieldset className="expenses-form__modes">
          <legend className="ui-field__label">{t("expenses.own.kind")}</legend>
          {modes.map((m) => (
            <label key={m}>
              <input type="radio" name="own-mode" checked={draft.mode === m} onChange={() => patch({ mode: m })} /> {t(`expenses.own.mode.${m}.label`)}
            </label>
          ))}
        </fieldset>
        <p className="caption">{t(`expenses.own.mode.${draft.mode}.hint`)}</p>
        <div className="expenses-form__dates">
          <TextInput label={draft.mode === "monthly" ? t("expenses.own.firstDay") : draft.mode === "period" ? t("expenses.own.start") : t("expenses.own.day")} type="date" required value={draft.start} onValueChange={(start) => patch({ start })} />
          {draft.mode === "period" && <TextInput label={t("expenses.own.end")} type="date" required value={draft.end} onValueChange={(end) => patch({ end })} />}
          {draft.mode === "monthly" && <NumberInput label={t("expenses.own.months")} value={draft.months} onValueChange={(months) => patch({ months })} digits={0} />}
        </div>
        <Select
          label={t("expenses.own.scopeCol")}
          value={draft.shop}
          onValueChange={(shop) => patch({ shop })}
          options={[{ value: ORG, label: t("expenses.own.scope.org") }, ...(shops.data ?? []).map((s) => ({ value: s.id, label: s.alias ?? s.name }))]}
        />
        <TextInput label={t("home.drill.note")} optional value={draft.note} onValueChange={(note) => patch({ note })} maxLength={300} />
      </form>
    </Dialog>
  );
}
