// Xaridlar ro'yxati (M9, B4.6; 04 §7.4): bosqich guruhi (URL'da), har xaridda ixcham Partiya yo'li, dona (buyurtma /
// qabul), jami va o'rtacha tannarx/dona (F20 — jonli, API'dan; taxminiy bo'lsa "~"). "Yangi xarid" — egasi, menejer,
// omborchi (`manage_purchases`); omborchi summalarni ko'rmaydi.
import { keepPreviousData, useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { currentOrg, markArrived, meQuery, purchasesPageQuery } from "../../app/query";
import { PURCHASE_GROUPS, purchasesSearch, type PurchaseGroup } from "../../app/search";
import { Badge, Banner, Button, DataTable, EmptyState, ExportButton, Pagination, Skeleton, TextInput, usePageSize, useToast, type Column, PageHelp } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { PathMark, PurchaseRow } from "../../lib/api/types";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";
import { GROUP_STATES, isEstimated } from "./model";
import { QuickPurchaseForm } from "./QuickPurchaseForm";

export const MANAGE_ROLES = ["owner", "manager", "warehouse"];

/** Holat nomi; TM9.8 — "Keldi", sanalmagan: "Omborimda · sanalmagan". */
export function stateLabel(t: (key: string) => string, state: string, counted: boolean): string {
  return state === "in_stock" && !counted ? t("purchases.uncounted") : t(`purchases.state.${state}`);
}

/** Ixcham Partiya yo'li (ADR-061 §1): uch nuqta (Yo'lda → Omborimda → Uzumda) + joriy holat, kunlari va kutilgan sana. */
export function CompactPath({ marks }: { marks: PathMark[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const current = marks.find((m) => m.mark === "current");
  const label = current?.uncounted ? t("purchases.uncounted") : t(`purchases.state.${current?.state ?? "in_transit"}`);
  return (
    <span className="purchase-path">
      <span className="purchase-path__dots" aria-hidden>
        {marks.map((m) => (
          <span key={m.state} className={cx("purchase-path__dot", `is-${m.mark}`, m.delayed && "is-delayed")} />
        ))}
      </span>
      <span className="purchase-path__label">
        {label}
        {current?.days != null && <span className="caption"> · {t("ui.daysPassed", { count: current.days })}</span>}
        {current?.expected && <span className="caption"> · {t("ui.expected", { date: f.date(current.expected).slice(0, 5) })}</span>}
        {current?.delayed && (
          <span className="ui-text--warning caption">
            {" "}
            <TriangleAlert size={14} aria-hidden /> {t("ui.status.delayed")}
          </span>
        )}
      </span>
    </span>
  );
}

export function Purchases() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const navigate = useNavigate();
  const search = purchasesSearch(useSearch({ strict: false }) as Record<string, unknown>);
  const group = search.group;
  const [size, setSize] = usePageSize();
  const query = useQuery({ ...purchasesPageQuery(org.id, group ? GROUP_STATES[group] : [], search.page, size), placeholderData: keepPreviousData });
  // So'ralgan sahifa oxirgisidan oshib ketgan bo'lsa API oxirgisini beradi — URL ham shunga o'tadi.
  const shownPage = query.data?.page;
  useEffect(() => {
    if (shownPage !== undefined && !query.isPlaceholderData && shownPage !== (search.page ?? 1)) {
      void navigate({ to: "/purchases", search: (prev) => ({ ...prev, group, page: shownPage > 1 ? shownPage : undefined }), replace: true });
    }
  }, [shownPage, query.isPlaceholderData, search.page, navigate, group]);
  const [adding, setAdding] = useState(false);
  // TM9.8: "Keldi" — bir nechta "Yo'lda" xaridni belgilab (sana — bugun, o'zgartiriladi).
  const [picked, setPicked] = useState<string[]>([]);
  const [arrivedOn, setArrivedOn] = useState(todayTashkent());
  const client = useQueryClient();
  const toast = useToast();
  const arrive = useMutation({
    mutationFn: () => markArrived(org.id, { purchase_ids: picked, arrived_on: arrivedOn }),
    onSuccess: async (out) => {
      setPicked([]);
      await Promise.all([["purchases"], ["inventory"], ["dashboard"]].map((k) => client.invalidateQueries({ queryKey: ["orgs", org.id, ...k] })));
      toast.show(t("purchases.arrived.saved", { count: out.updated }), "positive");
    },
  });
  const canManage = MANAGE_ROLES.includes(org.role);
  const amounts = query.data?.amounts ?? true;
  const setGroup = (next: PurchaseGroup | undefined) => void navigate({ to: "/purchases", search: (prev) => ({ ...prev, group: next, page: undefined }), replace: true });
  const units = (r: PurchaseRow) =>
    r.units_received === null
      ? r.state === "in_stock" && !r.counted
        ? `~${t("purchases.unitsOrdered", { ordered: f.number(r.units_ordered) })}`
        : t("purchases.unitsOrdered", { ordered: f.number(r.units_ordered) })
      : t("purchases.unitsReceived", { received: f.number(r.units_received), ordered: f.number(r.units_ordered) });
  const pickable = (r: PurchaseRow) => canManage && r.state === "in_transit";
  const columns: Column<PurchaseRow>[] = [
    {
      key: "purchase",
      header: t("purchases.col.purchase"),
      render: (r) => (
        <span className="purchase-cell">
          <Link to="/purchases/$purchaseId" params={{ purchaseId: r.id }} className="purchase-cell__title">
            {r.title ?? t("purchases.untitled")}
          </Link>
          {r.items.length > 0 && (
            <span className="caption" title={r.items.join(", ")}>
              {r.items.join(", ")}
              {r.line_count > r.items.length && ` ${t("purchases.more", { count: r.line_count - r.items.length })}`}
            </span>
          )}
          <span className="caption purchase-cell__meta">
            {stateLabel(t, r.state, r.counted)} · {units(r)}
            {r.track_no && ` · ${t("purchases.trackShort", { track: r.track_no })}`}
          </span>
          {pickable(r) && (
            <label className="purchase-cell__pick">
              <input
                type="checkbox"
                checked={picked.includes(r.id)}
                onChange={(e) => setPicked((p) => (e.target.checked ? [...p, r.id] : p.filter((x) => x !== r.id)))}
                aria-label={t("purchases.arrived.pick", { name: r.title ?? t("purchases.untitled") })}
              />
              <span className="caption">{t("purchases.arrived.pickHeader")}</span>
            </label>
          )}
        </span>
      ),
    },
    { key: "supplier", header: t("purchases.col.supplier"), render: (r) => r.supplier_name ?? "—" },
    { key: "path", header: t("purchases.col.path"), render: (r) => <CompactPath marks={r.path} /> },
    { key: "units", header: t("purchases.col.units"), numeric: true, render: units },
    ...(amounts
      ? [
          { key: "total", header: t("purchases.col.total"), numeric: true, render: (r: PurchaseRow) => (r.total === null ? "—" : f.money(r.total, { unit: false })) },
          {
            key: "unit",
            header: t("purchases.col.unitCost"),
            numeric: true,
            render: (r: PurchaseRow) =>
              r.error ? (
                <Badge tone="negative">{t("purchases.notCalculated")}</Badge>
              ) : r.unit_cost === null ? (
                "—"
              ) : (
                <span title={isEstimated(r.flags) ? t("terms.estimated") : undefined}>
                  {isEstimated(r.flags) && "~"}
                  {f.money(r.unit_cost, { unit: false })}
                </span>
              ),
          },
        ]
      : []),
  ];
  return (
    <section className="purchases">
      <header className="purchases__head">
        <div className="page-title">
          <h1 className="h2">{t("purchases.title")}</h1>
          <PageHelp page="purchases" />
        </div>
        <span className="purchases__actions">
          <Link to="/cargo-pool" className="ui-btn ui-btn--secondary ui-btn--md">
            {t("cargo.title")}
          </Link>
          <Link to="/shipments" className="ui-btn ui-btn--secondary ui-btn--md">
            {t("shipments.title")}
          </Link>
          <ExportButton orgId={org.id} table="purchases" />
          {canManage && (
            <Button variant="primary" onClick={() => setAdding(true)}>
              {t("purchases.add")}
            </Button>
          )}
        </span>
      </header>
      <div role="tablist" aria-label={t("purchases.groupsLabel")} className="orders-tabs">
        {([undefined, ...PURCHASE_GROUPS] as const).map((id) => (
          <button
            key={id ?? "all"}
            type="button"
            role="tab"
            aria-selected={group === id}
            aria-controls="purchases-panel"
            className={cx("orders-tab", group === id && "is-active")}
            onClick={() => setGroup(id)}
          >
            {t(`purchases.groups.${id ?? "all"}`)}
          </button>
        ))}
      </div>
      <div id="purchases-panel" role="tabpanel" aria-label={t("purchases.list")} className="purchases__panel purchases__panel--collapse">
        {!amounts && <Banner tone="info" title={t("purchases.noAmounts")}>{t("purchases.noAmountsText")}</Banner>}
        {picked.length > 0 && (
          <div className="purchases__arrive" role="group" aria-label={t("purchases.arrived.title")}>
            <TextInput label={t("purchases.arrived.on")} type="date" value={arrivedOn} onValueChange={setArrivedOn} max={todayTashkent()} />
            <Button variant="primary" loading={arrive.isPending} disabled={!arrivedOn} onClick={() => arrive.mutate()}>
              {t("purchases.arrived.save", { count: picked.length })}
            </Button>
            <Button variant="ghost" onClick={() => setPicked([])}>
              {t("purchases.arrived.cancel")}
            </Button>
            {arrive.isError && <Banner tone="negative" title={errorText(arrive.error, t)} />}
          </div>
        )}
        {query.isError ? (
          <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
        ) : !query.data ? (
          <Skeleton label={t("common.loading")} lines={6} />
        ) : query.data.items.length === 0 ? (
          group ? (
            <EmptyState title={t("purchases.emptyGroup")} />
          ) : (
            <EmptyState title={t("purchases.empty")} text={t("purchases.emptyText")} action={canManage ? <Button onClick={() => setAdding(true)}>{t("purchases.add")}</Button> : undefined} />
          )
        ) : (
          <>
            <DataTable caption={t("purchases.list")} columns={columns} rows={query.data.items} rowKey={(r) => r.id} />
            <Pagination
              page={query.data.page}
              pages={query.data.pages}
              total={query.data.total}
              size={size}
              onPage={(n) => void navigate({ to: "/purchases", search: (prev) => ({ ...prev, group, page: n > 1 ? n : undefined }), replace: true })}
              onSize={(n) => {
                setSize(n);
                void navigate({ to: "/purchases", search: (prev) => ({ ...prev, group, page: undefined }), replace: true });
              }}
            />
          </>
        )}
      </div>
      {adding && (
        <QuickPurchaseForm
          orgId={org.id}
          amounts={amounts}
          onClose={() => setAdding(false)}
          onSaved={(saved) => void navigate({ to: "/purchases/$purchaseId", params: { purchaseId: saved.purchase.id } })}
        />
      )}
    </section>
  );
}
