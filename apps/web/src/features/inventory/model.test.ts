import { describe, expect, it } from "vitest";

import { inventorySearch } from "../../app/search";
import { deadRow, stockRow } from "../../test/inventory";
import { canReorder, extraPlaces, orderByKind, reorderTitle, STATUS_TONE } from "./model";

describe("ombor yordamchilari", () => {
  it("joylar: nolmaslari tartib bilan; hammasi nol — bo'sh", () => {
    expect(extraPlaces(stockRow().locations)).toEqual([
      { place: "china", qty: 20 },
      { place: "road", qty: 30 },
      { place: "own", qty: 15 },
      { place: "defected", qty: 1 },
    ]);
    expect(extraPlaces(deadRow().locations)).toEqual([]);
  });

  it("buyurtma sanasi: kechikkan / sana / yo'q", () => {
    expect(orderByKind(stockRow())).toBe("now");
    expect(orderByKind(stockRow({ order_by: { day: "2026-11-20", overdue: false } }))).toBe("date");
    expect(orderByKind(deadRow())).toBe("none");
  });

  it("xarid yaratish: faqat tovar bor va tavsiya > 0", () => {
    expect(canReorder(stockRow())).toBe(true);
    expect(canReorder(stockRow({ item_id: null }))).toBe(false);
    expect(canReorder(stockRow({ reorder: { qty: 0, raw: "0", budget: null } }))).toBe(false);
    expect(canReorder(deadRow())).toBe(false);
  });

  it("qoralama xarid nomi: mahsulot yoki SKU nomi, 200 belgigacha", () => {
    expect(reorderTitle(stockRow(), "Qayta buyurtma")).toBe("Qayta buyurtma: Mashina");
    expect(reorderTitle(deadRow(), "Qayta buyurtma")).toBe("Qayta buyurtma: Chiroq LED");
    expect(reorderTitle(stockRow({ product_title: "x".repeat(500) }), "Q").length).toBe(200);
  });

  it("har holatning toni bor (ikon + matn bilan ko'rsatiladi)", () => {
    expect(Object.keys(STATUS_TONE)).toEqual(["critical", "high", "medium", "good", "dead"]);
  });

  it("URL: noto'g'ri holat va bo'sh qidiruv tashlanadi", () => {
    expect(inventorySearch({ status: "critical", q: "mashina" })).toEqual({ status: "critical", q: "mashina" });
    expect(inventorySearch({ status: "nope", q: "  " })).toEqual({});
    expect(inventorySearch({ q: "x".repeat(300) }).q).toHaveLength(100);
  });
});
