import { describe, expect, it } from "vitest";

import type { PickerRow } from "../../lib/api/types";
import { changedDates, datesInOrder, GROUP_STAGES, isEstimated, nextStage, pickerKey, pickerLabel, pickerOptions, timelineStages, visibleFlags } from "./model";

describe("xarid modeli", () => {
  it("keyingi bosqich: qoralama → buyurtma; yopilgan — yo'q", () => {
    expect(nextStage("draft")).toBe("ordered");
    expect(nextStage("shipped")).toBe("arrived");
    expect(nextStage("sent_to_uzum")).toBe("closed");
    expect(nextStage("closed")).toBeNull();
  });

  it("guruhlar: faol — qoralama va yopilgandan tashqari", () => {
    expect(GROUP_STAGES.active).not.toContain("draft");
    expect(GROUP_STAGES.active).not.toContain("closed");
    expect(GROUP_STAGES.transit).toEqual(["cn_warehouse", "shipped", "arrived"]);
  });

  it("taxminiy belgilar (F22): kurs CBU — taxminiy emas, faqat ma'lumot", () => {
    expect(isEstimated(["cbu_rate"])).toBe(false);
    expect(isEstimated(["cbu_rate", "not_received"])).toBe(true);
    expect(visibleFlags(["cbu_rate", "base_fallback", "x"])).toEqual(["base_fallback", "cbu_rate"]);
  });

  it("sanalar: faqat o'zgarganlari (bo'sh — null), tartib tekshiruvi", () => {
    expect(changedDates({ ordered: "2026-10-01", paid: "2026-10-02" }, { ordered: "2026-10-01", paid: "", shipped: "2026-10-12" })).toEqual({ paid: null, shipped: "2026-10-12" });
    expect(datesInOrder({ ordered: "2026-10-05", shipped: "2026-10-04" })).toBe(false);
    expect(datesInOrder({ ordered: "2026-10-05", paid: null, shipped: "2026-10-05" })).toBe(true);
  });

  it("Timeline: kunlar va kutilgan sana faqat joriy bosqichda", () => {
    const stages = timelineStages(
      [
        { stage: "ordered", state: "done", on: "2026-10-02", days: null, expected: null, delayed: false },
        { stage: "shipped", state: "current", on: "2026-10-12", days: 11, expected: "2026-10-28", delayed: true },
        { stage: "arrived", state: "upcoming", on: null, days: null, expected: null, delayed: false },
      ],
      (s) => s.toUpperCase(),
    );
    expect(stages).toEqual([
      { label: "ORDERED", state: "done", date: "2026-10-02", days: undefined, expected: undefined, delayed: false },
      { label: "SHIPPED", state: "current", date: "2026-10-12", days: 11, expected: "2026-10-28", delayed: true },
      { label: "ARRIVED", state: "upcoming", date: undefined, days: undefined, expected: undefined, delayed: false },
    ]);
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
