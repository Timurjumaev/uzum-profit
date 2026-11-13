// Uzum qabulidagi farq (TM7, ADR-061 §8; 02 M10, F33, F52). Bog'langan postavka qabul qilinganda jo'natilgan va qabul
// qilingan soni solishtiriladi. Kam bo'lsa sotuvchi tanlaydi: "Uzum yo'qotdi" (kamomad ro'yxatiga) yoki "Men sanashda
// adashganman" (xarid soni tuzatiladi). Ko'p bo'lsa: shu SKU'da ochiq kamomad bo'lsa "Topildi", bo'lmasa "Sonni oshirish".
// Kamomad holati: Ochiq → Topildi / Kompensatsiya qilindi (summa) / Zarar deb yopildi (zarar foyda hisobida — F52).
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, meQuery, receivingQuery, resolveReceiving, updateShortage } from "../../app/query";
import { Badge, Banner, Button, EmptyState, MoneyInput, Skeleton, useToast } from "../../components/ui";
import type { Receiving as ReceivingData, ReceivingDiff, ResolveIn, Shortage, ShortagePatch } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { MANAGE_ROLES } from "../purchases/Purchases";

type Action = ResolveIn["action"];

export function Receiving() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const canManage = MANAGE_ROLES.includes(org.role);
  const query = useQuery(receivingQuery(org.id));
  const client = useQueryClient();
  const toast = useToast();
  const apply = async (data: ReceivingData, message: string) => {
    client.setQueryData(receivingQuery(org.id).queryKey, data);
    toast.show(message, "positive");
    await Promise.all([["purchases"], ["dashboard"], ["pnl"], ["inventory"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", org.id, ...k] })));
  };
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const resolve = useMutation({
    mutationFn: (body: ResolveIn) => resolveReceiving(org.id, body),
    onSuccess: (data, body) => apply(data, t(`receiving.done.${body.action}`)),
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ShortagePatch }) => updateShortage(org.id, id, body),
    onSuccess: (data) => apply(data, t("receiving.shortageSaved")),
    onError: fail,
  });
  return (
    <section className="purchases dispatches receiving">
      <Link to="/dispatches" className="purchase__back">
        ← {t("receiving.back")}
      </Link>
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("receiving.title")}</h1>
        </div>
      </header>
      <p className="caption">{t("receiving.lead")}</p>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} />
      ) : !query.data ? (
        <Skeleton label={t("common.loading")} lines={4} />
      ) : (
        <>
          <section className="purchase__block" aria-labelledby="receiving-diffs-title">
            <h2 id="receiving-diffs-title" className="h3">
              {t("receiving.diffsTitle")}
            </h2>
            {query.data.diffs.length === 0 ? (
              <EmptyState title={t("receiving.diffsEmpty")} text={t("receiving.diffsEmptyText")} />
            ) : (
              <ul className="dispatch-list" aria-label={t("receiving.diffsTitle")}>
                {query.data.diffs.map((d) => (
                  <DiffCard key={`${d.dispatch_id}:${d.sku_id}`} d={d} canManage={canManage} pending={resolve.isPending && resolve.variables?.dispatch_id === d.dispatch_id && resolve.variables.sku_id === d.sku_id ? resolve.variables.action : null} onResolve={(action) => resolve.mutate({ dispatch_id: d.dispatch_id, sku_id: d.sku_id, action })} />
                ))}
              </ul>
            )}
          </section>
          <section className="purchase__block" aria-labelledby="receiving-shortages-title">
            <h2 id="receiving-shortages-title" className="h3">
              {t("receiving.shortagesTitle")}
            </h2>
            {query.data.shortages.length === 0 ? (
              <EmptyState title={t("receiving.shortagesEmpty")} text={t("receiving.shortagesEmptyText")} />
            ) : (
              <ul className="dispatch-list" aria-label={t("receiving.shortagesTitle")}>
                {query.data.shortages.map((s) => (
                  <ShortageCard key={s.id} s={s} canManage={canManage} amounts={query.data.amounts} pending={patch.isPending && patch.variables?.id === s.id} onPatch={(body) => patch.mutate({ id: s.id, body })} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}

function DiffCard({ d, canManage, pending, onResolve }: { d: ReceivingDiff; canManage: boolean; pending: Action | null; onResolve: (action: Action) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const name = d.title ?? d.barcode ?? "—";
  const short = d.diff < 0;
  const actions: Action[] = short ? ["lost", "miscount"] : d.open_shortages > 0 ? ["found"] : ["recount"];
  return (
    <li className="cargo-pool__card">
      <div className="purchase-cell">
        <span>
          {d.resolution ? <Badge tone="neutral">{t(`receiving.resolution.${d.resolution}`)}</Badge> : <Badge tone={short ? "negative" : "warning"}>{t(short ? "receiving.short" : "receiving.over", { count: Math.abs(d.diff) })}</Badge>} <strong>{name}</strong>
        </span>
        <span className="caption">{[d.shop, t("receiving.invoice", { number: d.invoice_number ?? "—" }), f.date(d.accepted_on)].filter(Boolean).join(" · ")}</span>
        <span className="caption">
          {t("receiving.counts", { shipped: f.number(d.shipped), accepted: f.number(d.accepted) })}
          {d.value !== null && ` · ${t("receiving.value", { amount: f.money(d.value) })}`}
        </span>
        {d.fines_total !== null && <span className="caption">{t("receiving.fines", { count: d.fines.length, amount: f.money(d.fines_total) })}</span>}
        {!d.resolution && !short && d.open_shortages > 0 && <span className="caption">{t("receiving.openHint", { count: d.open_shortages })}</span>}
      </div>
      {canManage && !d.resolution && (
        <div className="dispatch-list__actions">
          {actions.map((a, i) => (
            <Button key={a} variant={i === 0 ? "primary" : "secondary"} disabled={pending !== null && pending !== a} loading={pending === a} onClick={() => onResolve(a)} aria-label={`${t(`receiving.action.${a}`)}: ${name}`}>
              {t(`receiving.action.${a}`)}
            </Button>
          ))}
        </div>
      )}
    </li>
  );
}

function ShortageCard({ s, canManage, amounts, pending, onPatch }: { s: Shortage; canManage: boolean; amounts: boolean; pending: boolean; onPatch: (body: ShortagePatch) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [editing, setEditing] = useState(false);
  const [comp, setComp] = useState<string | null>(null);
  const name = s.title ?? "—";
  const tone = s.status === "open" ? "negative" : s.status === "written_off" ? "warning" : "positive";
  const valid = comp !== null && !comp.startsWith("-");
  return (
    <li className="cargo-pool__card">
      <div className="purchase-cell">
        <span>
          <Badge tone={tone}>{t(`receiving.status.${s.status}`)}</Badge> <strong>{name}</strong>
        </span>
        <span className="caption">{[s.shop, t("receiving.units", { count: s.qty }), s.amount !== null ? f.money(s.amount) : null, f.date(s.created_on)].filter(Boolean).join(" · ")}</span>
        {s.compensation !== null && <span className="caption">{t("receiving.compensation", { amount: f.money(s.compensation) })}</span>}
        {s.loss !== null && <span className="caption">{t("receiving.loss", { amount: f.money(s.loss) })}</span>}
        {s.closed_on && <span className="caption">{t("receiving.closedOn", { date: f.date(s.closed_on) })}</span>}
      </div>
      {canManage && (
        <div className="dispatch-list__actions">
          {s.status === "open" ? (
            editing ? (
              <>
                <MoneyInput label={t("receiving.compensationLabel")} aria-label={`${t("receiving.compensationLabel")}: ${name}`} value={comp} onValueChange={setComp} />
                <Button variant="primary" disabled={!valid} loading={pending} onClick={() => comp !== null && onPatch({ status: "compensated", compensation: comp })}>
                  {t("receiving.save")}
                </Button>
                <Button variant="ghost" onClick={() => setEditing(false)}>
                  {t("receiving.cancelEdit")}
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" loading={pending} onClick={() => onPatch({ status: "found" })} aria-label={`${t("receiving.set.found")}: ${name}`}>
                  {t("receiving.set.found")}
                </Button>
                {amounts && (
                  <Button variant="secondary" onClick={() => setEditing(true)} aria-label={`${t("receiving.set.compensated")}: ${name}`}>
                    {t("receiving.set.compensated")}
                  </Button>
                )}
                <Button variant="ghost" onClick={() => onPatch({ status: "written_off" })} aria-label={`${t("receiving.set.written_off")}: ${name}`}>
                  {t("receiving.set.written_off")}
                </Button>
              </>
            )
          ) : (
            <Button variant="ghost" loading={pending} onClick={() => onPatch({ status: "open" })} aria-label={`${t("receiving.set.open")}: ${name}`}>
              {t("receiving.set.open")}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}
