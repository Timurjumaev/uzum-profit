// Ombor (M10, B4.7; 04 §7.4): tepada muzlagan pul (F29), yo'ldagi tovar va o'z omborimdagi dona; holat guruhlari
// (Kritik → Yaxshi, F26) URL'da; har qatorda joylar bo'yicha qoldiq, tezlik (F23), zaxira kunlari (F24), buyurtma sanasi
// va tavsiya miqdor (F27) — hammasi API'dan (`/inventory`), bu yerda qayta hisoblanmaydi (tamoyil 4). "Xarid yaratish" —
// tavsiya miqdor bilan qoralama xarid (narx va kargo keyin kiritiladi). Omborchi summalarni ko'rmaydi (null).
import { keepPreviousData, useInfiniteQuery, useMutation, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { createLine, createPurchase, currentOrg, deletePurchase, inventoryQuery, meQuery } from "../../app/query";
import { inventorySearch, STOCK_STATUSES } from "../../app/search";
import { Badge, Banner, Button, DataTable, EmptyState, ExportButton, FormulaPopover, Kpi, Skeleton, StatusPill, useToast, type Column, PageHelp } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { StockRow } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { MANAGE_ROLES } from "../purchases/Purchases";
import { canReorder, extraPlaces, orderByKind, reorderTitle, STATUS_TONE } from "./model";
import { StockMoveForm } from "./StockMoveForm";

const DEBOUNCE_MS = 250;

export function Inventory() {
  const { t } = useTranslation();
  const f = useFormat();
  const navigate = useNavigate();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  const search = inventorySearch(useSearch({ strict: false }) as Record<string, unknown>);
  const query = useInfiniteQuery({ ...inventoryQuery(org.id, filters.shops, search), placeholderData: keepPreviousData });
  const canManage = MANAGE_ROLES.includes(org.role);
  const [moving, setMoving] = useState<StockRow | null>(null);

  const update = (patch: Record<string, string | undefined>) => void navigate({ to: "/inventory", search: (prev) => ({ ...prev, ...patch }), replace: true });
  // Qidiruv: yozish tugagach (250 ms) URL'ga; URL boshqa joydan o'zgarsa maydon ham yangilanadi.
  const [draft, setDraft] = useState(search.q ?? "");
  const [seen, setSeen] = useState(search.q ?? "");
  if ((search.q ?? "") !== seen) {
    setSeen(search.q ?? "");
    setDraft(search.q ?? "");
  }
  useEffect(() => {
    if (draft === (search.q ?? "")) return;
    const id = setTimeout(() => update({ q: draft.trim() === "" ? undefined : draft }), DEBOUNCE_MS);
    return () => clearTimeout(id);
    // `update` har renderda yangi; faqat kiritilgan matn va URL qiymatiga bog'liq.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, search.q]);

  const first = query.data?.pages[0];
  const rows = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  const columns = useMemo(() => buildColumns({ t, f, canManage, onMove: setMoving }), [t, f, canManage]);

  if (query.isError && !first) {
    return (
      <section className="inventory">
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  }
  if (!first) {
    return (
      <section className="inventory" aria-busy>
        <h1 className="ui-visually-hidden">{t("nav.inventory")}</h1>
        <Skeleton label={t("common.loading")} lines={10} />
      </section>
    );
  }
  const { totals } = first;
  const counts = totals.statuses as Record<string, number>;
  const all = Object.values(counts).reduce((a, b) => a + b, 0);
  const amounts = totals.frozen_total !== null;
  const filtered = Boolean(search.q || search.status);
  return (
    <section className="inventory" aria-busy={query.isPlaceholderData || undefined}>
      <header className="inventory__head">
        <div className="page-title">
          <h1 className="h2">{t("inventory.title")}</h1>
          <PageHelp page="inventory" />
        </div>
        <p className="caption">{t("inventory.asOf", { date: f.date(first.as_of) })}</p>
      </header>

      <div className="inventory__kpis">
        {amounts && (
          <Kpi
            label={t("inventory.kpi.frozen")}
            value={f.money(totals.frozen_total!)}
            note={t("inventory.kpi.frozenNote", { units: f.number(totals.units.fbo + totals.units.fbs + totals.units.own + (totals.units.inbound ?? 0)) })}
            help={<Help id="f29" metric={t("inventory.kpi.frozen")} />}
          />
        )}
        <Kpi
          label={t("inventory.kpi.transit")}
          value={t("inventory.kpiUnits", { count: f.number(totals.units.china + totals.units.road) })}
          note={amounts ? f.money(Number(totals.frozen_money!.china) + Number(totals.frozen_money!.road)) : undefined}
          help={<Help id="f29" metric={t("inventory.kpi.transit")} />}
        />
        <Kpi label={t("inventory.kpi.own")} value={t("inventory.kpiUnits", { count: f.number(totals.units.own) })} note={amounts ? f.money(totals.frozen_money!.own) : undefined} />
        {amounts && (
          <Kpi
            label={t("inventory.kpi.days")}
            value={totals.average_days_to_sell === null ? "—" : t("inventory.days", { count: f.number(totals.average_days_to_sell, { digits: 0 }) })}
            help={<Help id="f29" metric={t("inventory.kpi.days")} />}
          />
        )}
      </div>

      {!amounts && (
        <Banner tone="info" title={t("inventory.noAmounts")}>
          {t("inventory.noAmountsText")}
        </Banner>
      )}
      {totals.uncosted > 0 && amounts && (
        <Banner tone="warning" title={t("inventory.uncosted", { count: totals.uncosted })}>
          {t("inventory.uncostedText")}
        </Banner>
      )}

      <div role="tablist" aria-label={t("inventory.groupsLabel")} className="orders-tabs">
        {([undefined, ...STOCK_STATUSES] as const).map((id) => (
          <button
            key={id ?? "all"}
            type="button"
            role="tab"
            aria-selected={search.status === id}
            aria-controls="inventory-panel"
            className={cx("orders-tab", search.status === id && "is-active")}
            onClick={() => update({ status: id })}
          >
            {t(`inventory.status.${id ?? "all"}`)} <span className="caption">{f.number(id ? (counts[id] ?? 0) : all)}</span>
          </button>
        ))}
      </div>
      <div className="inventory__bar" role="search">
        <input
          type="search"
          className="ui-input inventory__search"
          aria-label={t("inventory.search")}
          placeholder={t("inventory.searchPlaceholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <ExportButton orgId={org.id} table="inventory" query={{ shop: filters.shops, status: search.status, q: search.q }} />
      </div>

      <div id="inventory-panel" role="tabpanel" aria-label={t("inventory.list")} className="inventory__panel">
        {rows.length === 0 ? (
          filtered ? (
            <EmptyState
              title={t("inventory.emptyFiltered")}
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDraft("");
                    update({ q: undefined, status: undefined });
                  }}
                >
                  {t("inventory.resetFilters")}
                </Button>
              }
            />
          ) : (
            <EmptyState title={t("inventory.empty")} text={t("inventory.emptyText")} />
          )
        ) : (
          <DataTable caption={t("inventory.list")} columns={columns} rows={rows} rowKey={(r) => r.sku_id} density="comfortable" />
        )}
      </div>
      {query.hasNextPage && (
        <div className="inventory__more">
          <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {t("inventory.more")}
          </Button>
        </div>
      )}
      {moving && moving.item_id && <StockMoveForm orgId={org.id} itemId={moving.item_id} title={moving.product_title ?? moving.title ?? ""} onClose={() => setMoving(null)} />}
    </section>
  );
}

function Help({ id, metric }: { id: "f23" | "f24" | "f26" | "f27" | "f29"; metric: string }) {
  const { t } = useTranslation();
  return <FormulaPopover metric={metric} code={t(`inventory.formula.${id}.code`)} formula={t(`inventory.formula.${id}.formula`)} source={t(`inventory.formula.${id}.source`)} />;
}

// --- Ustunlar -----------------------------------------------------------------------------------------------------

type Ctx = { t: ReturnType<typeof useTranslation>["t"]; f: ReturnType<typeof useFormat>; canManage: boolean; onMove: (row: StockRow) => void };

function buildColumns({ t, f, canManage, onMove }: Ctx): Column<StockRow>[] {
  const dash = <span className="muted">—</span>;
  const columns: Column<StockRow>[] = [
    {
      key: "sku",
      header: t("inventory.col.sku"),
      render: (r) => (
        <span className="inventory-cell">
          <Link to="/products/$skuId" params={{ skuId: r.sku_id }} className="inventory-cell__name">
            {r.product_title ?? r.title ?? "—"}
          </Link>
          {r.product_title && r.title && <span className="caption">{r.title}</span>}
        </span>
      ),
    },
    {
      key: "status",
      header: t("inventory.col.status"),
      help: <Help id="f26" metric={t("inventory.col.status")} />,
      render: (r) => <StatusCell row={r} />,
    },
    {
      key: "stock",
      header: t("inventory.col.stock"),
      numeric: true,
      render: (r) => (
        <span className="inventory-cell inventory-cell--num">
          <strong>{f.number(r.stock)}</strong>
          <span className="caption">{t("inventory.fboFbs", { fbo: f.number(r.locations.fbo), fbs: f.number(r.locations.fbs) })}</span>
        </span>
      ),
    },
    { key: "places", header: t("inventory.col.places"), render: (r) => <Places row={r} /> },
    {
      key: "velocity",
      header: t("inventory.col.velocity"),
      numeric: true,
      help: <Help id="f23" metric={t("inventory.col.velocity")} />,
      render: (r) => (Number(r.velocity.value) > 0 ? f.number(r.velocity.value, { digits: 2 }) : dash),
    },
    {
      key: "days",
      header: t("inventory.col.days"),
      numeric: true,
      help: <Help id="f24" metric={t("inventory.col.days")} />,
      render: (r) => (r.days_of_stock === null ? dash : f.number(r.days_of_stock, { digits: 0 })),
    },
    {
      key: "orderBy",
      header: t("inventory.col.orderBy"),
      numeric: true,
      help: <Help id="f27" metric={t("inventory.col.orderBy")} />,
      render: (r) => <OrderBy row={r} />,
    },
    {
      key: "reorder",
      header: t("inventory.col.reorder"),
      help: <Help id="f27" metric={t("inventory.col.reorder")} />,
      numeric: true,
      render: (r) => <Reorder row={r} />,
    },
    {
      key: "value",
      header: t("inventory.col.value"),
      help: <Help id="f29" metric={t("inventory.col.value")} />,
      numeric: true,
      render: (r) => (r.stock_value === null ? dash : f.money(r.stock_value, { unit: false })),
    },
    {
      key: "actions",
      header: t("inventory.col.actions"),
      render: (r) => (canManage ? <RowActions row={r} onMove={() => onMove(r)} /> : null),
    },
  ];
  return columns;
}

function StatusCell({ row }: { row: StockRow }) {
  const { t } = useTranslation();
  if (!row.status) return <span className="muted" title={row.lead_time ? undefined : t("inventory.noLeadHint")}>—</span>;
  return (
    <span className="inventory-cell">
      <StatusPill tone={STATUS_TONE[row.status]}>{t(`inventory.status.${row.status}`)}</StatusPill>
      {row.product_status && row.product_status !== row.status && <span className="caption">{t("inventory.productStatus", { status: t(`inventory.status.${row.product_status}`) })}</span>}
      {row.liquidity && <Badge tone="warning">{t(`inventory.liquidity.${row.liquidity as "illiquid" | "slow"}`)}</Badge>}
    </span>
  );
}

function Places({ row }: { row: StockRow }) {
  const { t } = useTranslation();
  const f = useFormat();
  const parts = extraPlaces(row.locations);
  if (parts.length === 0) return <span className="muted">—</span>;
  return (
    <ul className="inventory-places" aria-label={t("inventory.col.places")}>
      {parts.map(({ place, qty }) => (
        <li key={place}>
          {t(`inventory.place.${place}`)}: <strong>{f.number(qty)}</strong>
        </li>
      ))}
    </ul>
  );
}

function OrderBy({ row }: { row: StockRow }) {
  const { t } = useTranslation();
  const f = useFormat();
  const kind = orderByKind(row);
  if (kind === "none") return <span className="muted" title={t("inventory.noOrderHint")}>—</span>;
  if (kind === "now") return <StatusPill tone="negative">{t("inventory.orderNow")}</StatusPill>;
  return <>{f.date(row.order_by!.day)}</>;
}

function Reorder({ row }: { row: StockRow }) {
  const { t } = useTranslation();
  const f = useFormat();
  if (!row.reorder) return <span className="muted" title={t("inventory.noLeadHint")}>—</span>;
  const budget = row.reorder.budget;
  return (
    <span className="inventory-cell inventory-cell--num">
      <strong>{f.number(row.reorder.qty)}</strong>
      {budget && budget.length > 0 && row.reorder.qty > 0 && <span className="caption">{budget.map((b) => (b.currency === "UZS" ? f.money(b.amount) : f.currency(b.amount, b.currency))).join(" · ")}</span>}
    </span>
  );
}

function RowActions({ row, onMove }: { row: StockRow; onMove: () => void }): ReactNode {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { data: me } = useSuspenseQuery(meQuery);
  const orgId = currentOrg(me)!.id;
  // Qoralama xarid + bitta qator; qator yaratilmasa — qoralama qoldirilmaydi.
  const create = useMutation({
    mutationFn: async () => {
      const purchase = await createPurchase(orgId, { title: reorderTitle(row, t("inventory.reorderPrefix")) });
      const id = purchase.purchase.id;
      try {
        await createLine(orgId, id, { item_id: row.item_id!, ordered_qty: row.reorder!.qty });
      } catch (error) {
        await deletePurchase(orgId, id).catch(() => undefined);
        throw error;
      }
      return id;
    },
    onSuccess: async (id) => {
      await client.invalidateQueries({ queryKey: ["orgs", orgId, "purchases"] });
      toast.show(t("inventory.reorderCreated"), "positive");
      void navigate({ to: "/purchases/$purchaseId", params: { purchaseId: id } });
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  return (
    <span className="inventory-actions">
      {canReorder(row) && (
        <Button size="sm" variant="secondary" loading={create.isPending} onClick={() => create.mutate()}>
          {t("inventory.reorder")}
        </Button>
      )}
      {row.item_id && (
        <Button size="sm" variant="ghost" onClick={onMove}>
          {t("inventory.writeoff")}
        </Button>
      )}
    </span>
  );
}
