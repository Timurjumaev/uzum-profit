// Bildirishnomalar (B6.1, 02 M15): har foydalanuvchi o'zi uchun — qaysi hodisa yoqilgan, chegaralar (xulosa vaqti, zarar
// zanjiri, sinxron soatlari) va tinch soatlar. Kritik hodisa tinch soatda ham keladi. Hali ishlamaydigan hodisa — "tez orada"
// (bosqich bilan); rolga tegishli bo'lmagani ko'rsatilmaydi. Yuborish kanali (Telegram) — B6.2.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { notificationSettingsQuery, setNotificationSettings } from "../../app/query";
import { Badge, Banner, Button, NumberInput, Skeleton, TextInput, useToast } from "../../components/ui";
import type { NotificationEvent, NotificationSettings as Data, NotificationSettingsIn } from "../../lib/api/types";

type Draft = { rules: Record<string, { enabled: boolean; params: Record<string, string | null> }>; quiet: boolean; from: string; to: string };

const hhmm = (v: string | null | undefined) => (v ? v.slice(0, 5) : "");

function draftOf(data: Data): Draft {
  return {
    rules: Object.fromEntries(data.events.map((e) => [e.event, { enabled: e.enabled, params: Object.fromEntries(Object.entries(e.params).map(([k, v]) => [k, String(v)])) }])),
    quiet: data.quiet_from !== null,
    from: hhmm(data.quiet_from) || "22:00",
    to: hhmm(data.quiet_to) || "08:00",
  };
}

/** Chegara to'g'rimi (server ham tekshiradi). */
export function paramValid(key: string, value: string | null): boolean {
  if (value === null || value === "") return false;
  if (key === "at") return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
  const n = Number(value);
  const [low, high] = key === "streak" ? [2, 10] : key === "hours" ? [1, 24] : [1, 30];
  return Number.isInteger(n) && n >= low && n <= high;
}

export function NotificationSettings({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const query = useQuery(notificationSettingsQuery(orgId));
  return (
    <section className="settings-section" aria-labelledby="settings-notifications">
      <h2 id="settings-notifications" className="h3">
        {t("settings.notifications.title")}
      </h2>
      <p className="caption">{t("settings.notifications.lead")}</p>
      {query.isError ? <Banner tone="negative" title={errorText(query.error, t)} /> : !query.data ? <Skeleton label={t("common.loading")} lines={4} /> : <Form key={JSON.stringify(query.data)} orgId={orgId} data={query.data} />}
    </section>
  );
}

function Form({ orgId, data }: { orgId: string; data: Data }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => draftOf(data));
  const shown = data.events.filter((e) => e.available || e.stage !== null);
  const live = shown.filter((e) => e.available);
  const valid = live.every((e) => !draft.rules[e.event]!.enabled || Object.entries(draft.rules[e.event]!.params).every(([k, v]) => paramValid(k, v))) && (!draft.quiet || (paramValid("at", draft.from) && paramValid("at", draft.to) && draft.from !== draft.to));
  const save = useMutation({
    mutationFn: () => {
      const body: NotificationSettingsIn = {
        rules: live.map((e) => {
          const r = draft.rules[e.event]!;
          return { event: e.event, enabled: r.enabled, params: r.enabled ? Object.fromEntries(Object.entries(r.params).map(([k, v]) => [k, k === "at" ? v : Number(v)])) : {} };
        }),
        quiet_from: draft.quiet ? draft.from : null,
        quiet_to: draft.quiet ? draft.to : null,
      };
      return setNotificationSettings(orgId, body);
    },
    onSuccess: (out) => {
      client.setQueryData(notificationSettingsQuery(orgId).queryKey, out);
      toast.show(t("settings.notifications.saved"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const setRule = (event: string, patch: Partial<Draft["rules"][string]>) => setDraft((d) => ({ ...d, rules: { ...d.rules, [event]: { ...d.rules[event]!, ...patch } } }));
  const setParam = (event: string, key: string, value: string | null) => setRule(event, { params: { ...draft.rules[event]!.params, [key]: value } });
  return (
    <form
      className="settings-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) save.mutate();
      }}
    >
      <ul className="notify-list" aria-label={t("settings.notifications.events")}>
        {shown.map((e) => (
          <EventRow key={e.event} e={e} rule={draft.rules[e.event]!} onToggle={(enabled) => setRule(e.event, { enabled })} onParam={(k, v) => setParam(e.event, k, v)} />
        ))}
      </ul>
      <fieldset className="settings-fieldset notify-quiet">
        <legend className="label">{t("settings.notifications.quiet")}</legend>
        <label className="notify-check">
          <input type="checkbox" checked={draft.quiet} onChange={(ev) => setDraft((d) => ({ ...d, quiet: ev.target.checked }))} /> <span>{t("settings.notifications.quietOn")}</span>
        </label>
        {draft.quiet && (
          <div className="notify-quiet__times">
            <TextInput label={t("settings.notifications.quietFrom")} type="time" value={draft.from} onValueChange={(from) => setDraft((d) => ({ ...d, from }))} />
            <TextInput label={t("settings.notifications.quietTo")} type="time" value={draft.to} onValueChange={(to) => setDraft((d) => ({ ...d, to }))} />
          </div>
        )}
        <p className="caption">{t("settings.notifications.quietHint")}</p>
      </fieldset>
      {!valid && <Banner tone="warning" title={t("settings.notifications.invalid")} />}
      <p className="caption">{t("settings.notifications.channelSoon")}</p>
      <div className="settings-section__row">
        <Button type="submit" variant="primary" disabled={!valid} loading={save.isPending}>
          {t("settings.save")}
        </Button>
      </div>
    </form>
  );
}

function EventRow({ e, rule, onToggle, onParam }: { e: NotificationEvent; rule: Draft["rules"][string]; onToggle: (on: boolean) => void; onParam: (key: string, value: string | null) => void }) {
  const { t } = useTranslation();
  const name = t(`settings.notifications.event.${e.event}`);
  return (
    <li className="notify-row">
      <label className="notify-check">
        <input type="checkbox" checked={e.available && rule.enabled} disabled={!e.available} onChange={(ev) => onToggle(ev.target.checked)} /> <span>{name}</span>
        {e.critical && <Badge tone="warning">{t("settings.notifications.critical")}</Badge>}
        {e.stage && <Badge tone="neutral">{t("settings.notifications.soon", { stage: e.stage })}</Badge>}
      </label>
      {e.available && rule.enabled && Object.keys(rule.params).length > 0 && (
        <div className="notify-row__params">
          {Object.entries(rule.params).map(([k, v]) =>
            k === "at" ? (
              <TextInput key={k} label={t("settings.notifications.param.at")} aria-label={`${t("settings.notifications.param.at")}: ${name}`} type="time" value={v ?? ""} onValueChange={(x) => onParam(k, x)} />
            ) : (
              <NumberInput key={k} label={t(`settings.notifications.param.${k}`)} aria-label={`${t(`settings.notifications.param.${k}`)}: ${name}`} value={v} onValueChange={(x) => onParam(k, x)} digits={0} />
            ),
          )}
        </div>
      )}
    </li>
  );
}
