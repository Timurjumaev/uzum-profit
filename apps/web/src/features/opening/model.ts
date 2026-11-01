// Boshlang'ich holat (F41, ADR-033) — sof funksiyalar: qator qoralamasi, o'zgarganlar va API tanasi. Hisob serverda
// (tamoyil 4); bu yerda faqat kiritish holati. Qoralama — faqat foydalanuvchi o'zgartirgan maydonlar (`Edit`), qolgani
// serverdan: boshlash sanasi almashsa saqlanmagan qatorlarning Uzum qoldig'i taklifi o'zi yangilanadi.
import { parseNumber } from "../../lib/format";
import type { OpeningIn, OpeningRow, OpeningRowIn } from "../../lib/api/types";

export type Edit = { uzum?: string | null; own?: string | null; price?: string | null };
export type Draft = { uzum: string | null; own: string | null; price: string | null };

export const rowKey = (r: OpeningRow): string => r.item_id ?? `sku:${r.sku_id}`;

/** Bir nechta narx davri bo'lsa — bu sahifada faqat ko'rsatiladi (tahrir — keyin), saqlashda o'zgarmay qaytadi. */
export const hasPeriods = (r: OpeningRow): boolean => r.prices.length > 1;

export function saved(r: OpeningRow): Draft {
  return {
    uzum: r.uzum_qty === null ? null : String(r.uzum_qty),
    own: r.own_qty === null ? null : String(r.own_qty),
    price: r.prices.length === 1 ? r.prices[0].unit_cost : null,
  };
}

/** Ko'rinadigan qiymat: tahrir → saqlangan → taklif (Uzum qoldig'i). */
export function draftOf(r: OpeningRow, edit: Edit | undefined): Draft {
  const s = saved(r);
  const base: Draft = { uzum: s.uzum ?? (r.uzum_suggested === null ? null : String(r.uzum_suggested)), own: s.own, price: s.price };
  return { ...base, ...edit };
}

const qty = (v: string | null): number | null => {
  if (v === null || v.trim() === "") return 0;
  const n = parseNumber(v);
  return n !== null && Number.isInteger(Number(n)) && Number(n) >= 0 ? Number(n) : null;
};

const price = (v: string | null): string | null | undefined => {
  if (v === null || v.trim() === "") return null; // narxsiz
  const n = parseNumber(v);
  return n !== null && Number(n) >= 0 ? n : undefined; // undefined — noto'g'ri
};

export function invalid(d: Draft): boolean {
  return qty(d.uzum) === null || qty(d.own) === null || price(d.price) === undefined;
}

const isSaved = (r: OpeningRow): boolean => r.prices.length > 0 || r.uzum_qty !== null;
const samePrices = (a: OpeningRowIn["prices"], b: OpeningRow["prices"]): boolean =>
  (a ?? []).length === b.length && (a ?? []).every((x, i) => (x.valid_from ?? null) === b[i].valid_from && Number(x.unit_cost) === Number(b[i].unit_cost));

/** Yuboriladigan qator: avval saqlangan va o'zgargan yoki yangi va narx kiritilgan (narxsiz yangi qator yuborilmaydi —
 *  tovarsiz SKU uchun keraksiz tovar yaratilmasin). Noto'g'ri qiymat — `null`. */
export function rowBody(r: OpeningRow, d: Draft): OpeningRowIn | null {
  if (invalid(d)) return null;
  const p = price(d.price) ?? null;
  const body: OpeningRowIn = {
    ...(r.item_id ? { item_id: r.item_id } : { sku_id: r.sku_id }),
    uzum_qty: qty(d.uzum) ?? 0,
    own_qty: qty(d.own) ?? 0,
    prices: hasPeriods(r) ? r.prices : p === null ? [] : [{ valid_from: null, unit_cost: p }],
  };
  if (!isSaved(r)) return (body.prices ?? []).length > 0 ? body : null;
  const same = body.uzum_qty === r.uzum_qty && body.own_qty === (r.own_qty ?? 0) && samePrices(body.prices, r.prices);
  return same ? null : body;
}

export function openingBody(start: string | null, rows: OpeningRow[], edits: Record<string, Edit>): OpeningIn {
  const out: OpeningRowIn[] = [];
  for (const r of rows) {
    const body = rowBody(r, draftOf(r, edits[rowKey(r)]));
    if (body) out.push(body);
  }
  return { start_on: start, rows: out };
}

/** Narx kiritilgan (yoki partiyasi bor) qatorlar soni — "N / M tovar". */
export function filled(rows: OpeningRow[], edits: Record<string, Edit>): number {
  return rows.filter((r) => r.lots_after > 0 || hasPeriods(r) || (price(draftOf(r, edits[rowKey(r)]).price) ?? null) !== null).length;
}
