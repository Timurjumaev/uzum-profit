import { describe, expect, it } from "vitest";

import { openingRow } from "../../test/opening";
import { applyGroupPrice, draftOf, filled, groupPrice, groupRows, invalid, openingBody, rowBody, rowKey } from "./model";

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

describe("mahsulot guruhi (turlar)", () => {
  const a = openingRow({ item_id: null, sku_id: "v1", skus: ["ELONE-AIRGILOF-ВИШН-4"], product_id: "p1", product: "AirPods gʻilof" });
  const b = openingRow({ item_id: null, sku_id: "v2", skus: ["ELONE-AIRGILOF-ПАСТ-4"], product_id: "p1", product: "AirPods gʻilof" });
  const c = openingRow({ item_id: "i3", name: "Soat" });

  it("Uzum mahsuloti bo'yicha guruhlanadi, tartib saqlanadi", () => {
    const groups = groupRows([a, c, b]);
    expect(groups.map((g) => [g.title, g.rows.length])).toEqual([["AirPods gʻilof", 2], ["Soat", 1]]);
  });

  it("hammasiga bitta narx; keyin bittasini alohida o'zgartirish", () => {
    const [g] = groupRows([a, b]);
    expect(groupPrice(g!, {})).toBeNull();
    const edits = applyGroupPrice(g!, "15000", {});
    expect(groupPrice(g!, edits)).toBe("15000");
    expect(openingBody("2026-11-01", [a, b], edits).rows.map((r) => r.prices?.[0]?.unit_cost)).toEqual(["15000", "15000"]);
    const one = { ...edits, [rowKey(b)]: { ...edits[rowKey(b)], price: "17000" } };
    expect(groupPrice(g!, one)).toBeNull(); // har xil — guruh maydoni bo'sh
    expect(openingBody("2026-11-01", [a, b], one).rows.map((r) => r.prices?.[0]?.unit_cost)).toEqual(["15000", "17000"]);
  });

  it("narx davrlari bor tur guruh narxidan tashqarida", () => {
    const periods = openingRow({ item_id: "i9", product_id: "p1", uzum_qty: 1, own_qty: 0, prices: [{ valid_from: null, unit_cost: "1.00" }, { valid_from: "2026-09-01", unit_cost: "2.00" }] });
    const [g] = groupRows([a, periods]);
    const edits = applyGroupPrice(g!, "5", {});
    expect(edits[rowKey(periods)]).toBeUndefined();
    expect(groupPrice(g!, edits)).toBe("5");
  });
});
