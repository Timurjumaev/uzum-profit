// Uzum bonuslari (ADR-031) P&L sahifasida: davrga tushgan bonus davrlari (ma'lumot banneri — haqiqiy foyda
// o'zgarmaydi), tizim takliflari ("Uzum logistikani olmagan ko'rinadi — bonusmi?": belgilash yoki rad etish) va
// qo'shish shakli. To'liq ro'yxat va tahrirlash — Sozlamalar (B4.8). O'zgartirish — egasi va menejer
// (`manage_settings`); boshqalar faqat ko'radi.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createWaiver, deleteWaiver, feeWaiversQuery, shopsQuery } from "../../app/query";
import { Banner, Button, Dialog, Select, TextInput, useToast } from "../../components/ui";
import type { Pnl, WaiverIn, WaiverSuggestion } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Draft = { shop: string; start: string; end: string; kinds: string[]; reason: string; source: WaiverIn["source"] };

const ALL = "";

/** Bepul xarajat turi nomi: sotuv logistikasi — o'z matni, qolganlari — Uzum xarajat toifalari (bosh sahifadagi). */
export function useKindLabel() {
  const { t } = useTranslation();
  return (kind: string) => (kind === "sale_logistics" ? t("pnl.waivers.kind.sale_logistics") : t(`home.expense.${kind}`, { defaultValue: kind }));
}

function useShopName(orgId: string) {
  const { t } = useTranslation();
  const shops = useQuery(shopsQuery(orgId));
  return (id: string | null) => {
    if (id === null) return t("pnl.waivers.allShops");
    const shop = shops.data?.find((s) => s.id === id);
    return shop ? (shop.alias ?? shop.name) : id.slice(0, 8);
  };
}

/** Bonus o'zgarsa — hisobotlar (banner, grafik, belgi) va ro'yxat qayta so'raladi. */
function useRefresh(orgId: string) {
  const client = useQueryClient();
  return () =>
    Promise.all(
      ["pnl", "dashboard", "drill", "fee-waivers"].map((key) => client.invalidateQueries({ queryKey: ["orgs", orgId, key] })),
    );
}

type Props = { orgId: string; data: Pnl; canManage: boolean };

export function Waivers({ orgId, data, canManage }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const kindLabel = useKindLabel();
  const shopName = useShopName(orgId);
  const refresh = useRefresh(orgId);
  const [draft, setDraft] = useState<Draft | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) => deleteWaiver(orgId, id),
    onSuccess: async () => {
      await refresh();
      toast.show(t("pnl.waivers.deleted"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const dismiss = useMutation({
    mutationFn: (s: WaiverSuggestion) =>
      createWaiver(orgId, { shop_id: s.shop_id, start_on: s.start_on, end_on: s.end_on, kinds: s.kinds, reason: "", source: "detected", dismissed: true }),
    onSuccess: async () => {
      await refresh();
      toast.show(t("pnl.waivers.dismissed"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });

  const empty = (): Draft => ({ shop: ALL, start: data.meta.period.start, end: data.meta.period.end, kinds: ["sale_logistics"], reason: "", source: "manual" });
  const fromSuggestion = (s: WaiverSuggestion): Draft => ({ shop: s.shop_id, start: s.start_on, end: s.end_on, kinds: s.kinds, reason: "", source: "detected" });

  if (data.waivers.length === 0 && data.waiver_suggestions.length === 0 && !canManage) return null;
  return (
    <section className="pnl-waivers" aria-label={t("pnl.waivers.formTitle")}>
      {data.waivers.map((w) => (
        <Banner
          key={w.id}
          tone="info"
          title={t("pnl.waivers.title", { reason: w.reason || t("pnl.waivers.noReason") })}
          action={
            canManage ? (
              <Button variant="secondary" loading={remove.isPending && remove.variables === w.id} onClick={() => remove.mutate(w.id)}>
                {t("pnl.waivers.delete")}
              </Button>
            ) : undefined
          }
        >
          {t("pnl.waivers.text", { period: f.period(w.start_on, w.end_on), shop: shopName(w.shop_id), kinds: w.kinds.map(kindLabel).join(", ") })}
        </Banner>
      ))}
      {data.waiver_suggestions.map((s) => (
        <Banner
          key={`${s.shop_id}-${s.start_on}`}
          tone="warning"
          title={t("pnl.waivers.suggestionTitle")}
          action={
            canManage ? (
              <span className="pnl-waivers__actions">
                <Button variant="secondary" onClick={() => setDraft(fromSuggestion(s))}>
                  {t("pnl.waivers.confirm")}
                </Button>
                <Button variant="ghost" loading={dismiss.isPending && dismiss.variables === s} onClick={() => dismiss.mutate(s)}>
                  {t("pnl.waivers.dismiss")}
                </Button>
              </span>
            ) : undefined
          }
        >
          {t("pnl.waivers.suggestionText", { shop: shopName(s.shop_id), period: f.period(s.start_on, s.end_on) })}
        </Banner>
      ))}
      {canManage && (
        <Button variant="ghost" className="pnl-waivers__add" onClick={() => setDraft(empty())}>
          {t("pnl.waivers.add")}
        </Button>
      )}
      {draft && <WaiverForm orgId={orgId} initial={draft} onClose={() => setDraft(null)} />}
    </section>
  );
}

function WaiverForm({ orgId, initial, onClose }: { orgId: string; initial: Draft; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const kindLabel = useKindLabel();
  const shops = useQuery(shopsQuery(orgId));
  const kinds = useQuery(feeWaiversQuery(orgId));
  const refresh = useRefresh(orgId);
  const [draft, setDraft] = useState(initial);
  const patch = (p: Partial<Draft>) => setDraft((d) => ({ ...d, ...p }));
  const save = useMutation({
    mutationFn: () =>
      createWaiver(orgId, {
        shop_id: draft.shop === ALL ? null : draft.shop,
        start_on: draft.start,
        end_on: draft.end,
        kinds: draft.kinds,
        reason: draft.reason,
        source: draft.source,
        dismissed: false,
      }),
    onSuccess: async () => {
      await refresh();
      toast.show(t("pnl.waivers.saved"), "positive");
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  const toggle = (kind: string, on: boolean) => patch({ kinds: on ? [...draft.kinds, kind] : draft.kinds.filter((k) => k !== kind) });
  const shopOptions = [{ value: ALL, label: t("pnl.waivers.allShops") }, ...(shops.data ?? []).map((s) => ({ value: s.id, label: s.alias ?? s.name }))];
  return (
    <Dialog
      open
      title={t("pnl.waivers.formTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("pnl.waivers.cancel")}
          </Button>
          <Button type="submit" form="pnl-waiver-form" loading={save.isPending}>
            {t("pnl.waivers.save")}
          </Button>
        </>
      }
    >
      <form id="pnl-waiver-form" className="pnl-waiver-form" onSubmit={submit}>
        <p className="caption">{t("pnl.waivers.formLead")}</p>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <Select label={t("pnl.waivers.shop")} options={shopOptions} value={draft.shop} onValueChange={(shop) => patch({ shop })} />
        <div className="pnl-waiver-form__dates">
          <TextInput label={t("pnl.waivers.start")} type="date" required value={draft.start} onValueChange={(start) => patch({ start })} />
          <TextInput label={t("pnl.waivers.end")} type="date" required value={draft.end} onValueChange={(end) => patch({ end })} />
        </div>
        <fieldset className="pnl-waiver-form__kinds">
          <legend className="ui-field__label">{t("pnl.waivers.kinds")}</legend>
          {(kinds.data?.kinds ?? ["sale_logistics"]).map((kind) => (
            <label key={kind}>
              <input type="checkbox" checked={draft.kinds.includes(kind)} onChange={(e) => toggle(kind, e.target.checked)} /> {kindLabel(kind)}
            </label>
          ))}
        </fieldset>
        <TextInput
          label={t("pnl.waivers.reason")}
          help={t("pnl.waivers.reasonHelp")}
          optional
          maxLength={300}
          value={draft.reason}
          onValueChange={(reason) => patch({ reason })}
        />
      </form>
    </Dialog>
  );
}
