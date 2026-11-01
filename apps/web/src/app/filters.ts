// Umumiy filtrlar (04 §5, §7.1; 03 §9: "filtrlar va davr — URL'da"): do'kon(lar), davr, solishtirish. Topbar ularni
// o'zgartiradi, sahifalar URL'dan o'qiydi — shu sababli bir sahifadan ikkinchisiga o'tganda saqlanadi va havola bilan
// ulashiladi. URL faqat foydalanuvchi tanlaganini saqlaydi; tanlanmagan davr — "Shu oy" (har kuni yangilanadi).
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback, useMemo } from "react";

import type { CompareMode } from "../components/ui";
import { isIsoDate, presetRange, todayTashkent, type IsoDate, type Range } from "../lib/dates";

export type FilterSearch = { shop?: string[]; from?: IsoDate; to?: IsoDate; cmp?: Exclude<CompareMode, "none"> };

export type Filters = {
  /** Tanlangan do'konlar; bo'sh — hammasi. */
  shops: string[];
  range: Range;
  compare: CompareMode;
};

/** Topbar filtrlari: sahifa qaysilarini haqiqatan ishlatadi (ishlatmaydigani ko'rsatilmaydi — aldamasin). */
export type FilterKind = "shop" | "range" | "compare";

const PAGE_FILTERS: ReadonlyArray<readonly [RegExp, readonly FilterKind[]]> = [
  [/^\/(pnl\/?)?$/, ["shop", "range", "compare"]], // bosh sahifa, Foyda va zarar
  [/^\/(products|orders|expenses)(\/|$)/, ["shop", "range"]],
  [/^\/(inventory|opening)\/?$/, ["shop"]], // qoldiq — davrsiz (bugungi holat)
];

/** Sahifa ishlatadigan filtrlar; ro'yxatda yo'q sahifa (Xaridlar, Sozlamalar, holat ...) — butun tashkilot bo'yicha. */
export function pageFilters(pathname: string): ReadonlySet<FilterKind> {
  return new Set(PAGE_FILTERS.find(([re]) => re.test(pathname))?.[1] ?? []);
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** URL → tiplangan qidiruv: noto'g'ri qiymat jim tashlanadi (ruxsatsiz yoki eskirgan havola sahifani buzmasin). */
export function filterSearch(search: Record<string, unknown>): FilterSearch {
  const out: FilterSearch = {};
  const raw = Array.isArray(search.shop) ? search.shop : search.shop === undefined ? [] : [search.shop];
  const shops = [...new Set(raw.filter((id): id is string => typeof id === "string" && UUID.test(id)))];
  if (shops.length > 0) out.shop = shops;
  if (isIsoDate(search.from) && isIsoDate(search.to) && search.from <= search.to) {
    out.from = search.from;
    out.to = search.to;
  }
  if (search.cmp === "previous" || search.cmp === "lastYear") out.cmp = search.cmp;
  return out;
}

export function resolveFilters(search: FilterSearch, today: IsoDate = todayTashkent()): Filters {
  return {
    shops: search.shop ?? [],
    range: search.from && search.to ? { start: search.from, end: search.to } : presetRange("thisMonth", today),
    compare: search.cmp ?? "none",
  };
}

/** Filtrlar → URL: bo'sh narsa yozilmaydi. */
export function toSearch(filters: Partial<Filters>): FilterSearch {
  const out: FilterSearch = {};
  if (filters.shops?.length) out.shop = filters.shops;
  if (filters.range) {
    out.from = filters.range.start;
    out.to = filters.range.end;
  }
  if (filters.compare && filters.compare !== "none") out.cmp = filters.compare;
  return out;
}

/** Joriy sahifaning filtrlari va ularni o'zgartiruvchi (sahifada qoladi, tarixga yangi yozuv qo'shadi). */
export function useFilters(): { filters: Filters; setFilters: (patch: Partial<Filters>) => void } {
  const search = useSearch({ strict: false }) as Record<string, unknown>;
  const navigate = useNavigate();
  const parsed = useMemo(() => filterSearch(search), [search]);
  const filters = useMemo(() => resolveFilters(parsed), [parsed]);
  const setFilters = useCallback(
    (patch: Partial<Filters>) => {
      const next = { ...resolveFilters(parsed), ...patch };
      // Tanlanmagan davr URL'da yo'q bo'lib qoladi, o'zgartirilmasa shunday qoladi.
      const range = patch.range ?? (parsed.from && parsed.to ? next.range : undefined);
      void navigate({
        to: ".",
        search: (prev: Record<string, unknown>) => ({
          ...prev,
          shop: undefined,
          from: undefined,
          to: undefined,
          cmp: undefined,
          ...toSearch({ shops: next.shops, range, compare: next.compare }),
        }),
      });
    },
    [navigate, parsed],
  );
  return { filters, setFilters };
}
