import { describe, expect, it } from "vitest";

import { settingsData, TAX_1, TAX_2 } from "../../test/settings";
import { activeTax, coverDraft, inventoryBody, inventoryState, leadDraft, taxBody, taxDraft, taxValid, termsDays } from "./model";

const today = "2026-10-31";

describe("soliq profili shakli", () => {
  it("qatordan forma: ortiqcha nollar tashlanadi; yangi — aylanma, bo'sh stavka", () => {
    const p = settingsData().tax_profiles[0]!;
    expect(taxDraft(p, today)).toEqual({ valid_from: "2026-07-01", regime: "turnover", rate: "4", base: "payout", vat: null, profit: null });
    expect(taxDraft(null, today)).toMatchObject({ valid_from: today, regime: "turnover", rate: null });
    expect(taxDraft({ ...p, rate_pct: "1.500" }, today).rate).toBe("1.5");
  });

  it("tekshiruv: aylanmada stavka > 0 va ≤ 100; QQS/foyda 0–100; agent va 'yo'q' — doim to'g'ri", () => {
    const d = taxDraft(null, today);
    expect(taxValid(d)).toBe(false);
    expect(taxValid({ ...d, rate: "0" })).toBe(false);
    expect(taxValid({ ...d, rate: "101" })).toBe(false);
    expect(taxValid({ ...d, rate: "4" })).toBe(true);
    expect(taxValid({ ...d, valid_from: "", rate: "4" })).toBe(false);
    expect(taxValid({ ...d, regime: "vat_profit", vat: "12", profit: "15" })).toBe(true);
    expect(taxValid({ ...d, regime: "vat_profit", vat: "120", profit: null })).toBe(false);
    expect(taxValid({ ...d, regime: "agent" })).toBe(true);
    expect(taxValid({ ...d, regime: "none" })).toBe(true);
  });

  it("serverga: rejimga tegishli bo'lmagan maydonlar nol", () => {
    const d = { ...taxDraft(null, today), rate: "4", base: "payout" as const, vat: "12", profit: "15" };
    expect(taxBody(d)).toEqual({ valid_from: today, regime: "turnover", rate_pct: "4", base: "payout", vat_pct: "0", profit_pct: "0" });
    expect(taxBody({ ...d, regime: "vat_profit" })).toEqual({ valid_from: today, regime: "vat_profit", rate_pct: "0", base: "revenue", vat_pct: "12", profit_pct: "15" });
    expect(taxBody({ ...d, regime: "agent" })).toMatchObject({ rate_pct: "0", vat_pct: "0", profit_pct: "0", base: "revenue" });
  });

  it("amalda turgan profil — sanasi bugundan oshmagan eng yangisi", () => {
    const rows = settingsData().tax_profiles;
    expect(activeTax(rows, today)?.id).toBe(TAX_2);
    expect(activeTax(rows, "2026-03-01")?.id).toBe(TAX_1);
    expect(activeTax(rows, "2025-12-31")).toBeNull();
    expect(activeTax([], today)).toBeNull();
  });
});

describe("muddatlar va qamrov", () => {
  const inv = settingsData().inventory;

  it("sozlanmagan — hamma bo'sh; qamrov standart", () => {
    expect(Object.values(leadDraft(inv))).toEqual([null, null, null, null, null]);
    expect(coverDraft(inv)).toEqual({ A: "60", B: "30", C: "14" });
    expect(inventoryState(leadDraft(inv), coverDraft(inv))).toBe("ok");
    expect(inventoryBody(leadDraft(inv), coverDraft(inv))).toEqual({ lead_days: null, cover_days: { A: 60, B: 30, C: 14 } });
  });

  it("sozlangan muddatlar formaga to'ldiriladi va serverga son bo'lib ketadi", () => {
    const lead = leadDraft({ ...inv, lead_days: { prep: 8, china: 2, cargo: 13, receive: 7, handover: 2 } });
    expect(lead.cargo).toBe("13");
    expect(inventoryState(lead, coverDraft(inv))).toBe("ok");
    expect(inventoryBody(lead, coverDraft(inv)).lead_days).toEqual({ prep: 8, china: 2, cargo: 13, receive: 7, handover: 2 });
  });

  it("qisman to'ldirilgan — 'partial'; noto'g'ri son yoki bo'sh qamrov — 'invalid'", () => {
    const empty = leadDraft(inv);
    expect(inventoryState({ ...empty, prep: "5" }, coverDraft(inv))).toBe("partial");
    const full = { prep: "8", china: "2", cargo: "13", receive: "7", handover: "2" };
    expect(inventoryState({ ...full, prep: "-1" }, coverDraft(inv))).toBe("invalid");
    expect(inventoryState({ ...full, prep: "400" }, coverDraft(inv))).toBe("invalid");
    expect(inventoryState({ ...full, prep: "1.5" }, coverDraft(inv))).toBe("invalid");
    expect(inventoryState(empty, { A: "60", B: null, C: "14" })).toBe("invalid");
  });

  it("to'lov shartlari: oy kunlari matni", () => {
    expect(termsDays([7, 14, 21, 28])).toBe("7, 14, 21, 28");
    expect(termsDays(null)).toBe("");
  });
});
