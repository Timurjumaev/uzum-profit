// Uzum to'lov jadvali (F38): butun akkauntga bitta (Temur, 2026-11-16), sana bo'yicha (`valid_from`). Jadval turi — kunlik, haftalik, 2 haftalik,
// oylik; oy kunlari va yechish foizi serverdan (ma'lumotnoma). To'lov prognozi (Pul oqimi) shundan foydalanadi (B5).
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { createPayoutSchedule, deletePayoutSchedule } from "../../app/query";
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
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<PayoutSchedule | null>(null);
  const remove = useSettingsMutation(orgId, (id: string) => deletePayoutSchedule(orgId, id), "settings.payout.deleted", () => setRemoving(null));
  const terms = (kind: ScheduleKind) => {
    const x = data.payout_terms.find((p) => p.kind === kind);
    if (!x) return "—";
    return t(x.days_of_month ? "settings.payout.terms" : "settings.payout.termsDaily", { days: termsDays(x.days_of_month), fee: f.percent(String(Number(x.fee_pct) / 100)) });
  };
  const columns: Column<PayoutSchedule>[] = [
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
      <p className="caption">{t("settings.payout.rules", { lag: data.payout_rules.lag_days, fee: f.percent(String(Number(data.payout_rules.urgent_fee_pct) / 100)) })}</p>
      {data.payout_schedules.length === 0 ? (
        <EmptyState title={t("settings.payout.empty")} text={t("settings.payout.emptyText")} />
      ) : (
        <DataTable caption={t("settings.payout.title")} columns={columns} rows={data.payout_schedules} rowKey={(p) => p.id} />
      )}
      {adding && <PayoutForm orgId={orgId} data={data} onClose={() => setAdding(false)} />}
      {removing && (
        <Confirm title={t("settings.payout.deleteTitle")} action={t("settings.delete")} loading={remove.isPending} onConfirm={() => remove.mutate(removing.id)} onClose={() => setRemoving(null)}>
          {t("settings.payout.deleteText", { date: f.date(removing.valid_from) })}
        </Confirm>
      )}
    </section>
  );
}

function PayoutForm({ orgId, data, onClose }: { orgId: string; data: Settings; onClose: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [kind, setKind] = useState<ScheduleKind>("weekly");
  const [from, setFrom] = useState(todayTashkent());
  const save = useSettingsMutation(orgId, () => createPayoutSchedule(orgId, { kind, valid_from: from }), "settings.payout.saved", onClose);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (from) save.mutate(undefined);
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
          <Button type="submit" form="payout-form" disabled={!from} loading={save.isPending}>
            {t("settings.save")}
          </Button>
        </>
      }
    >
      <form id="payout-form" className="settings-form" onSubmit={submit}>
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
