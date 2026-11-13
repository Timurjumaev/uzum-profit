import { describe, expect, it } from "vitest";

import type { PickerRow } from "../../lib/api/types";
import { GROUP_STATES, isEstimated, isInfoFlag, pickerKey, pickerLabel, pathStages, pickerOptions, visibleFlags } from "./model";

describe("xarid modeli", () => {
  it("guruhlar — uch holat (ADR-061 §1)", () => {
    expect(GROUP_STATES).toEqual({ in_transit: ["in_transit"], in_stock: ["in_stock"], at_uzum: ["at_uzum"] });
  });

  it("uch nuqtali yo'l → Timeline: kunlar faqat joriy nuqtada", () => {
    const stages = pathStages(
      [
        { state: "in_transit", mark: "current", on: "2026-10-02", days: 11, expected: "2026-10-28", delayed: false },
        { state: "in_stock", mark: "upcoming", on: null, days: null, expected: null, delayed: false },
      ],
      (s) => s,
    );
    expect(stages).toEqual([
      { label: "in_transit", state: "current", date: "2026-10-02", days: 11, expected: "2026-10-28", delayed: false },
      { label: "in_stock", state: "upcoming", date: undefined, days: undefined, expected: undefined, delayed: false },
    ]);
  });

  it("ma'lumot belgilari: qator summalari yo'q — taxminiy emas", () => {
    expect(isInfoFlag("no_line_sums")).toBe(true);
    expect(isEstimated(["no_line_sums"])).toBe(false);
    expect(visibleFlags(["no_line_sums", "cargo_missing", "cbu_rate"])).toEqual(["cargo_missing", "no_line_sums", "cbu_rate"]);
  });

  it("taxminiy belgilar (F22): kurs CBU — taxminiy emas, faqat ma'lumot", () => {
    expect(isEstimated(["cbu_rate"])).toBe(false);
    expect(isEstimated(["cbu_rate", "not_received"])).toBe(true);
    expect(visibleFlags(["cbu_rate", "base_fallback", "x"])).toEqual(["base_fallback", "cbu_rate"]);
  });

  it("SKU tanlovi: hech narsa yashirilmaydi, hint — variant, do'kon, qoldiq, holat, takror belgisi", () => {
    const row = (over: Partial<PickerRow>): PickerRow => ({ sku_id: null, item_id: null, item_name: null, shop_id: null, shop: null, product_title: null, title: null, article: null, image_url: null, stock: null, sold: null, status: null, ...over });
    const rows = [
      row({ sku_id: "s1", item_id: "i1", product_title: "Koʻylak", title: "Koʻylak-Qora-M", shop: "byDurii", stock: 5, status: "ACTIVE", article: "KY-1" }),
      row({ sku_id: "s2", title: "Arxiv", stock: 0, status: "ARCHIVED" }),
      row({ item_id: "i9", item_name: "Eski tovar" }),
    ];
    const t = (key: string, o?: Record<string, unknown>) => (o?.count !== undefined ? `${key}:${String(o.count)}` : key);
    const options = pickerOptions(rows, t, new Set(["i1"]));
    expect(options).toHaveLength(3);
    expect(options.map((o) => o.value)).toEqual(["sku:s1", "sku:s2", "item:i9"]);
    expect(options[0]).toMatchObject({ label: "Koʻylak", hint: "Koʻylak-Qora-M · byDurii · purchases.lines.stock:5 · ACTIVE · purchases.lines.inPurchase" });
    expect(options[0]!.keywords).toContain("KY-1");
    expect(options[1]).toMatchObject({ label: "Arxiv", hint: "purchases.lines.noStock · ARCHIVED" });
    expect(options[2]).toMatchObject({ label: "Eski tovar", hint: "purchases.lines.withoutSku" });
    expect(pickerKey(rows[2]!)).toBe("item:i9");
    expect(pickerLabel(row({}))).toBe("—");
  });
});
