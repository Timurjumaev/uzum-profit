// Sahifalash (ADR-054, 04 §5): "20 / 50 / 100 tadan" tanlovi, "1–50 / 340 ta", sahifa raqamlari (oldingi/keyingi bilan).
// Tanlangan o'lcham brauzerda eslanadi (standart 50); sahifa raqami URL'da — sahifa komponentida. Bir sahifaga
// sig'adigan ro'yxatda (jami ≤ eng kichik o'lcham) hech narsa chizilmaydi.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useFormat } from "../../lib/i18n";
import { Button } from "./Button";
import { cx } from "./cx";
import { Select } from "./Select";

export const PAGE_SIZES = [20, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 50;
const STORAGE_KEY = "sellermax.pageSize";

/** Eslab qolingan sahifa o'lchami; brauzer xotirasi yo'q yoki qiymat noto'g'ri bo'lsa — standart. */
export function loadPageSize(): number {
  try {
    const n = Number(localStorage.getItem(STORAGE_KEY));
    return (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE;
  } catch {
    return DEFAULT_PAGE_SIZE;
  }
}

export function savePageSize(size: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(size));
  } catch {
    /* xotira yopiq (maxfiy oyna) — tanlov faqat shu sessiyada */
  }
}

/** Sahifa o'lchami holati: boshlang'ich qiymat — brauzerda eslangani; o'zgarsa eslab qolinadi. */
export function usePageSize(): [number, (size: number) => void] {
  const [size, setSize] = useState(loadPageSize);
  return [
    size,
    (next) => {
      savePageSize(next);
      setSize(next);
    },
  ];
}

/** Ko'rinadigan sahifa raqamlari: birinchi, oxirgi, joriy va qo'shnilari; orasi — `null` (ko'p nuqta). */
export function pageItems(page: number, pages: number): (number | null)[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const keep = new Set([1, pages, page - 1, page, page + 1]);
  if (page <= 3) [2, 3, 4].forEach((n) => keep.add(n));
  if (page >= pages - 2) [pages - 3, pages - 2, pages - 1].forEach((n) => keep.add(n));
  const nums = [...keep].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  nums.forEach((n, i) => {
    if (i > 0 && n - nums[i - 1]! > 1) out.push(null);
    out.push(n);
  });
  return out;
}

export type PaginationProps = {
  page: number;
  pages: number;
  total: number;
  size: number;
  onPage: (page: number) => void;
  onSize: (size: number) => void;
  className?: string;
};

export function Pagination({ page, pages, total, size, onPage, onSize, className }: PaginationProps) {
  const { t } = useTranslation();
  const f = useFormat();
  if (total <= PAGE_SIZES[0]) return null;
  const from = (page - 1) * size + 1;
  const to = Math.min(total, page * size);
  return (
    <div className={cx("ui-pagination", className)}>
      <p className="caption ui-pagination__range" aria-live="polite">
        {t("ui.pagination.range", { from: f.number(from), to: f.number(to), total: f.number(total) })}
      </p>
      {pages > 1 && (
        <nav className="ui-pagination__pages" aria-label={t("ui.pagination.label")}>
          <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t("ui.pagination.prev")}>
            <ChevronLeft size={16} aria-hidden />
          </Button>
          {pageItems(page, pages).map((n, i) =>
            n === null ? (
              <span key={`gap${i}`} className="ui-pagination__gap" aria-hidden>
                …
              </span>
            ) : (
              <Button
                key={n}
                variant={n === page ? "secondary" : "ghost"}
                size="sm"
                aria-current={n === page ? "page" : undefined}
                aria-label={t("ui.pagination.page", { n: f.number(n) })}
                onClick={() => (n === page ? undefined : onPage(n))}
              >
                {f.number(n)}
              </Button>
            ),
          )}
          <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t("ui.pagination.next")}>
            <ChevronRight size={16} aria-hidden />
          </Button>
        </nav>
      )}
      <Select
        label={t("ui.pagination.size")}
        value={String(size)}
        onValueChange={(v) => onSize(Number(v))}
        options={PAGE_SIZES.map((n) => ({ value: String(n), label: t("ui.pagination.sizeOption", { n }) }))}
      />
    </div>
  );
}
