import { describe, expect, it } from "vitest";

import { changedDates, datesInOrder, GROUP_STAGES, isEstimated, nextStage, timelineStages, visibleFlags } from "./model";

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
});
