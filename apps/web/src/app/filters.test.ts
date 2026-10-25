import { describe, expect, it } from "vitest";

import { filterSearch, resolveFilters, toSearch } from "./filters";

const A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

describe("filterSearch (URL → tiplangan)", () => {
  it("to'g'ri qiymatlar saqlanadi", () => {
    expect(filterSearch({ shop: [A, B], from: "2026-10-01", to: "2026-10-25", cmp: "previous" })).toEqual({
      shop: [A, B],
      from: "2026-10-01",
      to: "2026-10-25",
      cmp: "previous",
    });
  });

  it("bitta do'kon satr bo'lib kelsa ham ro'yxatga, takrorlar olib tashlanadi", () => {
    expect(filterSearch({ shop: A })).toEqual({ shop: [A] });
    expect(filterSearch({ shop: [A, A, B] })).toEqual({ shop: [A, B] });
  });

  it("noto'g'ri do'kon ID, son va boshqa turlar jim tashlanadi", () => {
    expect(filterSearch({ shop: ["x", 5, null, A] })).toEqual({ shop: [A] });
    expect(filterSearch({ shop: ["' OR 1=1"] })).toEqual({});
  });

  it("davr faqat ikkala sana to'g'ri va tartibda bo'lsa", () => {
    expect(filterSearch({ from: "2026-10-01" })).toEqual({});
    expect(filterSearch({ to: "2026-10-01" })).toEqual({});
    expect(filterSearch({ from: "2026-13-40", to: "2026-10-01" })).toEqual({});
    expect(filterSearch({ from: "2026-10-25", to: "2026-10-01" })).toEqual({});
    expect(filterSearch({ from: "2026-10-25", to: "2026-10-25" })).toEqual({ from: "2026-10-25", to: "2026-10-25" });
  });

  it("solishtirish: faqat ma'lum rejimlar ('none' URL'da yo'q)", () => {
    expect(filterSearch({ cmp: "lastYear" })).toEqual({ cmp: "lastYear" });
    expect(filterSearch({ cmp: "none" })).toEqual({});
    expect(filterSearch({ cmp: "x" })).toEqual({});
  });
});

describe("resolveFilters", () => {
  it("tanlanmagan davr — shu oy (Toshkent kuni bo'yicha)", () => {
    expect(resolveFilters({}, "2026-10-25")).toEqual({
      shops: [],
      range: { start: "2026-10-01", end: "2026-10-25" },
      compare: "none",
    });
  });

  it("URL qiymatlari ustun", () => {
    expect(resolveFilters({ shop: [A], from: "2026-09-01", to: "2026-09-30", cmp: "lastYear" }, "2026-10-25")).toEqual({
      shops: [A],
      range: { start: "2026-09-01", end: "2026-09-30" },
      compare: "lastYear",
    });
  });
});

describe("toSearch", () => {
  it("bo'sh narsa yozilmaydi", () => {
    expect(toSearch({ shops: [], compare: "none" })).toEqual({});
    expect(toSearch({ shops: [A], range: { start: "2026-10-01", end: "2026-10-25" }, compare: "previous" })).toEqual({
      shop: [A],
      from: "2026-10-01",
      to: "2026-10-25",
      cmp: "previous",
    });
  });

  it("filterSearch bilan o'zaro mos", () => {
    const search = toSearch({ shops: [A, B], range: { start: "2026-01-01", end: "2026-10-25" }, compare: "lastYear" });
    expect(filterSearch(search)).toEqual(search);
  });
});
