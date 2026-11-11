import { describe, expect, it } from "vitest";

import { settingsData, TAX_1, TAX_2 } from "../../test/settings";
import type { TaxLine } from "../../lib/api/types";
import { activeTax, alertValid, coverDraft, inventoryBody, inventoryState, leadDraft, newLine, percentToShare, shareToPercent, taxBody, taxDraft, taxTemplate, taxValid, termsDays, type TaxDraft } from "./model";

const today = "2026-10-31";

describe("soliq profili shakli", () => {
  const names = { turnover: "Aylanmadan soliq", social: "Ijtimoiy soliq" };
  const yatt = (): TaxLine[] => [
    { id: "L1", name: "Aylanmadan soliq", kind: "percent", rate_pct: "1.0000", base: "revenue", amount: null, bhm_count: null, period: "month" },
    { id: "L2", name: "Ijtimoiy soliq", kind: "fixed", rate_pct: "0.0000", base: "revenue", amount: null, bhm_count: "1.00", period: "month" },
  ];

  it("qatordan forma: qatorli profil — o'z qatorlari; qatorsiz aylanma (eski) — bitta foizli qator; yangi — qatorsiz", () => {
    const p = settingsData().tax_profiles[0]!;
    const legacy = taxDraft(p, today);
    expect(legacy).toMatchObject({ valid_from: "2026-07-01", regime: "turnover", vat: null, profit: null });
    expect(legacy.lines).toMatchObject([{ name: "Aylanmadan soliq", kind: "percent", rate: "4", base: "payout" }]);
    expect(taxDraft({ ...p, rate_pct: "1.500" }, today).lines[0]?.rate).toBe("1.5");
    const lined = taxDraft({ ...p, rate_pct: "0.000", lines: yatt() }, today);
    expect(lined.lines).toMatchObject([
      { key: "L1", kind: "percent", rate: "1" },
      { key: "L2", kind: "fixed", mode: "bhm", bhm: "1", amount: null, period: "month" },
    ]);
    expect(taxDraft(null, today)).toMatchObject({ valid_from: today, regime: "turnover", lines: [] });
    expect(taxDraft({ ...p, regime: "none", rate_pct: "0.000" }, today).lines).toEqual([]);
  });

  it("tekshiruv: aylanmada kamida bitta to'g'ri qator, nomlar takrorlanmaydi, ko'pi bilan 10; QQS/foyda 0–100; agent va 'yo'q' — doim to'g'ri", () => {
    const d = taxDraft(null, today);
    expect(taxValid(d)).toBe(false); // qator yo'q
    const ok = newLine("percent", { name: "A", rate: "1" });
    expect(taxValid({ ...d, lines: [ok] })).toBe(true);
    expect(taxValid({ ...d, valid_from: "", lines: [ok] })).toBe(false);
    expect(taxValid({ ...d, lines: [{ ...ok, rate: "0" }] })).toBe(false);
    expect(taxValid({ ...d, lines: [{ ...ok, rate: "101" }] })).toBe(false);
    expect(taxValid({ ...d, lines: [{ ...ok, name: "  " }] })).toBe(false);
    expect(taxValid({ ...d, lines: [ok, newLine("percent", { name: "a", rate: "2" })] })).toBe(false); // takror nom
    const bhm = newLine("fixed", { name: "B", bhm: "1" });
    expect(taxValid({ ...d, lines: [ok, bhm] })).toBe(true);
    expect(taxValid({ ...d, lines: [ok, { ...bhm, bhm: null }] })).toBe(false);
    expect(taxValid({ ...d, lines: [ok, { ...bhm, mode: "sum", amount: "310000", bhm: null }] })).toBe(true);
    expect(taxValid({ ...d, lines: [ok, { ...bhm, mode: "sum", amount: "0", bhm: null }] })).toBe(false);
    const many = Array.from({ length: 11 }, (_, i) => newLine("percent", { name: `n${i}`, rate: "1" }));
    expect(taxValid({ ...d, lines: many })).toBe(false);
    expect(taxValid({ ...d, lines: many.slice(0, 10) })).toBe(true);
    expect(taxValid({ ...d, regime: "vat_profit", vat: "12", profit: "15" })).toBe(true);
    expect(taxValid({ ...d, regime: "vat_profit", vat: "120", profit: null })).toBe(false);
    expect(taxValid({ ...d, regime: "agent" })).toBe(true);
    expect(taxValid({ ...d, regime: "none" })).toBe(true);
  });

  it("serverga: aylanmada qatorlar (eski stavka nol); rejimga tegishli bo'lmagan maydonlar nol, qatorlar bo'sh", () => {
    const d: TaxDraft = {
      ...taxDraft(null, today),
      vat: "12",
      profit: "15",
      lines: [newLine("percent", { name: " Aylanmadan soliq ", rate: "1", base: "payout" }), newLine("fixed", { name: "Ijtimoiy soliq", bhm: "1" }), newLine("fixed", { name: "Qat'iy", mode: "sum", amount: "310000", period: "quarter" })],
    };
    expect(taxBody(d)).toEqual({
      valid_from: today,
      regime: "turnover",
      rate_pct: "0",
      base: "revenue",
      vat_pct: "0",
      profit_pct: "0",
      lines: [
        { name: "Aylanmadan soliq", kind: "percent", rate_pct: "1", base: "payout", period: "month" },
        { name: "Ijtimoiy soliq", kind: "fixed", rate_pct: "0", base: "revenue", period: "month", bhm_count: "1" },
        { name: "Qat'iy", kind: "fixed", rate_pct: "0", base: "revenue", period: "quarter", amount: "310000" },
      ],
    });
    expect(taxBody({ ...d, regime: "vat_profit" })).toEqual({ valid_from: today, regime: "vat_profit", rate_pct: "0", base: "revenue", vat_pct: "12", profit_pct: "15", lines: [] });
    expect(taxBody({ ...d, regime: "agent" })).toMatchObject({ rate_pct: "0", vat_pct: "0", profit_pct: "0", base: "revenue", lines: [] });
  });

  it("shablonlar: YaTT — ma'lumotnoma stavkasi + 1 BHM; MChJ — ma'lumotnoma stavkasi; bo'sh; stavka yo'q — bo'sh maydon", () => {
    const rates = [
      { code: "turnover_individual", rate_pct: "1.0000", note: null },
      { code: "turnover_ecommerce", rate_pct: "4.0000", note: null },
    ];
    expect(taxTemplate("yatt", rates, names)).toMatchObject([
      { name: "Aylanmadan soliq", kind: "percent", rate: "1" },
      { name: "Ijtimoiy soliq", kind: "fixed", mode: "bhm", bhm: "1", period: "month" },
    ]);
    expect(taxTemplate("ecommerce", rates, names)).toMatchObject([{ kind: "percent", rate: "4" }]);
    expect(taxTemplate("empty", rates, names)).toEqual([]);
    expect(taxTemplate("yatt", [], names)[0]?.rate).toBeNull();
    expect(taxValid({ ...taxDraft(null, today), lines: taxTemplate("yatt", rates, names) })).toBe(true); // shablon darhol saqlanadi
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

describe("ogohlantirish chegaralari (ADR-043)", () => {
  it("foiz ↔ ulush — vergul siljishi (float xatosi yo'q)", () => {
    expect(shareToPercent("0.300000")).toBe("30");
    expect(shareToPercent("0.075")).toBe("7.5");
    expect(shareToPercent("1")).toBe("100");
    expect(shareToPercent("0.000500")).toBe("0.05");
    expect(shareToPercent(null)).toBeNull();
    expect(percentToShare("30")).toBe("0.3");
    expect(percentToShare("7.5")).toBe("0.075");
    expect(percentToShare("0.07")).toBe("0.0007");
    expect(percentToShare("100")).toBe("1");
    expect(percentToShare(null)).toBeNull();
  });

  it("chegara: (0; 100]; bo'sh — to'g'ri (o'chirilgan)", () => {
    expect(alertValid(null)).toBe(true);
    expect(alertValid("30")).toBe(true);
    expect(alertValid("100")).toBe(true);
    expect(alertValid("0")).toBe(false);
    expect(alertValid("101")).toBe(false);
  });
});
