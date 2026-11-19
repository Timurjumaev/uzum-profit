// Uzumga jo'natish (TM6, ADR-061 §7, 04 §7.4 (5)): do'kon tanlanadi → Omborimdagi shu do'kon SKU'lari to'liq soni bilan
// (sonni kamaytirish va qatorni olib tashlash mumkin) → "Excel yuklab olish" (Uzum kabineti shablonida). Saqlangan zahoti
// donalar "Jo'natilmoqda" — Omborimdan band. Postavka Open API'da ko'ringanda o'zi bog'lanadi ("Uzumda"); bir nechta nomzod
// bo'lsa sotuvchi tanlaydi. Bekor — donalar Omborimga qaytadi. Shtrix-kodi yo'q SKU Excel'ga kirmaydi.
// TM9.7 (G11): Excel'dagi tannarx tahrirlanadi; taxminiy (F22) — belgi, noma'lum — kiritmasdan saqlanmaydi (0 ketmaydi).
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import {
  cancelDispatch,
  createDispatch,
  currentOrg,
  dispatchDraftQuery,
  dispatchesQuery,
  dispatchExcelUrl,
  dispatchInvoicesQuery,
  linkDispatch,
  meQuery,
  orphanInvoicesQuery,
  orphanNotMine,
  orphanSent,
  shopsQuery,
} from "../../app/query";
import { Badge, Banner, Button, EmptyState, MoneyInput, NumberInput, Select, Skeleton, useToast } from "../../components/ui";
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
      <Orphans orgId={org.id} canManage={canManage} />
      <DispatchList orgId={org.id} canManage={canManage} />
    </section>
  );
}

/** TM9.1 (a): dasturdan tashqari (kabinetda to'g'ridan-to'g'ri yaratilgan) postavkalar — bir bosishda "Omborimdan ketgan"
 * (postavka tarkibidan jo'natma) yoki "Omborimdan emas". */
function Orphans({ orgId, canManage }: { orgId: string; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const orphans = useQuery(orphanInvoicesQuery(orgId));
  const done = async (message: string) => {
    toast.show(message, "positive");
    await Promise.all([["inventory"], ["purchases"], ["dashboard"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
  };
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const sent = useMutation({ mutationFn: (id: string) => orphanSent(orgId, id), onSuccess: () => done(t("dispatch.orphans.sentSaved")), onError: fail });
  const notMine = useMutation({ mutationFn: (id: string) => orphanNotMine(orgId, id), onSuccess: () => done(t("dispatch.orphans.notMineSaved")), onError: fail });
  const items = orphans.data?.items ?? [];
  if (items.length === 0) return null;
  return (
    <section className="purchase__block" aria-labelledby="dispatch-orphans-title">
      <h2 id="dispatch-orphans-title" className="h3">
        {t("dispatch.orphans.title", { count: items.length })}
      </h2>
      <p className="caption">{t("dispatch.orphans.lead")}</p>
      <ul className="dispatch-list" aria-label={t("dispatch.orphans.title", { count: items.length })}>
        {items.map((o) => {
          const number = o.invoice.number ?? "—";
          return (
            <li key={o.invoice.id} className="cargo-pool__card">
              <div className="purchase-cell">
                <span>
                  <Badge tone={o.accepted_on ? "positive" : "info"}>{o.accepted_on ? t("dispatch.orphans.accepted", { date: f.date(o.accepted_on) }) : t("dispatch.orphans.open")}</Badge> <strong>№ {number}</strong> {o.shop}
                </span>
                <span className="caption">
                  {o.items.map((x) => t("dispatch.orphans.item", { name: x.title ?? "—", declared: f.number(x.declared), available: f.number(x.available) })).join(", ")}
                </span>
              </div>
              {canManage && (
                <div className="dispatch-list__actions">
                  <Button variant="primary" loading={sent.isPending && sent.variables === o.invoice.id} onClick={() => sent.mutate(o.invoice.id)} aria-label={`${t("dispatch.orphans.sent")}: № ${number}`}>
                    {t("dispatch.orphans.sent")}
                  </Button>
                  <Button variant="ghost" loading={notMine.isPending && notMine.variables === o.invoice.id} onClick={() => notMine.mutate(o.invoice.id)} aria-label={`${t("dispatch.orphans.notMine")}: № ${number}`}>
                    {t("dispatch.orphans.notMine")}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** TM9.1 (b): qo'lda tanlash — do'konning bog'lanmagan hamma postavkasi (bosilganda yuklanadi). */
function OtherInvoice({ orgId, dispatchId, onPick }: { orgId: string; dispatchId: string; onPick: (invoice: string) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [open, setOpen] = useState(false);
  const all = useQuery({ ...dispatchInvoicesQuery(orgId, dispatchId), enabled: open });
  if (!open)
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        {t("dispatch.otherInvoice")}
      </Button>
    );
  return (
    <Select
      label={t("dispatch.otherInvoice")}
      value=""
      onValueChange={(invoice) => invoice && onPick(invoice)}
      options={[
        { value: "", label: all.data ? t("dispatch.pickInvoiceHint", { count: all.data.length }) : t("common.loading") },
        ...(all.data ?? []).map((c) => ({ value: c.id, label: `№ ${c.number ?? "—"}${c.created_on ? ` · ${f.date(c.created_on.slice(0, 10))}` : ""}` })),
      ]}
    />
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
  const [cost, setCost] = useState<Record<string, string | null>>({});
  const rows = (draft.data?.rows ?? []).filter((r) => !removed.includes(r.sku_id));
  const valueOf = (id: string, max: number) => (qty[id] === undefined ? String(max) : qty[id]);
  const costOf = (id: string) => {
    const v = cost[id];
    return v === undefined || v === null || v === "" ? null : v;
  };
  // F54: "Tavsiya bo'yicha to'ldirish" — rejasi bor qatorlarga yuborish rejasi; reja 0 (Uzumda yetarli) — qoralamadan olib
  // tashlanadi ("qaytarish" bilan tiklanadi); rejasiz qatorlar o'zgarmaydi. Standart — to'liq son (ADR-061 §7).
  const planned = (draft.data?.rows ?? []).filter((r) => r.plan_qty !== null && r.plan_qty !== undefined);
  const applyPlan = () => {
    const nextQty: Record<string, string | null> = {};
    const drop: string[] = [];
    for (const r of planned) {
      if ((r.plan_qty ?? 0) > 0) nextQty[r.sku_id] = String(r.plan_qty);
      else drop.push(r.sku_id);
    }
    setQty((x) => ({ ...x, ...nextQty }));
    setRemoved((x) => [...new Set([...x, ...drop])]);
    toast.show(t("dispatch.planApplied", { count: Object.keys(nextQty).length, skipped: drop.length }), "positive");
  };
  const items = rows.map((r) => ({ sku_id: r.sku_id, qty: Number(valueOf(r.sku_id, r.qty)), max: r.qty, unit_cost: costOf(r.sku_id), unknown: r.unknown ?? false }));
  const costOk = (x: (typeof items)[number]) => (x.unit_cost === null ? !x.unknown : Number(x.unit_cost) > 0);
  const valid = items.length > 0 && items.every((x) => Number.isInteger(x.qty) && x.qty >= 1 && x.qty <= x.max && costOk(x));
  const save = useMutation({
    mutationFn: async () => {
      const out = await createDispatch(orgId, {
        shop_id: shopId,
        items: items.map(({ sku_id, qty: n, unit_cost }) => ({ sku_id, qty: n, ...(unit_cost !== null ? { unit_cost } : {}) })),
      });
      try {
        await download(dispatchExcelUrl(orgId, out.id), "uzum-jonatma.xlsx");
      } catch {
        toast.show(t("ui.exportFailed"), "negative");
      }
      return out;
    },
    onSuccess: async () => {
      setQty({});
      setCost({});
      setRemoved([]);
      toast.show(t("dispatch.saved"), "positive");
      await Promise.all([["inventory"], ["purchases"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })));
    },
  });
  if (draft.isError) return <Banner tone="negative" title={errorText(draft.error, t)} />;
  if (!draft.data) return <Skeleton label={t("common.loading")} lines={3} />;
  return (
    <div className="dispatch-draft">
      {draft.data.uncounted > 0 && (
        <Banner tone="info" title={t("dispatch.uncounted", { count: draft.data.uncounted })}>
          <Link to="/warehouse">{t("dispatch.uncountedLink")}</Link>
        </Banner>
      )}
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
                <li key={r.sku_id} className={r.unknown || r.unit_cost !== null ? "has-cost" : undefined}>
                  <span className="purchase-cell">
                    <strong>{name}</strong>
                    <span className="caption">
                      {[r.barcode, t("dispatch.inStock", { count: r.qty }), r.unit_cost !== null && !r.unknown ? `${r.estimated ? "~" : ""}${f.money(r.unit_cost)}` : null].filter(Boolean).join(" · ")}
                    </span>
                    {r.unknown ? <Badge tone="warning">{t("dispatch.costUnknown")}</Badge> : r.estimated && <Badge tone="warning">{t("dispatch.costEstimated")}</Badge>}
                  </span>
                  <NumberInput label={t("dispatch.qty")} aria-label={t("dispatch.qtyOf", { name })} value={valueOf(r.sku_id, r.qty)} onValueChange={(v) => setQty((x) => ({ ...x, [r.sku_id]: v }))} digits={0} />
                  {(r.unknown || r.unit_cost !== null) && (
                    <MoneyInput
                      label={t("dispatch.cost")}
                      aria-label={t("dispatch.costOf", { name })}
                      help={r.unknown ? t("dispatch.costRequired") : undefined}
                      optional={!r.unknown}
                      value={cost[r.sku_id] ?? null}
                      onValueChange={(v) => setCost((x) => ({ ...x, [r.sku_id]: v }))}
                    />
                  )}
                  <Button variant="ghost" onClick={() => setRemoved((x) => [...x, r.sku_id])} aria-label={`${t("dispatch.remove")}: ${name}`}>
                    {t("dispatch.remove")}
                  </Button>
                </li>
              );
            })}
          </ul>
          {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
          <div className="cargo-pool__footer">
            {planned.length > 0 && (
              <Button variant="secondary" onClick={applyPlan} title={t("dispatch.planHint")}>
                {t("dispatch.fillPlan")}
              </Button>
            )}
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
                {d.origin === "invoice" && <span className="caption">{t("dispatch.fromInvoice")}</span>}
                {d.adjustments.length > 0 && (
                  <span className="caption">
                    {t("dispatch.adjusted")}{" "}
                    {d.adjustments.map((a) => t("dispatch.adjustment", { name: a.title ?? "—", before: f.number(a.before), after: f.number(a.after), declared: f.number(a.declared) })).join("; ")}
                  </span>
                )}
              </div>
              <div className="dispatch-list__actions">
                {d.status !== "canceled" && (
                  <Button variant="secondary" loading={excel.isPending && excel.variables === d.id} onClick={() => excel.mutate(d.id)}>
                    {t("dispatch.excel")}
                  </Button>
                )}
                {canManage && d.status === "sending" && d.candidates.length > 0 && (
                  <Select
                    label={t("dispatch.pickInvoice")}
                    value=""
                    onValueChange={(invoice) => invoice && link.mutate({ id: d.id, invoice })}
                    options={[
                      { value: "", label: t("dispatch.pickInvoiceHint", { count: d.candidates.length }) },
                      ...d.candidates.map((c) => ({
                        value: c.id,
                        label: [
                          `№ ${c.number ?? "—"}`,
                          c.created_on ? f.date(c.created_on.slice(0, 10)) : null,
                          c.common !== null && c.union !== null && c.common !== c.union ? t("dispatch.partial", { common: c.common, union: c.union }) : null,
                        ]
                          .filter(Boolean)
                          .join(" · "),
                      })),
                    ]}
                  />
                )}
                {canManage && d.status === "sending" && <OtherInvoice orgId={orgId} dispatchId={d.id} onPick={(invoice) => link.mutate({ id: d.id, invoice })} />}
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
