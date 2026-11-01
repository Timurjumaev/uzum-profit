import { describe, expect, it } from "vitest";

import { openingRow } from "../../test/opening";
import { draftOf, filled, invalid, openingBody, rowBody, rowKey } from "./model";

describe("boshlang'ich holat modeli", () => {
  it("qoralama: tahrir → saqlangan → Uzum taklifi", () => {
    const r = openingRow();
    expect(draftOf(r, undefined)).toEqual({ uzum: "120", own: null, price: null });
    const saved = openingRow({ uzum_qty: 100, own_qty: 5, prices: [{ valid_from: null, unit_cost: "12000.00" }] });
    expect(draftOf(saved, undefined)).toEqual({ uzum: "100", own: "5", price: "12000.00" });
    expect(draftOf(saved, { price: "13000" }).price).toBe("13000");
    expect(rowKey(openingRow({ item_id: null, sku_id: "sku-9" }))).toBe("sku:sku-9");
  });

  it("narxsiz yangi qator yuborilmaydi; narx kiritilsa — qoldiq bilan", () => {
    const r = openingRow();
    expect(rowBody(r, draftOf(r, undefined))).toBeNull();
    expect(rowBody(r, draftOf(r, { price: "12 000", own: "10" }))).toEqual({ item_id: "item-1", uzum_qty: 120, own_qty: 10, prices: [{ valid_from: null, unit_cost: "12000" }] });
    const lone = openingRow({ item_id: null, sku_id: "sku-9" });
    expect(rowBody(lone, draftOf(lone, { price: "5000" }))?.sku_id).toBe("sku-9");
  });

  it("saqlangan qator: o'zgarmasa yuborilmaydi, narx o'chirilsa — bo'sh narx bilan", () => {
    const r = openingRow({ uzum_qty: 100, own_qty: 0, prices: [{ valid_from: null, unit_cost: "12000.00" }] });
    expect(rowBody(r, draftOf(r, { price: "12000" }))).toBeNull();
    expect(rowBody(r, draftOf(r, { price: null }))?.prices).toEqual([]);
    expect(rowBody(r, draftOf(r, { uzum: "90" }))?.uzum_qty).toBe(90);
  });

  it("narx davrlari o'zgarmay qaytadi", () => {
    const prices = [
      { valid_from: null, unit_cost: "8000.00" },
      { valid_from: "2026-09-01", unit_cost: "10000.00" },
    ];
    const r = openingRow({ uzum_qty: 3, own_qty: 0, prices });
    expect(rowBody(r, draftOf(r, { uzum: "4" }))?.prices).toEqual(prices);
  });

  it("noto'g'ri qiymatlar", () => {
    expect(invalid({ uzum: "1,5", own: null, price: null })).toBe(true);
    expect(invalid({ uzum: "-1", own: null, price: null })).toBe(true);
    expect(invalid({ uzum: "2", own: null, price: "abc" })).toBe(true);
    expect(invalid({ uzum: "", own: "", price: "" })).toBe(false);
    expect(rowBody(openingRow(), { uzum: "x", own: null, price: "1" })).toBeNull();
  });

  it("tana va to'ldirilganlar soni", () => {
    const rows = [openingRow(), openingRow({ item_id: "item-2", lots_after: 1 }), openingRow({ item_id: "item-3" })];
    const edits = { "item-1": { price: "100" } };
    expect(openingBody("2026-11-01", rows, edits)).toEqual({ start_on: "2026-11-01", rows: [{ item_id: "item-1", uzum_qty: 120, own_qty: 0, prices: [{ valid_from: null, unit_cost: "100" }] }] });
    expect(filled(rows, edits)).toBe(2);
  });
});
