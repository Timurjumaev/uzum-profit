// Uzumga jo'natish (TM6, ADR-061 §7, 04 §7.4 (5)): do'kon tanlanadi → Omborimdagi shu do'kon SKU'lari to'liq soni bilan
// (sonni kamaytirish va qatorni olib tashlash mumkin) → "Excel yuklab olish" (Uzum kabineti shablonida). Saqlangan zahoti
// donalar "Jo'natilmoqda" — Omborimdan band. Postavka Open API'da ko'ringanda o'zi bog'lanadi ("Uzumda"); bir nechta nomzod
// bo'lsa sotuvchi tanlaydi. Bekor — donalar Omborimga qaytadi. Shtrix-kodi yo'q SKU Excel'ga kirmaydi.
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { cancelDispatch, createDispatch, currentOrg, dispatchDraftQuery, dispatchesQuery, dispatchExcelUrl, linkDispatch, meQuery, shopsQuery } from "../../app/query";
import { Badge, Banner, Button, EmptyState, NumberInput, Select, Skeleton, useToast } from "../../components/ui";
import { fileName } from "../../components/ui/ExportButton";
import type { Dispatch } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { MANAGE_ROLES } from "../purchases/Purchases";

/** Excel'ni yuklab olish (cookie bilan, ExportButton kabi). */
async function download(url: string, fallback: string) {
  const response = await fetch(new Request(new URL(url, globalThis.location.origin).href, { credentials: "include" }));
  if (!response.ok) throw new Error(String(response.status));
  const blob = await response.blob();
  const link = document.createElement("a");
  const href = URL.createObjectURL(blob);
  link.href = href;
  link.download = fileName(response.headers.get("Content-Disposition"), fallback);
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export function Dispatches() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const canManage = MANAGE_ROLES.includes(org.role);
  const shops = useQuery(shopsQuery(org.id));
  const [picked, setShop] = useState("");
  // Tanlanmagan bo'lsa — birinchi do'kon (holat effektsiz hosila).
  const shop = picked || shops.data?.[0]?.id || "";
  return (
    <section className="purchases dispatches">
      <Link to="/warehouse" className="purchase__back">
        ← {t("dispatch.back")}
      </Link>
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("dispatch.title")}</h1>
        </div>
        <Link to="/receiving" className="ui-btn ui-btn--secondary ui-btn--md">
          {t("receiving.link")}
        </Link>
      </header>
      <p className="caption">{t("dispatch.lead")}</p>
      {canManage && (
        <section className="purchase__block" aria-labelledby="dispatch-new-title">
          <h2 id="dispatch-new-title" className="h3">
            {t("dispatch.newTitle")}
          </h2>
          <Select label={t("dispatch.shop")} value={shop} onValueChange={setShop} options={(shops.data ?? []).map((s) => ({ value: s.id, label: s.alias || s.name }))} />
          {shop && <DraftForm key={shop} orgId={org.id} shopId={shop} />}
        </section>
      )}
      <DispatchList orgId={org.id} canManage={canManage} />
    </section>
  );
}

function DraftForm({ orgId, shopId }: { orgId: string; shopId: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const draft = useQuery(dispatchDraftQuery(orgId, shopId));
  const [qty, setQty] = useState<Record<string, string | null>>({});
  const [removed, setRemoved] = useState<string[]>([]);
  const rows = (draft.data?.rows ?? []).filter((r) => !removed.includes(r.sku_id));
  const valueOf = (id: string, max: number) => (qty[id] === undefined ? String(max) : qty[id]);
  const items = rows.map((r) => ({ sku_id: r.sku_id, qty: Number(valueOf(r.sku_id, r.qty)), max: r.qty }));
  const valid = items.length > 0 && items.every((x) => Number.isInteger(x.qty) && x.qty >= 1 && x.qty <= x.max);
  const save = useMutation({
    mutationFn: async () => {
      const out = await createDispatch(orgId, { shop_id: shopId, items: items.map(({ sku_id, qty: n }) => ({ sku_id, qty: n })) });
      try {
        await download(dispatchExcelUrl(orgId, out.id), "uzum-jonatma.xlsx");
      } catch {
        toast.show(t("ui.exportFailed"), "negative");
      }
      return out;
    },
    onSuccess: async () => {
      setQty({});
      setRemoved([]);
      toast.show(t("dispatch.saved"), "positive");
      await Promise.all([["inventory"], ["purchases"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
    },
  });
  if (draft.isError) return <Banner tone="negative" title={errorText(draft.error, t)} />;
  if (!draft.data) return <Skeleton label={t("common.loading")} lines={3} />;
  return (
    <div className="dispatch-draft">
      {draft.data.no_barcode.length > 0 && (
        <Banner tone="warning" title={t("dispatch.noBarcode", { count: draft.data.no_barcode.length })}>
          {draft.data.no_barcode.map((r) => r.title ?? r.product_title).join(", ")}
        </Banner>
      )}
      {draft.data.rows.length === 0 ? (
        <EmptyState title={t("dispatch.draftEmpty")} text={t("dispatch.draftEmptyText")} />
      ) : (
        <>
          <ul className="dispatch-draft__list" aria-label={t("dispatch.draftList")}>
            {rows.map((r) => {
              const name = r.title ?? r.product_title ?? "—";
              return (
                <li key={r.sku_id}>
                  <span className="purchase-cell">
                    <strong>{name}</strong>
                    <span className="caption">{[r.barcode, t("dispatch.inStock", { count: r.qty }), r.unit_cost !== null ? f.money(r.unit_cost) : null].filter(Boolean).join(" · ")}</span>
                  </span>
                  <NumberInput label={t("dispatch.qty")} aria-label={t("dispatch.qtyOf", { name })} value={valueOf(r.sku_id, r.qty)} onValueChange={(v) => setQty((x) => ({ ...x, [r.sku_id]: v }))} digits={0} />
                  <Button variant="ghost" onClick={() => setRemoved((x) => [...x, r.sku_id])} aria-label={`${t("dispatch.remove")}: ${name}`}>
                    {t("dispatch.remove")}
                  </Button>
                </li>
              );
            })}
          </ul>
          {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
          <div className="cargo-pool__footer">
            {removed.length > 0 && (
              <Button variant="ghost" onClick={() => setRemoved([])}>
                {t("dispatch.restore", { count: removed.length })}
              </Button>
            )}
            <Button variant="primary" disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>
              {t("dispatch.save", { count: items.reduce((a, x) => a + (Number.isFinite(x.qty) ? x.qty : 0), 0) })}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function DispatchList({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const list = useQuery(dispatchesQuery(orgId));
  const refresh = async (message: string) => {
    toast.show(message, "positive");
    await Promise.all([["inventory"], ["purchases"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
  };
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const cancel = useMutation({ mutationFn: (id: string) => cancelDispatch(orgId, id), onSuccess: () => refresh(t("dispatch.canceled")), onError: fail });
  const link = useMutation({ mutationFn: ({ id, invoice }: { id: string; invoice: string | null }) => linkDispatch(orgId, id, invoice), onSuccess: () => refresh(t("dispatch.linkedSaved")), onError: fail });
  const excel = useMutation({ mutationFn: (id: string) => download(dispatchExcelUrl(orgId, id), "uzum-jonatma.xlsx"), onError: () => toast.show(t("ui.exportFailed"), "negative") });
  const badge = (d: Dispatch) =>
    d.status === "linked" ? (
      <Badge tone="positive">{t("dispatch.status.linked", { number: d.invoice?.number ?? "—" })}</Badge>
    ) : d.status === "canceled" ? (
      <Badge tone="neutral">{t("dispatch.status.canceled")}</Badge>
    ) : (
      <Badge tone="info">{t("dispatch.status.sending")}</Badge>
    );
  return (
    <section className="purchase__block" aria-labelledby="dispatch-list-title">
      <h2 id="dispatch-list-title" className="h3">
        {t("dispatch.listTitle")}
      </h2>
      {list.isError ? (
        <Banner tone="negative" title={errorText(list.error, t)} />
      ) : !list.data ? (
        <Skeleton label={t("common.loading")} lines={3} />
      ) : list.data.items.length === 0 ? (
        <EmptyState title={t("dispatch.empty")} text={t("dispatch.emptyText")} />
      ) : (
        <ul className="dispatch-list" aria-label={t("dispatch.listTitle")}>
          {list.data.items.map((d) => (
            <li key={d.id} className="cargo-pool__card">
              <div className="purchase-cell">
                <span>
                  {badge(d)} <strong>{d.shop}</strong>
                </span>
                <span className="caption">{[f.date(d.exported_at.slice(0, 10)), t("dispatch.units", { count: d.units, skus: d.items.length }), d.note].filter(Boolean).join(" · ")}</span>
                <span className="caption">{d.items.map((x) => `${x.title ?? x.barcode ?? "—"} × ${f.number(x.qty)}`).join(", ")}</span>
              </div>
              <div className="dispatch-list__actions">
                {d.status !== "canceled" && (
                  <Button variant="secondary" loading={excel.isPending && excel.variables === d.id} onClick={() => excel.mutate(d.id)}>
                    {t("dispatch.excel")}
                  </Button>
                )}
                {canManage && d.status === "sending" && d.candidates.length > 1 && (
                  <Select
                    label={t("dispatch.pickInvoice")}
                    value=""
                    onValueChange={(invoice) => invoice && link.mutate({ id: d.id, invoice })}
                    options={[{ value: "", label: t("dispatch.pickInvoiceHint", { count: d.candidates.length }) }, ...d.candidates.map((c) => ({ value: c.id, label: `№ ${c.number ?? "—"}${c.created_on ? ` · ${f.date(c.created_on.slice(0, 10))}` : ""}` }))]}
                  />
                )}
                {canManage && d.status === "linked" && (
                  <Button variant="ghost" onClick={() => link.mutate({ id: d.id, invoice: null })}>
                    {t("dispatch.unlink")}
                  </Button>
                )}
                {canManage && d.status === "sending" && (
                  <Button variant="ghost" loading={cancel.isPending && cancel.variables === d.id} onClick={() => cancel.mutate(d.id)} aria-label={`${t("dispatch.cancel")}: ${d.shop ?? ""} ${f.date(d.exported_at.slice(0, 10))}`}>
                    {t("dispatch.cancel")}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
