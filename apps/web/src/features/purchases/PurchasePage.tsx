// Xarid sahifasi (M9, B4.6; 04 §6.2, §7.4): Partiya yo'li (bosqich sanalari, joriy bosqichda kunlar va kutilgan sana
// F25), qatorlar jadvali, xarajat komponentlari (kurs bilan), birlik tannarx tarkibi o'ngda (F20 — jonli, API'dan;
// taxminiy belgilar F22). Har tahrirdan keyin javobda yangi hisob; sotuvlar tannarxi fon ishida qayta hisoblanadi
// ("qayta hisoblanmoqda" banneri). Omborchi summalarni ko'rmaydi: qatorlar, qabul va bosqichlar.
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { copyPurchase, currentOrg, deleteComponent, deleteLine, deletePurchase, meQuery, purchaseQuery, updatePurchase } from "../../app/query";
import { Badge, Banner, Button, DataTable, Dialog, EmptyState, FormulaPopover, Skeleton, TextInput, Timeline, useToast, type Column } from "../../components/ui";
import type { CostComponent, PurchaseDetail, PurchaseLine, PurchaseStage } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { ComponentForm, lineLabel } from "./ComponentForm";
import { LineForm } from "./LineForm";
import { changedDates, DATED_STAGES, datesInOrder, isEstimated, nextStage, timelineStages, visibleFlags } from "./model";
import { PurchaseForm } from "./PurchaseForm";
import { MANAGE_ROLES } from "./Purchases";

type Editing = { kind: "header" } | { kind: "dates" } | { kind: "delete" } | { kind: "line"; line: PurchaseLine | null } | { kind: "component"; component: CostComponent | null };

export function PurchasePage() {
  const { t } = useTranslation();
  const { purchaseId } = useParams({ strict: false }) as { purchaseId: string };
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const query = useQuery(purchaseQuery(org.id, purchaseId));
  if (query.isError)
    return (
      <section className="purchase">
        <BackLink />
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  if (!query.data) return <Skeleton label={t("common.loading")} lines={10} />;
  return <PurchaseView orgId={org.id} detail={query.data} canManage={MANAGE_ROLES.includes(org.role)} />;
}

function BackLink() {
  const { t } = useTranslation();
  return (
    <Link to="/purchases" className="purchase__back">
      ← {t("purchases.back")}
    </Link>
  );
}

function PurchaseView({ orgId, detail, canManage }: { orgId: string; detail: PurchaseDetail; canManage: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<Editing | null>(null);
  const p = detail.purchase;
  const key = purchaseQuery(orgId, p.id).queryKey;
  /** Yozuv javobi — yangi hisob bilan butun xarid: keshga qo'yiladi; ro'yxat va hisobotlar eskiradi. */
  const applied = async (next: PurchaseDetail, message: string) => {
    client.setQueryData(key, next);
    setEditing(null);
    toast.show(message, "positive");
    await Promise.all(
      [["purchases", "list"], ["pnl"], ["dashboard"], ["skus"], ["sku"], ["inventory"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", orgId, ...k] })),
    );
  };
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const mark = useMutation({
    mutationFn: (stage: PurchaseStage) => updatePurchase(orgId, p.id, { dates: { [stage]: todayTashkent() } }),
    onSuccess: (next) => applied(next, t("purchases.saved")),
    onError: fail,
  });
  const copy = useMutation({
    mutationFn: () => copyPurchase(orgId, p.id),
    onSuccess: async (next) => {
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "purchases", "list"] });
      toast.show(t("purchases.copied"), "positive");
      void navigate({ to: "/purchases/$purchaseId", params: { purchaseId: next.purchase.id } });
    },
    onError: fail,
  });
  const removeLine = useMutation({
    mutationFn: (id: string) => deleteLine(orgId, p.id, id),
    onSuccess: (next) => applied(next, t("purchases.lines.deleted")),
    onError: fail,
  });
  const removeComponent = useMutation({
    mutationFn: (id: string) => deleteComponent(orgId, p.id, id),
    onSuccess: (next) => applied(next, t("purchases.components.deleted")),
    onError: fail,
  });
  const next = nextStage(p.stage);
  const amounts = detail.amounts;
  const est = (flags: string[]) => (isEstimated(flags) ? "~" : "");

  const lineColumns: Column<PurchaseLine>[] = [
    {
      key: "item",
      header: t("purchases.lines.col.item"),
      render: (l) => (
        <span className="purchase-cell">
          <span className="purchase-cell__title">{l.item_name ?? l.temp_name ?? "—"}</span>
          {l.variant && <span className="caption">{l.variant}</span>}
          {l.url && (
            <a href={l.url} target="_blank" rel="noreferrer noopener" className="caption">
              {t("purchases.lines.link")} <ExternalLink size={12} aria-hidden />
            </a>
          )}
        </span>
      ),
    },
    { key: "ordered", header: t("purchases.lines.col.ordered"), numeric: true, render: (l) => f.number(l.ordered_qty) },
    {
      key: "received",
      header: t("purchases.lines.col.received"),
      numeric: true,
      render: (l) =>
        l.received_qty === null ? (
          <span className="caption">{t("purchases.lines.notReceived")}</span>
        ) : (
          <>
            {f.number(l.received_qty)}
            {l.shortage > 0 && (
              <>
                {" "}
                <Badge tone="warning">{t("purchases.lines.shortage", { count: l.shortage })}</Badge>
              </>
            )}
          </>
        ),
    },
    ...(amounts
      ? [{ key: "price", header: t("purchases.lines.col.price"), numeric: true, render: (l: PurchaseLine) => (l.unit_price === null ? "—" : f.currency(l.unit_price, l.currency ?? "UZS")) }]
      : []),
    { key: "weight", header: t("purchases.lines.col.weight"), numeric: true, render: (l) => (l.unit_weight === null ? "—" : t("purchases.lines.kg", { value: f.number(l.unit_weight, { digits: 3, trim: true }) })) },
    ...(amounts
      ? [
          {
            key: "unit",
            header: t("purchases.lines.col.unitCost"),
            numeric: true,
            render: (l: PurchaseLine) => (l.cost?.unit_cost == null ? "—" : `${est(l.flags)}${f.money(l.cost.unit_cost, { unit: false })}`),
          },
        ]
      : []),
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (l: PurchaseLine) => (
              <span className="expenses-actions">
                <Button variant="ghost" onClick={() => setEditing({ kind: "line", line: l })} aria-label={`${t("purchases.lines.edit")}: ${lineLabel(l)}`}>
                  {t("purchases.lines.edit")}
                </Button>
                <Button variant="ghost" loading={removeLine.isPending && removeLine.variables === l.id} onClick={() => removeLine.mutate(l.id)} aria-label={`${t("purchases.lines.delete")}: ${lineLabel(l)}`}>
                  {t("purchases.lines.delete")}
                </Button>
              </span>
            ),
          },
        ]
      : []),
  ];

  const rateText = (c: CostComponent) => {
    if (c.error) return <Badge tone="negative">{c.error}</Badge>;
    if (c.applied_rate === null) return "—";
    return t("purchases.components.rateOn", {
      rate: f.number(c.applied_rate, { digits: 2, trim: true }),
      mode: t(`purchases.components.rateLabel.${c.rate_mode}`),
      date: c.rate_day ? f.date(c.rate_day) : "",
    });
  };
  const componentColumns: Column<CostComponent>[] = [
    { key: "kind", header: t("purchases.components.col.kind"), render: (c) => t(`purchases.components.kind.${c.kind}`) },
    { key: "amount", header: t("purchases.components.col.amount"), numeric: true, render: (c) => (c.currency === "UZS" ? f.money(c.amount, { unit: false }) : f.currency(c.amount, c.currency)) },
    { key: "rate", header: t("purchases.components.col.rate"), render: rateText },
    { key: "uzs", header: t("purchases.components.col.uzs"), numeric: true, render: (c) => (c.amount_uzs === null ? "—" : f.money(c.amount_uzs, { unit: false })) },
    { key: "allocation", header: t("purchases.components.col.allocation"), render: (c) => t(`purchases.components.allocation.${c.allocation}`) },
    {
      key: "lines",
      header: t("purchases.components.col.lines"),
      render: (c) => (c.lines === null ? t("purchases.components.allLines") : t("purchases.components.someLines", { count: c.lines.length })),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: t("expenses.own.actions"),
            render: (c: CostComponent) => {
              const name = t(`purchases.components.kind.${c.kind}`);
              return (
                <span className="expenses-actions">
                  <Button variant="ghost" onClick={() => setEditing({ kind: "component", component: c })} aria-label={`${t("purchases.components.edit")}: ${name}`}>
                    {t("purchases.components.edit")}
                  </Button>
                  <Button variant="ghost" loading={removeComponent.isPending && removeComponent.variables === c.id} onClick={() => removeComponent.mutate(c.id)} aria-label={`${t("purchases.components.delete")}: ${name}`}>
                    {t("purchases.components.delete")}
                  </Button>
                </span>
              );
            },
          },
        ]
      : []),
  ];

  return (
    <section className="purchase">
      <BackLink />
      <header className="purchase__head">
        <div>
          <h1 className="h2">{p.title ?? t("purchases.untitled")}</h1>
          <p className="caption">
            <Badge tone={p.stage === "closed" ? "positive" : p.stage === "draft" ? "neutral" : "info"}>{t(`purchases.stage.${p.stage}`)}</Badge>
            {p.supplier_name && ` · ${p.supplier_name}`}
            {p.carrier_name && ` · ${p.carrier_name}`}
          </p>
          {p.note && <p className="caption">{p.note}</p>}
        </div>
        {canManage && (
          <div className="purchase__actions">
            <Button variant="secondary" onClick={() => setEditing({ kind: "header" })}>
              {t("purchases.edit")}
            </Button>
            <Button variant="secondary" loading={copy.isPending} onClick={() => copy.mutate()}>
              {t("purchases.copy")}
            </Button>
            <Button variant="ghost" onClick={() => setEditing({ kind: "delete" })}>
              {t("purchases.delete")}
            </Button>
          </div>
        )}
      </header>

      {p.error && (
        <Banner tone="negative" title={t("purchases.error", { reason: p.error })}>
          {t("purchases.errorHint")}
        </Banner>
      )}
      {detail.recalc_pending && amounts && (
        <Banner tone="info" title={t("purchases.pending")}>
          {t("purchases.pendingText")}
        </Banner>
      )}
      {!amounts && (
        <Banner tone="info" title={t("purchases.noAmounts")}>
          {t("purchases.noAmountsText")}
        </Banner>
      )}

      <section className="purchase__path" aria-labelledby="purchase-path-title">
        <div className="purchase__section-head">
          <h2 id="purchase-path-title" className="h3">
            {t("purchases.path")}
          </h2>
          {canManage && (
            <div className="purchase__actions">
              {next && (
                <Button variant="secondary" loading={mark.isPending} onClick={() => mark.mutate(next)}>
                  {t("purchases.markNext", { stage: t(`purchases.stage.${next}`) })}
                </Button>
              )}
              <Button variant="ghost" onClick={() => setEditing({ kind: "dates" })}>
                {t("purchases.editDates")}
              </Button>
            </div>
          )}
        </div>
        <div className="purchase__timeline">
          <Timeline label={t("purchases.path")} stages={timelineStages(p.timeline, (s) => t(`purchases.stage.${s}`))} />
        </div>
        <p className="caption">{t("purchases.pathNote")}</p>
      </section>

      <div className="purchase__layout">
        <div className="purchase__main">
          <section aria-labelledby="purchase-lines-title" className="purchase__block">
            <div className="purchase__section-head">
              <h2 id="purchase-lines-title" className="h3">
                {t("purchases.lines.title")}
              </h2>
              {canManage && <Button onClick={() => setEditing({ kind: "line", line: null })}>{t("purchases.lines.add")}</Button>}
            </div>
            {detail.lines.length === 0 ? (
              <EmptyState title={t("purchases.lines.empty")} text={t("purchases.lines.emptyText")} />
            ) : (
              <DataTable caption={t("purchases.lines.title")} density="compact" columns={lineColumns} rows={detail.lines} rowKey={(l) => l.id} />
            )}
          </section>
          {amounts && (
            <section aria-labelledby="purchase-components-title" className="purchase__block">
              <div className="purchase__section-head">
                <h2 id="purchase-components-title" className="h3">
                  {t("purchases.components.title")}
                </h2>
                {canManage && (
                  <Button onClick={() => setEditing({ kind: "component", component: null })} disabled={detail.lines.length === 0}>
                    {t("purchases.components.add")}
                  </Button>
                )}
              </div>
              {detail.components.length === 0 ? (
                <EmptyState title={t("purchases.components.empty")} text={t("purchases.components.emptyText")} />
              ) : (
                <DataTable caption={t("purchases.components.title")} density="compact" columns={componentColumns} rows={detail.components} rowKey={(c) => c.id} />
              )}
            </section>
          )}
        </div>
        <CostPanel detail={detail} />
      </div>

      {editing?.kind === "header" && <PurchaseForm orgId={orgId} detail={detail} onClose={() => setEditing(null)} onSaved={(d) => void applied(d, t("purchases.saved"))} />}
      {editing?.kind === "dates" && <DatesForm orgId={orgId} detail={detail} onClose={() => setEditing(null)} onSaved={(d) => void applied(d, t("purchases.saved"))} />}
      {editing?.kind === "line" && (
        <LineForm orgId={orgId} purchaseId={p.id} line={editing.line} amounts={amounts} onClose={() => setEditing(null)} onSaved={(d) => void applied(d, t("purchases.lines.saved"))} />
      )}
      {editing?.kind === "component" && (
        <ComponentForm
          orgId={orgId}
          purchaseId={p.id}
          component={editing.component}
          lines={detail.lines}
          onClose={() => setEditing(null)}
          onSaved={(d) => void applied(d, t("purchases.components.saved"))}
        />
      )}
      {editing?.kind === "delete" && <DeleteDialog orgId={orgId} purchaseId={p.id} onClose={() => setEditing(null)} />}
    </section>
  );
}

/** Birlik tannarx tarkibi (o'ngda doim ko'rinadi): xarid jami, turlar bo'yicha, o'rtacha va qatorlar bo'yicha. */
function CostPanel({ detail }: { detail: PurchaseDetail }) {
  const { t } = useTranslation();
  const f = useFormat();
  const p = detail.purchase;
  const flags = visibleFlags(p.flags);
  const help = <FormulaPopover metric={t("purchases.cost.title")} code={t("purchases.cost.formula.code")} formula={t("purchases.cost.formula.formula")} source={t("purchases.cost.formula.source")} />;
  return (
    <aside className="purchase__cost" aria-labelledby="purchase-cost-title">
      <h2 id="purchase-cost-title" className="h3">
        {t("purchases.cost.title")} {help}
      </h2>
      {!detail.amounts ? (
        <p className="caption">{t("purchases.cost.hidden")}</p>
      ) : p.total === null ? (
        <p className="caption">{p.error ? t("purchases.errorHint") : t("purchases.cost.empty")}</p>
      ) : (
        <>
          <dl className="purchase__dl">
            {Object.entries(detail.by_kind).map(([kind, value]) => (
              <div key={kind}>
                <dt>{t(`purchases.components.kind.${kind}`)}</dt>
                <dd className="num">{f.money(value, { unit: false })}</dd>
              </div>
            ))}
            <div className="is-total">
              <dt>{t("purchases.cost.total")}</dt>
              <dd className="num">{f.money(p.total)}</dd>
            </div>
            {p.unit_cost !== null && (
              <div className="is-total">
                <dt>{t("purchases.cost.average")}</dt>
                <dd className="num">
                  {isEstimated(p.flags) && "~"}
                  {f.money(p.unit_cost)}
                </dd>
              </div>
            )}
          </dl>
          {flags.length > 0 && (
            <ul className="purchase__flags">
              {flags.map((flag) => (
                <li key={flag}>
                  <Badge tone={flag === "cbu_rate" ? "info" : "warning"}>{flag === "cbu_rate" ? t("purchases.components.rateLabel.cbu") : t("terms.estimated")}</Badge> {t(`purchases.cost.flag.${flag}`)}
                </li>
              ))}
            </ul>
          )}
          <h3 className="purchase__sub">{t("purchases.cost.byLine")}</h3>
          <ul className="purchase__lines-cost">
            {detail.lines.map((l) => (
              <li key={l.id}>
                <span>{lineLabel(l)}</span>
                <span className="num">{l.cost?.unit_cost == null ? "—" : `${isEstimated(l.flags) ? "~" : ""}${f.money(l.cost.unit_cost)}`}</span>
                {l.cost && Object.keys(l.cost.breakdown).length > 0 && (
                  <span className="caption">
                    {Object.entries(l.cost.breakdown)
                      .map(([kind, value]) => `${t(`purchases.components.kind.${kind}`)} ${f.money(value, { unit: false })}`)
                      .join(" + ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}

function DatesForm({ orgId, detail, onClose, onSaved }: { orgId: string; detail: PurchaseDetail; onClose: () => void; onSaved: (d: PurchaseDetail) => void }) {
  const { t } = useTranslation();
  const before = detail.purchase.dates as Partial<Record<PurchaseStage, string | null>>;
  const [draft, setDraft] = useState<Partial<Record<PurchaseStage, string>>>(() => Object.fromEntries(DATED_STAGES.map((s) => [s, before[s] ?? ""])));
  const ordered = datesInOrder(draft);
  const save = useMutation({ mutationFn: () => updatePurchase(orgId, detail.purchase.id, { dates: changedDates(before, draft) }), onSuccess: onSaved });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ordered) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("purchases.datesTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button type="submit" form="dates-form" disabled={!ordered} loading={save.isPending}>
            {t("purchases.save")}
          </Button>
        </>
      }
    >
      <form id="dates-form" className="purchase-form" onSubmit={submit}>
        <p className="caption">{t("purchases.datesHint")}</p>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        {!ordered && <Banner tone="warning" title={t("purchases.datesOrder")} />}
        <div className="purchase-form__dates">
          {DATED_STAGES.map((s) => (
            <TextInput key={s} label={t(`purchases.stage.${s}`)} type="date" optional value={draft[s] ?? ""} onValueChange={(v) => setDraft((d) => ({ ...d, [s]: v }))} />
          ))}
        </div>
      </form>
    </Dialog>
  );
}

function DeleteDialog({ orgId, purchaseId, onClose }: { orgId: string; purchaseId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const navigate = useNavigate();
  const remove = useMutation({
    mutationFn: () => deletePurchase(orgId, purchaseId),
    onSuccess: async () => {
      client.removeQueries({ queryKey: purchaseQuery(orgId, purchaseId).queryKey });
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "purchases", "list"] });
      toast.show(t("purchases.deleted"), "positive");
      void navigate({ to: "/purchases" });
    },
  });
  return (
    <Dialog
      open
      title={t("purchases.deleteTitle")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button variant="destructive" loading={remove.isPending} onClick={() => remove.mutate()}>
            {t("purchases.delete")}
          </Button>
        </>
      }
    >
      {remove.isError && <Banner tone="negative" title={errorText(remove.error, t)} />}
      <p>{t("purchases.deleteText")}</p>
    </Dialog>
  );
}
