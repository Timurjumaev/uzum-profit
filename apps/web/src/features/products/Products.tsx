// Mahsulotlar (M6, B4.3): SKU jadvali — qidiruv (lotin/kirill), filtrlar, saralash (URL'da), ustun tanlash va saqlangan
// ko'rinishlar (brauzerda), 500+ qatorda virtual skroll. Har raqam API'dan (`/skus`); har ustunda "?" formulasi (F-raqam).
// Bonus davri (ADR-031) bo'lsa — ma'lumot banneri va "Me'yoriy foyda/dona" ustuni: haqiqiy foyda o'zgarmaydi.
// Jadvaldan tashqari qismlar (SKUga bog'lanmagan sotuvlar, taqsimlanmagan xarajat) alohida — qatorlar + ular = P&L jami.
import { keepPreviousData, useInfiniteQuery, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { Columns3, Save } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, meQuery, shopsQuery, skusQuery, syncQuery } from "../../app/query";
import { DEFAULT_PRODUCT_SORT, parseSort, productsSearch, PRODUCT_ABC, PRODUCT_LABELS, type ProductSort } from "../../app/search";
import { Badge, Banner, Button, DataTable, EmptyState, FormulaPopover, Popover, ProductThumb, Select, Skeleton, StatusPill, type Column } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import type { SkuRow, Skus } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { syncSummary } from "../../lib/sync";
import { useKindLabel } from "../pnl/Waivers";
import {
  COLUMN_FORMULA,
  COLUMN_IDS,
  DEFAULT_COLUMNS,
  LABEL_TONE,
  loadColumns,
  loadViews,
  nextSort,
  REQUIRED_COLUMNS,
  saveColumns,
  saveViews,
  SORT_KEY,
  sortParam,
  upsertView,
  type ColumnId,
  type SavedView,
} from "./model";

const DEBOUNCE_MS = 250;

export function Products() {
  const { t } = useTranslation();
  const f = useFormat();
  const navigate = useNavigate();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  const search = productsSearch(useSearch({ strict: false }) as Record<string, unknown>);
  const sort = parseSort(search.sort);
  const params = useMemo(
    () => ({ shops: filters.shops, start: filters.range.start, end: filters.range.end }),
    [filters.shops, filters.range.start, filters.range.end],
  );
  const list = { q: search.q, sort: search.sort, label: search.label, abc: search.abc };
  const query = useInfiniteQuery({ ...skusQuery(org.id, params, list), placeholderData: keepPreviousData });
  const sync = useQuery(syncQuery(org.id));
  const shops = useQuery(shopsQuery(org.id));

  const update = (patch: Record<string, string | undefined>) =>
    void navigate({ to: "/products", search: (prev) => ({ ...prev, ...patch }), replace: true });

  // Qidiruv: yozish tugagach (250 ms) URL'ga; URL boshqa joydan o'zgarsa (ko'rinish tanlandi) maydon ham yangilanadi.
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

  const [stored, setStored] = useState<ColumnId[] | null>(() => loadColumns(org.id));
  const [views, setViews] = useState<SavedView[]>(() => loadViews(org.id));
  const first = query.data?.pages[0];
  const rows = useMemo(() => query.data?.pages.flatMap((p) => p.items) ?? [], [query.data]);
  const hasBonus = (first?.bonus.waivers.length ?? 0) > 0;
  // Foydalanuvchi ustun tanlamagan va bonus davri bor — me'yoriy foyda ustuni o'zi ko'rinadi (ADR-031).
  const chosen: readonly ColumnId[] = stored ?? (hasBonus ? DEFAULT_COLUMNS.flatMap((c) => (c === "profit" ? [c, "normative" as const] : [c])) : DEFAULT_COLUMNS);
  const setColumns = (next: ColumnId[]) => {
    setStored(next);
    saveColumns(org.id, next);
  };

  const shopName = (id: string) => {
    const shop = shops.data?.find((s) => s.id === id);
    return shop ? (shop.alias ?? shop.name) : id.slice(0, 8);
  };
  const columns = useMemo(() => buildColumns(chosen, { t, f, shopName }), [chosen, t, f, shops.data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (query.isError && !first) {
    return (
      <section className="products">
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      </section>
    );
  }
  if (!first) {
    return (
      <section className="products" aria-busy>
        <h1 className="ui-visually-hidden">{t("nav.products")}</h1>
        <Skeleton label={t("common.loading")} lines={10} />
      </section>
    );
  }

  const summary = sync.data ? syncSummary(sync.data) : null;
  const emptyState = summary?.state === "never" ? "never" : summary && summary.state !== "fresh" ? "partial" : "none";
  const filtered = Boolean(search.q || search.label || search.abc);
  const apply = (view: SavedView) => {
    setColumns(view.columns);
    update({ q: view.q, sort: view.sort, label: view.label, abc: view.abc });
  };
  const saveView = (name: string) => {
    const next = upsertView(views, { name, columns: [...chosen], q: search.q, sort: search.sort, label: search.label, abc: search.abc });
    setViews(next);
    saveViews(org.id, next);
  };
  const removeView = (name: string) => {
    const next = views.filter((v) => v.name !== name);
    setViews(next);
    saveViews(org.id, next);
  };
  const { period } = first.meta;
  return (
    <section className="products" aria-busy={query.isPlaceholderData || undefined}>
      <header className="products__head">
        <h1 className="h2">{t("products.title", { period: f.period(period.start, period.end) })}</h1>
        <p className="caption">{t("products.count", { shown: f.number(rows.length), total: f.number(first.total) })}</p>
      </header>
      {hasBonus && <BonusNote data={first} />}

      <div className="products__bar" role="search">
        <input
          type="search"
          className="ui-input products__search"
          aria-label={t("products.search")}
          placeholder={t("products.searchPlaceholder")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Select
          label={t("products.filter.label")}
          value={search.label ?? ""}
          onValueChange={(v) => update({ label: v || undefined })}
          options={[{ value: "", label: t("products.filter.all") }, ...PRODUCT_LABELS.map((l) => ({ value: l, label: t(`products.label.${l}`) }))]}
        />
        <Select
          label={t("products.filter.abc")}
          value={search.abc ?? ""}
          onValueChange={(v) => update({ abc: v || undefined })}
          options={[{ value: "", label: t("products.filter.all") }, ...PRODUCT_ABC.map((c) => ({ value: c, label: c }))]}
        />
        <ColumnsMenu chosen={chosen} onChange={setColumns} />
        <ViewsMenu views={views} onApply={apply} onSave={saveView} onRemove={removeView} />
      </div>

      {rows.length === 0 ? (
        filtered ? (
          <EmptyState
            title={t("products.emptyFiltered")}
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setDraft("");
                  update({ q: undefined, label: undefined, abc: undefined });
                }}
              >
                {t("products.resetFilters")}
              </Button>
            }
          />
        ) : (
          <EmptyState title={t(`home.empty.${emptyState}`)} text={t(`home.empty.${emptyState}Text`)} />
        )
      ) : (
        <DataTable
          caption={t("products.caption")}
          columns={columns}
          rows={rows}
          rowKey={(r) => r.sku_id}
          density="compact"
          sort={{ key: sort.key, desc: sort.desc }}
          onSort={(key) => {
            const next = sortParam(nextSort(sort, key as ProductSort));
            update({ sort: next === sortParam(DEFAULT_PRODUCT_SORT) ? undefined : next });
          }}
        />
      )}
      {query.hasNextPage && (
        <div className="products__more">
          <Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {t("products.more")}
          </Button>
        </div>
      )}
      <Outside data={first} />
    </section>
  );
}

// --- Ustunlar -----------------------------------------------------------------------------------------------------

type Ctx = { t: ReturnType<typeof useTranslation>["t"]; f: ReturnType<typeof useFormat>; shopName: (id: string) => string };

const cell = (value: string | null, render: (v: string) => ReactNode) => (value === null ? <span className="muted">—</span> : render(value));

function tone(value: string | null): string | undefined {
  return value !== null && value.startsWith("-") && !/^-0+(\.0*)?$/.test(value) ? "ui-text--negative" : undefined;
}

function buildColumns(ids: readonly ColumnId[], { t, f, shopName }: Ctx): Column<SkuRow>[] {
  const money = (v: string | null) => cell(v, (x) => <span className={tone(x)}>{f.money(x, { unit: false })}</span>);
  const percent = (v: string | null) => cell(v, (x) => f.percent(x));
  const header = (id: ColumnId) => t(`products.col.${id}`);
  const help = (id: ColumnId): ReactNode => {
    const key = COLUMN_FORMULA[id];
    return key ? (
      <FormulaPopover
        metric={header(id)}
        code={t(`home.formula.${key}.code`)}
        formula={t(`home.formula.${key}.formula`)}
        source={t(`home.formula.${key}.source`)}
        estimatedReason={key === "normative" ? t("home.formula.normative.estimated") : undefined}
      />
    ) : undefined;
  };
  const all: Record<ColumnId, (r: SkuRow) => ReactNode> = {
    product: (r) => <ProductCell row={r} />,
    shop: (r) => shopName(r.shop_id),
    units: (r) => f.number(r.units),
    revenue: (r) => f.money(r.revenue, { unit: false }),
    avg_price: (r) => money(r.avg_price),
    commission: (r) => percent(r.commission_share),
    logistics: (r) => money(r.logistics_per_unit),
    cogs: (r) => money(r.cogs_per_unit),
    ads: (r) => money(r.ads_per_unit),
    profit: (r) => money(r.profit_per_unit),
    normative: (r) => <NormativeCell row={r} />,
    net: (r) => money(r.net_profit),
    margin: (r) => percent(r.margin),
    roi: (r) => percent(r.roi),
    returns: (r) => percent(r.return_share),
    cancel: (r) => percent(r.cancel_share),
    direct: (r) => money(r.expenses_direct),
    allocated: (r) => money(r.expenses_allocated),
    stock: (r) => f.number(r.stock),
    days: (r) => cell(r.days_of_stock, (x) => f.number(x, { digits: 0 })),
    abc: (r) => <Badge>{r.abc}</Badge>,
    label: (r) => <StatusPill tone={LABEL_TONE[r.label]}>{t(`products.label.${r.label}`)}</StatusPill>,
  };
  return COLUMN_IDS.filter((id) => ids.includes(id)).map((id) => ({
    key: id,
    header: header(id),
    numeric: !["product", "shop", "abc", "label"].includes(id),
    render: all[id],
    sortKey: SORT_KEY[id],
    help: help(id),
  }));
}

function ProductCell({ row }: { row: SkuRow }) {
  const { t } = useTranslation();
  const name = row.title ?? row.product_title ?? t("home.sku.unnamed");
  return (
    <span className="products-cell">
      <ProductThumb src={row.image_url} name={name} size={32} />
      <span className="products-cell__text">
        <Link
          to="/products/$skuId"
          params={{ skuId: row.sku_id }}
          search={(prev) => ({ shop: prev.shop, from: prev.from, to: prev.to, cmp: prev.cmp })}
          className="products-cell__name"
        >
          {name}
        </Link>
        {(row.article || row.product_title) && <span className="caption">{[row.article, row.title ? row.product_title : null].filter(Boolean).join(" · ")}</span>}
      </span>
    </span>
  );
}

/** F40: bonus SKU'ga ta'sir qilmagan bo'lsa haqiqiy foyda; ta'sir qilgan bo'lsa me'yoriy; baho yo'q — taxmin emas, "baho yo'q". */
function NormativeCell({ row }: { row: SkuRow }) {
  const { t } = useTranslation();
  const f = useFormat();
  if (row.normative_state === "unavailable") return <span className="muted">{t("products.normative.unavailable")}</span>;
  if (row.normative_profit_per_unit === null) return <span className="muted">—</span>;
  return (
    <span className={cx(tone(row.normative_profit_per_unit))} title={row.normative_state === "adjusted" ? t("products.normative.adjusted") : undefined}>
      {f.money(row.normative_profit_per_unit, { unit: false })}
      {row.normative_state === "adjusted" && <Badge tone="info">{t("products.normative.badge")}</Badge>}
    </span>
  );
}

// --- Bonus va jadvaldan tashqari ---------------------------------------------------------------------------------

function BonusNote({ data }: { data: Skus }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const gaps = data.bonus.unestimated_kinds;
  return (
    <Banner tone="info" title={t("products.bonus.title")}>
      {t("products.bonus.text")}
      {gaps.length > 0 && <> {t("products.bonus.unestimated", { kinds: gaps.map(kindLabel).join(", ") })}</>}
    </Banner>
  );
}

/** ADR-026: SKUga bog'lanmagan sotuvlar va sotuvsiz kun xarajati jadval qatori emas — qatorlar + ular = P&L jami. */
function Outside({ data }: { data: Skus }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { unlinked, unallocated } = data;
  if (unlinked.lines === 0 && Number(unallocated.net_profit) === 0 && Number(unlinked.net_profit) === 0) return null;
  return (
    <section className="products-outside" aria-label={t("products.outside.title")}>
      <h2 className="h3">{t("products.outside.title")}</h2>
      <p className="caption">{t("products.outside.note")}</p>
      <dl>
        <div>
          <dt>{t("pnl.views.unlinked")}</dt>
          <dd>
            {t("products.outside.unlinked", { units: f.number(unlinked.units), revenue: f.money(unlinked.revenue), profit: f.money(unlinked.net_profit) })}
          </dd>
        </div>
        <div>
          <dt>{t("pnl.views.unallocated")}</dt>
          <dd>{t("products.outside.unallocated", { profit: f.money(unallocated.net_profit) })}</dd>
        </div>
      </dl>
    </section>
  );
}

// --- Ustun tanlash va ko'rinishlar --------------------------------------------------------------------------------

function ColumnsMenu({ chosen, onChange }: { chosen: readonly ColumnId[]; onChange: (next: ColumnId[]) => void }) {
  const { t } = useTranslation();
  const toggle = (id: ColumnId) =>
    onChange(COLUMN_IDS.filter((c) => (c === id ? !chosen.includes(c) : chosen.includes(c) || REQUIRED_COLUMNS.includes(c))));
  return (
    <Popover trigger={<><Columns3 size={16} aria-hidden /> {t("products.columns.title")}</>} label={t("products.columns.title")} align="end">
      <fieldset className="products-menu">
        <legend className="label">{t("products.columns.title")}</legend>
        {COLUMN_IDS.map((id) => (
          <label key={id} className="products-menu__item">
            <input type="checkbox" checked={chosen.includes(id)} disabled={REQUIRED_COLUMNS.includes(id)} onChange={() => toggle(id)} />
            {t(`products.col.${id}`)}
          </label>
        ))}
        <Button variant="ghost" size="sm" onClick={() => onChange([...DEFAULT_COLUMNS])}>
          {t("products.columns.reset")}
        </Button>
      </fieldset>
    </Popover>
  );
}

function ViewsMenu({ views, onApply, onSave, onRemove }: { views: SavedView[]; onApply: (v: SavedView) => void; onSave: (name: string) => void; onRemove: (name: string) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  return (
    <Popover trigger={<><Save size={16} aria-hidden /> {t("products.views.title")}</>} label={t("products.views.title")} align="end">
      {(close) => (
        <div className="products-menu">
          <p className="label">{t("products.views.title")}</p>
          {views.length === 0 && <p className="caption">{t("products.views.empty")}</p>}
          <ul className="products-views">
            {views.map((v) => (
              <li key={v.name}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    onApply(v);
                    close();
                  }}
                >
                  {v.name}
                </Button>
                <Button variant="ghost" size="sm" aria-label={t("products.views.remove", { name: v.name })} onClick={() => onRemove(v.name)}>
                  ×
                </Button>
              </li>
            ))}
          </ul>
          <form
            className="products-views__save"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim() === "") return;
              onSave(name.trim());
              setName("");
            }}
          >
            <input className="ui-input" aria-label={t("products.views.name")} placeholder={t("products.views.name")} value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
            <Button type="submit" variant="secondary" size="sm" disabled={name.trim() === ""}>
              {t("products.views.save")}
            </Button>
          </form>
        </div>
      )}
    </Popover>
  );
}
