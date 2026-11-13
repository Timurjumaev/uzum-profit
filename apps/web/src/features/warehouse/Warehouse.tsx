// Omborim (TM5, ADR-061 §7, 02 M10): SKU bo'yicha qoldiq sanalgan xaridlardan, tannarxdagi qiymat (summalar ruxsati
// bilan). Har qatorda: "Boshqa SKU'ga o'tkazish" (do'konlar orasida ham — dona birlik tannarxi bilan o'tadi; bekor qilish
// mumkin) va "Brak" (sanashdan keyin topilgan brak — hisobdan chiqadi, foyda hisobida "Brak zarari", F51). Hisob serverda.
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { cancelTransfer, createStockMove, currentOrg, meQuery, skuPickerQuery, transferToSku, warehouseQuery } from "../../app/query";
import { Banner, Button, Combobox, DataTable, Dialog, EmptyState, NumberInput, Select, Skeleton, TextInput, useToast, type Column } from "../../components/ui";
import type { WarehouseRow } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { pickerLabel } from "../purchases/model";
import { MANAGE_ROLES } from "../purchases/Purchases";

type Editing = { kind: "transfer"; row: WarehouseRow } | { kind: "defect"; row: WarehouseRow };

const rowName = (r: WarehouseRow, untitled: string) => r.title ?? r.product_title ?? untitled;

export function Warehouse() {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const query = useQuery(warehouseQuery(org.id));
  const canManage = MANAGE_ROLES.includes(org.role);
  const amounts = query.data?.amounts ?? true;
  const [editing, setEditing] = useState<Editing | null>(null);
  const refresh = async (message: string) => {
    setEditing(null);
    toast.show(message, "positive");
    await Promise.all([["inventory"], ["purchases"], ["pnl"], ["dashboard"], ["skus"], ["sku"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", org.id, ...k] })));
  };
  const cancel = useMutation({
    mutationFn: (lineId: string) => cancelTransfer(org.id, lineId),
    onSuccess: () => refresh(t("warehouse.transfer.cancelled")),
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const untitled = t("warehouse.untitled");
  const actions = (r: WarehouseRow) => (
    <>
      <Button variant="ghost" disabled={r.sources.length === 0} onClick={() => setEditing({ kind: "transfer", row: r })} aria-label={`${t("warehouse.transfer.open")}: ${rowName(r, untitled)}`}>
        {t("warehouse.transfer.open")}
      </Button>
      <Button variant="ghost" disabled={r.qty === 0 || r.item_id === null} onClick={() => setEditing({ kind: "defect", row: r })} aria-label={`${t("warehouse.defect.open")}: ${rowName(r, untitled)}`}>
        {t("warehouse.defect.open")}
      </Button>
    </>
  );
  const columns: Column<WarehouseRow>[] = [
    {
      key: "sku",
      header: t("warehouse.col.sku"),
      render: (r) => (
        <span className="purchase-cell">
          <span className="purchase-cell__title">{rowName(r, untitled)}</span>
          <span className="caption">{[r.shop ?? t("warehouse.noSku"), r.barcode].filter(Boolean).join(" · ")}</span>
          {r.transfers_in.map((x) => (
            <span key={x.line_id} className="caption warehouse__transfer">
              {t("warehouse.transfer.from", { count: x.qty, name: x.from_name ?? untitled })}{" "}
              {canManage && (
                <Button variant="ghost" loading={cancel.isPending && cancel.variables === x.line_id} onClick={() => cancel.mutate(x.line_id)} aria-label={t("warehouse.transfer.cancelOf", { name: rowName(r, untitled), count: x.qty })}>
                  {t("warehouse.transfer.cancel")}
                </Button>
              )}
            </span>
          ))}
          {canManage && <span className="warehouse__mobile-actions">{actions(r)}</span>}
        </span>
      ),
    },
    {
      key: "qty",
      header: t("warehouse.col.qty"),
      numeric: true,
      mobile: true,
      render: (r) => (
        <>
          {f.number(r.qty)}
          {r.reserved > 0 && <span className="caption"> {t("warehouse.reserved", { count: r.reserved })}</span>}
        </>
      ),
    },
    ...(amounts
      ? [
          { key: "unit", header: t("warehouse.col.unitCost"), numeric: true, render: (r: WarehouseRow) => (r.unit_cost === null ? "—" : f.money(r.unit_cost, { unit: false })) },
          { key: "value", header: t("warehouse.col.value"), numeric: true, mobile: true, render: (r: WarehouseRow) => (r.value === null ? "—" : f.money(r.value, { unit: false })) },
        ]
      : []),
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (r: WarehouseRow) => (
              <span className="expenses-actions">{actions(r)}</span>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="purchases warehouse">
      <Link to="/inventory" className="purchase__back">
        ← {t("warehouse.back")}
      </Link>
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("warehouse.title")}</h1>
        </div>
        {query.data && (
          <p className="caption">
            {t("warehouse.total", { count: query.data.total_qty })}
            {amounts && query.data.total_value !== null && ` · ${f.money(query.data.total_value)}`}
          </p>
        )}
      </header>
      <p className="caption">{t("warehouse.lead")}</p>
      {!amounts && <Banner tone="info" title={t("purchases.noAmounts")}>{t("purchases.noAmountsText")}</Banner>}
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      ) : !query.data ? (
        <Skeleton label={t("common.loading")} lines={6} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title={t("warehouse.empty")} text={t("warehouse.emptyText")} />
      ) : (
        <div className="purchases__panel">
          <DataTable caption={t("warehouse.title")} mobileList columns={columns} rows={query.data.items} rowKey={(r) => r.key} />
        </div>
      )}
      {editing?.kind === "transfer" && <TransferDialog orgId={org.id} row={editing.row} onClose={() => setEditing(null)} onSaved={() => void refresh(t("warehouse.transfer.saved"))} />}
      {editing?.kind === "defect" && <DefectDialog orgId={org.id} row={editing.row} onClose={() => setEditing(null)} onSaved={() => void refresh(t("warehouse.defect.saved"))} />}
    </section>
  );
}

function TransferDialog({ orgId, row, onClose, onSaved }: { orgId: string; row: WarehouseRow; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const picker = useQuery(skuPickerQuery(orgId));
  const [source, setSource] = useState(row.sources[0]?.line_id ?? "");
  const [target, setTarget] = useState<string | null>(null);
  const [qty, setQty] = useState<string | null>(null);
  const chosen = row.sources.find((s) => s.line_id === source);
  const options = useMemo(
    () =>
      (picker.data?.rows ?? [])
        .filter((r) => r.sku_id !== null && r.sku_id !== row.sku_id)
        .map((r) => ({ value: r.sku_id!, label: `${pickerLabel(r)}${r.title && r.title !== pickerLabel(r) ? ` · ${r.title}` : ""}`, hint: r.shop ?? undefined })),
    [picker.data, row.sku_id],
  );
  const n = Number(qty);
  const valid = chosen !== undefined && target !== null && qty !== null && Number.isInteger(n) && n >= 1 && n <= chosen.qty;
  const save = useMutation({ mutationFn: () => transferToSku(orgId, { source_line_id: source, to_sku_id: target!, qty: n }), onSuccess: onSaved });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("warehouse.transfer.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="transfer-form" disabled={!valid} loading={save.isPending}>
            {t("warehouse.transfer.save")}
          </Button>
        </>
      }
    >
      <form id="transfer-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <p className="caption">{t("warehouse.transfer.hint", { name: row.title ?? row.product_title ?? "" })}</p>
        <Select
          label={t("warehouse.transfer.source")}
          value={source}
          onValueChange={setSource}
          options={row.sources.map((s) => ({
            value: s.line_id,
            label: [s.purchase_title ?? t("purchases.untitled"), s.counted_on ? f.date(s.counted_on) : null, t("cargo.units", { count: s.qty }), s.unit_cost !== null ? f.money(s.unit_cost) : null].filter(Boolean).join(" · "),
          }))}
        />
        <Combobox label={t("warehouse.transfer.target")} placeholder={t("purchases.lines.pickItem")} options={options} value={target} onValueChange={setTarget} limit={200} />
        <NumberInput label={t("warehouse.transfer.qty")} help={chosen ? t("warehouse.transfer.max", { count: chosen.qty }) : undefined} value={qty} onValueChange={setQty} digits={0} />
      </form>
    </Dialog>
  );
}

function DefectDialog({ orgId, row, onClose, onSaved }: { orgId: string; row: WarehouseRow; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [qty, setQty] = useState<string | null>(null);
  const [day, setDay] = useState(todayTashkent());
  const [note, setNote] = useState("");
  const [source, setSource] = useState(row.sources[0]?.line_id ?? "");
  const n = Number(qty);
  const valid = qty !== null && Number.isInteger(n) && n >= 1 && n <= row.qty && day !== "";
  const save = useMutation({
    mutationFn: () =>
      createStockMove(orgId, {
        item_id: row.item_id!,
        kind: "writeoff",
        reason: "defect",
        qty: n,
        day,
        note: note.trim() || null,
        sku_id: row.sku_id,
        purchase_line_id: source || null,
      }),
    onSuccess: onSaved,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("warehouse.defect.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="defect-form" disabled={!valid} loading={save.isPending}>
            {t("warehouse.defect.save")}
          </Button>
        </>
      }
    >
      <form id="defect-form" className="purchase-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <p className="caption">{t("warehouse.defect.hint")}</p>
        <NumberInput label={t("warehouse.defect.qty")} help={t("warehouse.transfer.max", { count: row.qty })} value={qty} onValueChange={setQty} digits={0} />
        {row.sources.length > 1 && (
          <Select label={t("warehouse.transfer.source")} value={source} onValueChange={setSource} options={row.sources.map((s) => ({ value: s.line_id, label: [s.purchase_title ?? t("purchases.untitled"), t("cargo.units", { count: s.qty })].join(" · ") }))} />
        )}
        <TextInput label={t("warehouse.defect.day")} type="date" value={day} onValueChange={setDay} />
        <TextInput label={t("purchases.fields.note")} optional value={note} onValueChange={setNote} maxLength={500} />
      </form>
    </Dialog>
  );
}
