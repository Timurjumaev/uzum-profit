// Uzum to'lov jadvali (F38): har do'kon uchun sana bo'yicha (`valid_from`). Jadval turi — kunlik, haftalik, 2 haftalik,
// oylik; oy kunlari va yechish foizi serverdan (ma'lumotnoma). To'lov prognozi (Pul oqimi) shundan foydalanadi (B5).
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { createPayoutSchedule, deletePayoutSchedule, shopsQuery } from "../../app/query";
import { Button, DataTable, Dialog, EmptyState, Select, TextInput, type Column } from "../../components/ui";
import type { PayoutSchedule, ScheduleKind, Settings } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { Confirm } from "./Confirm";
import { PAYOUT_KINDS, termsDays } from "./model";
import { useSettingsMutation } from "./useSettingsMutation";

export function Payouts({ orgId, data, canManage }: { orgId: string; data: Settings; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shops = useQuery(shopsQuery(orgId));
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<PayoutSchedule | null>(null);
  const remove = useSettingsMutation(orgId, (id: string) => deletePayoutSchedule(orgId, id), "settings.payout.deleted", () => setRemoving(null));
  const shopName = (id: string) => {
    const s = shops.data?.find((x) => x.id === id);
    return s ? (s.alias ?? s.name) : id.slice(0, 8);
  };
  const terms = (kind: ScheduleKind) => {
    const x = data.payout_terms.find((p) => p.kind === kind);
    if (!x) return "—";
    return t(x.days_of_month ? "settings.payout.terms" : "settings.payout.termsDaily", { days: termsDays(x.days_of_month), fee: f.percent(String(Number(x.fee_pct) / 100)) });
  };
  const columns: Column<PayoutSchedule>[] = [
    { key: "shop", header: t("settings.payout.col.shop"), render: (p) => shopName(p.shop_id) },
    { key: "kind", header: t("settings.payout.col.kind"), render: (p) => t(`settings.payout.kind.${p.kind}`) },
    { key: "terms", header: t("settings.payout.col.terms"), render: (p) => terms(p.kind) },
    { key: "from", header: t("settings.payout.col.from"), render: (p) => f.date(p.valid_from) },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("settings.col.actions"),
            render: (p: PayoutSchedule) => (
              <Button size="sm" variant="ghost" onClick={() => setRemoving(p)}>
                {t("settings.delete")}
              </Button>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="settings-section" aria-labelledby="settings-payout">
      <header className="settings-section__head">
        <h2 id="settings-payout" className="h3">
          {t("settings.payout.title")}
        </h2>
        {canManage && <Button onClick={() => setAdding(true)}>{t("settings.payout.add")}</Button>}
      </header>
      <p className="caption">{t("settings.payout.lead")}</p>
      {data.payout_schedules.length === 0 ? (
        <EmptyState title={t("settings.payout.empty")} text={t("settings.payout.emptyText")} />
      ) : (
        <DataTable caption={t("settings.payout.title")} columns={columns} rows={data.payout_schedules} rowKey={(p) => p.id} />
      )}
      {adding && <PayoutForm orgId={orgId} data={data} onClose={() => setAdding(false)} />}
      {removing && (
        <Confirm title={t("settings.payout.deleteTitle")} action={t("settings.delete")} loading={remove.isPending} onConfirm={() => remove.mutate(removing.id)} onClose={() => setRemoving(null)}>
          {t("settings.payout.deleteText", { shop: shopName(removing.shop_id), date: f.date(removing.valid_from) })}
        </Confirm>
      )}
    </section>
  );
}

function PayoutForm({ orgId, data, onClose }: { orgId: string; data: Settings; onClose: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shops = useQuery(shopsQuery(orgId));
  const [shop, setShop] = useState("");
  const [kind, setKind] = useState<ScheduleKind>("weekly");
  const [from, setFrom] = useState(todayTashkent());
  const shopId = shop || shops.data?.[0]?.id || "";
  const save = useSettingsMutation(orgId, () => createPayoutSchedule(orgId, { shop_id: shopId, kind, valid_from: from }), "settings.payout.saved", onClose);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (shopId && from) save.mutate(undefined);
  };
  const term = data.payout_terms.find((p) => p.kind === kind);
  return (
    <Dialog
      open
      title={t("settings.payout.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("settings.cancel")}
          </Button>
          <Button type="submit" form="payout-form" disabled={!shopId || !from} loading={save.isPending}>
            {t("settings.save")}
          </Button>
        </>
      }
    >
      <form id="payout-form" className="settings-form" onSubmit={submit}>
        <Select label={t("settings.payout.col.shop")} value={shopId} onValueChange={setShop} options={(shops.data ?? []).map((s) => ({ value: s.id, label: s.alias ?? s.name }))} />
        <Select
          label={t("settings.payout.col.kind")}
          value={kind}
          onValueChange={(v) => setKind(v as ScheduleKind)}
          options={PAYOUT_KINDS.map((k) => ({ value: k, label: t(`settings.payout.kind.${k}`) }))}
          help={term ? t(term.days_of_month ? "settings.payout.terms" : "settings.payout.termsDaily", { days: termsDays(term.days_of_month), fee: f.percent(String(Number(term.fee_pct) / 100)) }) : undefined}
        />
        <TextInput label={t("settings.payout.col.from")} help={t("settings.payout.fromHelp")} type="date" required value={from} onValueChange={setFrom} />
      </form>
    </Dialog>
  );
}
