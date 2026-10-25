import { describe, expect, it } from "vitest";

import {
  formatChange,
  formatCompact,
  formatCurrency,
  formatDate,
  formatDay,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPeriod,
  formatRelative,
  formatterFor,
  formatWeekday,
  MINUS,
  NBSP,
  ruPlural,
} from ".";

// Testlarda o'qish oson bo'lishi uchun: "_" — U+00A0, "-" boshida — U+2212.
const v = (text: string) => text.replaceAll("_", NBSP).replace(/^-/, MINUS);

describe("sonlar (04 §8.4)", () => {
  it("guruh U+00A0, kasr vergul, manfiy U+2212", () => {
    expect(formatNumber(1234567)).toBe(v("1_234_567"));
    expect(formatNumber("1234.5", { digits: 1 })).toBe(v("1_234,5"));
    expect(formatNumber("-312400.00")).toBe(v("-312_400"));
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber("999")).toBe("999");
    expect(formatNumber("12.50", { digits: 2, trim: true })).toBe("12,5");
    expect(formatNumber(5, { sign: true })).toBe("+5");
    expect(formatNumber(0, { sign: true })).toBe("0");
  });

  it("ROUND_HALF_UP satr ustida (float xatosisiz)", () => {
    expect(formatNumber("2.5")).toBe("3");
    expect(formatNumber("-2.5")).toBe(v("-3"));
    expect(formatNumber("1.005", { digits: 2 })).toBe("1,01"); // float'da 1.00
    expect(formatNumber("-0.4")).toBe("0"); // "−0" yo'q
    expect(formatNumber("123456789012345678901234.49")).toBe(v("123_456_789_012_345_678_901_234"));
    expect(formatNumber(0.1 + 0.2, { digits: 2 })).toBe("0,30");
    expect(formatNumber(10n ** 21n)).toBe(v("1_000_000_000_000_000_000_000"));
    expect(formatNumber(1e21)).toBe(v("1_000_000_000_000_000_000_000"));
    expect(() => formatNumber("abc")).toThrow(RangeError);
    expect(() => formatNumber(Number.NaN)).toThrow(RangeError);
  });

  it("pul va valyutalar", () => {
    expect(formatMoney("48357200.00", "uz-Latn")).toBe(v("48_357_200_soʻm"));
    expect(formatMoney("48357200.00", "uz-Cyrl")).toBe(v("48_357_200_сўм"));
    expect(formatMoney("48357200.00", "ru")).toBe(v("48_357_200_сум"));
    expect(formatMoney("-1500.40", "uz-Latn", { unit: false })).toBe(v("-1_500"));
    expect(formatCurrency("142.5", "USD")).toBe(v("142,50_$"));
    expect(formatCurrency("1000", "CNY")).toBe(v("1_000_¥"));
    expect(formatCurrency("3", "KZT")).toBe(v("3_KZT"));
  });

  it("ixcham", () => {
    expect(formatCompact(850_000, "uz-Latn")).toBe(v("850_ming"));
    expect(formatCompact(1_234_567, "uz-Latn")).toBe(v("1,2_mln"));
    expect(formatCompact("3400000000", "uz-Latn")).toBe(v("3,4_mlrd"));
    expect(formatCompact(2_000_000, "ru")).toBe(v("2_млн"));
    expect(formatCompact(850_400, "ru")).toBe(v("850_тыс."));
    expect(formatCompact(1_250_000, "uz-Cyrl")).toBe(v("1,3_млн"));
    expect(formatCompact(-999_950, "uz-Latn")).toBe(v("-1_000_ming"));
    expect(formatCompact(999, "uz-Latn")).toBe("999");
  });

  it("foiz va o'zgarish", () => {
    expect(formatPercent("0.125000")).toBe("12,5%");
    expect(formatPercent("0.1")).toBe("10%");
    expect(formatPercent("1.000000")).toBe("100%");
    expect(formatPercent("-0.031")).toBe(v("-3,1%"));
    expect(formatPercent("0.0004", { digits: 2 })).toBe("0,04%");
    expect(formatPercent("0.05", { sign: true })).toBe("+5%");
    expect(formatChange("0.124")).toBe("▲ 12,4%");
    expect(formatChange("-0.031")).toBe("▼ 3,1%");
    expect(formatChange("0")).toBe("0%");
  });
});

describe("sanalar (Toshkent)", () => {
  it("sana, kun, hafta kuni", () => {
    expect(formatDate("2026-10-23")).toBe("23.10.2026");
    // UTC 20:00 — Toshkentda ertasi kun.
    expect(formatDate(new Date("2026-09-30T20:00:00Z"))).toBe("01.10.2026");
    expect(formatDate("2026-09-30T20:00:00Z")).toBe("01.10.2026");
    expect(formatDay("2026-10-23", "uz-Latn")).toBe("23-oktabr");
    expect(formatDay("2026-10-23", "uz-Cyrl")).toBe("23-октябр");
    expect(formatDay("2026-10-23", "ru")).toBe(v("23_октября"));
    expect(formatDay("2025-09-01", "uz-Latn", { withYear: true })).toBe("1-sentabr 2025");
    expect(formatWeekday("2026-10-26", "uz-Latn")).toBe("Du");
    expect(formatWeekday("2026-10-25", "uz-Latn")).toBe("Ya");
    expect(formatWeekday("2026-10-25", "ru")).toBe("Вс");
    expect(() => formatDate("23.10.2026")).toThrow(RangeError);
  });

  it("davr", () => {
    expect(formatPeriod("2026-10-01", "2026-10-31", "uz-Latn")).toBe("1–31-oktabr");
    expect(formatPeriod("2026-10-01", "2026-10-31", "ru")).toBe(v("1–31_октября"));
    expect(formatPeriod("2026-10-05", "2026-10-05", "uz-Latn")).toBe("5-oktabr");
    expect(formatPeriod("2026-09-28", "2026-10-03", "uz-Latn")).toBe("28-sentabr – 3-oktabr");
    expect(formatPeriod("2025-12-29", "2026-01-04", "uz-Latn")).toBe("29-dekabr 2025 – 4-yanvar 2026");
  });

  it("nisbiy vaqt", () => {
    const now = new Date("2026-10-25T12:00:00Z");
    const ago = (s: number) => new Date(now.getTime() - s * 1000);
    expect(formatRelative(ago(30), "uz-Latn", now)).toBe("hozirgina");
    expect(formatRelative(ago(180), "uz-Latn", now)).toBe("3 daqiqa oldin");
    expect(formatRelative(ago(180), "ru", now)).toBe("3 минуты назад");
    expect(formatRelative(ago(21 * 60), "ru", now)).toBe("21 минуту назад");
    expect(formatRelative(ago(5 * 3600), "uz-Cyrl", now)).toBe("5 соат олдин");
    expect(formatRelative(ago(2 * 86_400), "ru", now)).toBe("2 дня назад");
    expect(formatRelative(ago(10 * 86_400), "uz-Latn", now)).toBe("15.10.2026");
    expect(formatRelative(new Date(now.getTime() + 5000), "ru", now)).toBe("только что");
    expect([1, 2, 5, 11, 12, 21, 22, 25, 111].map(ruPlural)).toEqual([0, 1, 2, 2, 2, 0, 1, 2, 2]);
  });

  it("tilga bog'langan formatlovchi", () => {
    const f = formatterFor("ru");
    expect(f.money(1000)).toBe(v("1_000_сум"));
    expect(f.day("2026-10-23")).toBe(v("23_октября"));
    expect(f.compact(2_000_000)).toBe(v("2_млн"));
    expect(f.period("2026-10-01", "2026-10-02")).toBe(v("1–2_октября"));
    expect(f.weekday("2026-10-26")).toBe("Пн");
    expect(f.month("2026-10-23")).toBe("октябрь 2026");
    expect(formatterFor("uz-Latn").month("2026-09-01")).toBe("sentabr 2026");
    expect(f.relative(new Date(), new Date())).toBe("только что");
  });
});
