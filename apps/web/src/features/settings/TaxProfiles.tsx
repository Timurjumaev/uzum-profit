// Soliq profili (F11): sana bo'yicha (`valid_from`) — eski davr hisobi o'zgarmaydi, yangi qator keyingi sanalarga amal
// qiladi. Rejimlar: aylanmadan foiz (baza — tushum yoki Uzum to'lovi), Uzum soliq agenti, QQS + foyda solig'i, yo'q.
// Ma'lumotnoma stavkasi tavsiya sifatida ko'rsatiladi — buxgalter tasdiqlaydi.
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { createTaxProfile, deleteTaxProfile, updateTaxProfile } from "../../app/query";
import { Badge, Button, DataTable, Dialog, EmptyState, NumberInput, Select, TextInput, type Column } from "../../components/ui";
import type { Settings, TaxProfile } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { Confirm } from "./Confirm";
import { activeTax, BASES, REGIMES, taxBody, taxDraft, taxValid, type TaxDraft } from "./model";
import { useSettingsMutation } from "./useSettingsMutation";

type Editing = { profile: TaxProfile | null };

export function TaxProfiles({ orgId, data, canManage }: { orgId: string; data: Settings; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [editing, setEditing] = useState<Editing | null>(null);
  const [removing, setRemoving] = useState<TaxProfile | null>(null);
  const today = todayTashkent();
  const current = activeTax(data.tax_profiles, today);
  const remove = useSettingsMutation(orgId, (id: string) => deleteTaxProfile(orgId, id), "settings.tax.deleted", () => setRemoving(null));
  const detail = (p: TaxProfile) =>
    p.regime === "turnover"
      ? t("settings.tax.detailTurnover", { rate: f.percent(String(Number(p.rate_pct) / 100)), base: t(`settings.tax.base.${p.base}`) })
      : p.regime === "vat_profit"
        ? t("settings.tax.detailVat", { vat: f.percent(String(Number(p.vat_pct) / 100)), profit: f.percent(String(Number(p.profit_pct) / 100)) })
        : "—";
  const columns: Column<TaxProfile>[] = [
    { key: "from", header: t("settings.tax.col.from"), render: (p) => f.date(p.valid_from) },
    {
      key: "regime",
      header: t("settings.tax.col.regime"),
      render: (p) => (
        <>
          {t(`settings.tax.regime.${p.regime}`)} {p.id === current?.id && <Badge tone="positive">{t("settings.tax.current")}</Badge>}
        </>
      ),
    },
    { key: "detail", header: t("settings.tax.col.detail"), render: detail },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("settings.col.actions"),
            render: (p: TaxProfile) => (
              <span className="settings-actions">
                <Button size="sm" variant="ghost" onClick={() => setEditing({ profile: p })}>
                  {t("settings.edit")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRemoving(p)}>
                  {t("settings.delete")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="settings-section" aria-labelledby="settings-tax">
      <header className="settings-section__head">
        <h2 id="settings-tax" className="h3">
          {t("settings.tax.title")}
        </h2>
        {canManage && <Button onClick={() => setEditing({ profile: null })}>{t("settings.tax.add")}</Button>}
      </header>
      <p className="caption">{t("settings.tax.lead")}</p>
      {data.tax_profiles.length === 0 ? (
        <EmptyState title={t("settings.tax.empty")} text={t("settings.tax.emptyText")} />
      ) : (
        <DataTable caption={t("settings.tax.title")} columns={columns} rows={data.tax_profiles} rowKey={(p) => p.id} />
      )}
      {editing && <TaxForm orgId={orgId} data={data} profile={editing.profile} today={today} onClose={() => setEditing(null)} />}
      {removing && (
        <Confirm title={t("settings.tax.deleteTitle")} action={t("settings.delete")} loading={remove.isPending} onConfirm={() => remove.mutate(removing.id)} onClose={() => setRemoving(null)}>
          {t("settings.tax.deleteText", { date: f.date(removing.valid_from) })}
        </Confirm>
      )}
    </section>
  );
}

function TaxForm({ orgId, data, profile, today, onClose }: { orgId: string; data: Settings; profile: TaxProfile | null; today: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<TaxDraft>(() => taxDraft(profile, today));
  const patch = (p: Partial<TaxDraft>) => setDraft((d) => ({ ...d, ...p }));
  const save = useSettingsMutation(
    orgId,
    () => (profile ? updateTaxProfile(orgId, profile.id, taxBody(draft)) : createTaxProfile(orgId, taxBody(draft))),
    "settings.tax.saved",
    onClose,
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (taxValid(draft)) save.mutate(undefined);
  };
  const hint = data.tax_rates.find((r) => (draft.regime === "turnover" ? r.code.startsWith("turnover") : false));
  return (
    <Dialog
      open
      title={t(profile ? "settings.tax.editTitle" : "settings.tax.addTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("settings.cancel")}
          </Button>
          <Button type="submit" form="tax-form" disabled={!taxValid(draft)} loading={save.isPending}>
            {t("settings.save")}
          </Button>
        </>
      }
    >
      <form id="tax-form" className="settings-form" onSubmit={submit}>
        <TextInput label={t("settings.tax.from")} help={t("settings.tax.fromHelp")} type="date" required value={draft.valid_from} onValueChange={(valid_from) => patch({ valid_from })} />
        <Select label={t("settings.tax.regimeLabel")} value={draft.regime} onValueChange={(regime) => patch({ regime: regime as TaxDraft["regime"] })} options={REGIMES.map((r) => ({ value: r, label: t(`settings.tax.regime.${r}`) }))} help={t(`settings.tax.regimeHelp.${draft.regime}`)} />
        {draft.regime === "turnover" && (
          <>
            <NumberInput label={t("settings.tax.rate")} help={hint ? t("settings.tax.rateHint", { rate: Number(hint.rate_pct) }) : undefined} suffix="%" value={draft.rate} onValueChange={(rate) => patch({ rate })} />
            <Select label={t("settings.tax.baseLabel")} value={draft.base} onValueChange={(base) => patch({ base: base as TaxDraft["base"] })} options={BASES.map((b) => ({ value: b, label: t(`settings.tax.base.${b}`) }))} />
          </>
        )}
        {draft.regime === "vat_profit" && (
          <>
            <NumberInput label={t("settings.tax.vat")} suffix="%" value={draft.vat} onValueChange={(vat) => patch({ vat })} />
            <NumberInput label={t("settings.tax.profit")} suffix="%" value={draft.profit} onValueChange={(profit) => patch({ profit })} />
          </>
        )}
      </form>
    </Dialog>
  );
}
