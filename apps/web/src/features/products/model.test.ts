// Mahsulotlar modeli va URL qidiruvi: ustunlar tanlovi, saralash almashinuvi, brauzerdagi ko'rinishlar.
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PRODUCT_SORT, parseSort, productsSearch } from "../../app/search";
import {
  COLUMN_IDS,
  DEFAULT_COLUMNS,
  loadColumns,
  loadViews,
  nextSort,
  normalizeColumns,
  saveColumns,
  saveViews,
  sortParam,
  upsertView,
  type SavedView,
} from "./model";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("productsSearch", () => {
  it("to'g'ri qiymatlar saqlanadi, noto'g'ri tashlanadi, standart saralash URL'da yo'q", () => {
    expect(productsSearch({ q: " mashina ", sort: "-roi", label: "loss", abc: "B" })).toEqual({ q: " mashina ", sort: "-roi", label: "loss", abc: "B" });
    expect(productsSearch({ q: "  ", sort: "-revenue" })).toEqual({});
    expect(productsSearch({ sort: "nope", label: "x", abc: "D" })).toEqual({});
    expect(productsSearch({ q: "a".repeat(300) }).q).toHaveLength(100);
    expect(productsSearch({ sort: 5, q: 3 })).toEqual({});
  });

  it("parseSort: standart, kamayish va o'sish", () => {
    expect(parseSort(undefined)).toEqual(DEFAULT_PRODUCT_SORT);
    expect(parseSort("nope")).toEqual(DEFAULT_PRODUCT_SORT);
    expect(parseSort("-roi")).toEqual({ key: "roi", desc: true });
    expect(parseSort("title")).toEqual({ key: "title", desc: false });
  });
});

describe("saralash", () => {
  it("bir xil kalit — yo'nalish almashadi; yangi kalit — kamayish (nom — o'sish)", () => {
    expect(nextSort({ key: "revenue", desc: true }, "revenue")).toEqual({ key: "revenue", desc: false });
    expect(nextSort({ key: "revenue", desc: false }, "revenue")).toEqual({ key: "revenue", desc: true });
    expect(nextSort({ key: "revenue", desc: true }, "roi")).toEqual({ key: "roi", desc: true });
    expect(nextSort({ key: "revenue", desc: true }, "title")).toEqual({ key: "title", desc: false });
    expect(sortParam({ key: "roi", desc: true })).toBe("-roi");
    expect(sortParam({ key: "title", desc: false })).toBe("title");
  });
});

describe("ustunlar", () => {
  it("normalizeColumns: noma'lum tashlanadi, majburiy qo'shiladi, tartib — standart", () => {
    expect(normalizeColumns(["roi", "x", "units"])).toEqual(["product", "units", "roi"]);
    expect(normalizeColumns("nope")).toBeNull();
    expect(normalizeColumns([])).toEqual(["product"]);
  });

  it("standart ustunlar ro'yxatda va majburiy ustunni o'z ichiga oladi", () => {
    expect(DEFAULT_COLUMNS[0]).toBe("product");
    expect(DEFAULT_COLUMNS.every((c) => COLUMN_IDS.includes(c))).toBe(true);
  });

  it("saqlash va o'qish; buzilgan yozuv — null; saqlash yopiq bo'lsa jim", () => {
    expect(loadColumns("o1")).toBeNull();
    saveColumns("o1", ["product", "roi"]);
    expect(loadColumns("o1")).toEqual(["product", "roi"]);
    expect(loadColumns("o2")).toBeNull(); // tashkilot bo'yicha alohida
    localStorage.setItem("up.products.columns.o3", "{broken");
    expect(loadColumns("o3")).toBeNull();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("yopiq");
    });
    expect(() => saveColumns("o1", ["product"])).not.toThrow();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("yopiq");
    });
    expect(loadColumns("o1")).toBeNull();
  });
});

describe("saqlangan ko'rinishlar", () => {
  const view = (name: string): SavedView => ({ name, columns: ["product", "roi"], label: "loss" });

  it("upsertView: nom bo'yicha almashtiradi va tartiblaydi", () => {
    const a = upsertView([], view("B"));
    const b = upsertView(a, view("A"));
    expect(b.map((v) => v.name)).toEqual(["A", "B"]);
    expect(upsertView(b, { ...view("A"), label: "borderline" }).find((v) => v.name === "A")?.label).toBe("borderline");
    expect(upsertView(b, view("A"))).toHaveLength(2);
  });

  it("saqlash/o'qish; yaroqsiz yozuvlar tashlanadi", () => {
    saveViews("o1", [view("X")]);
    expect(loadViews("o1")).toEqual([view("X")]);
    localStorage.setItem("up.products.views.o2", JSON.stringify([{ name: "", columns: [] }, { name: "ok", columns: ["roi"] }, { columns: ["roi"] }, 5]));
    expect(loadViews("o2")).toEqual([{ name: "ok", columns: ["product", "roi"] }]);
    localStorage.setItem("up.products.views.o3", "not json");
    expect(loadViews("o3")).toEqual([]);
    localStorage.setItem("up.products.views.o4", JSON.stringify({ a: 1 }));
    expect(loadViews("o4")).toEqual([]);
  });
});
