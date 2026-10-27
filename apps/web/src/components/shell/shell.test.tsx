// Karkas (B3.5): menyu, filtrlar (URL), SyncIndicator, mobil tab bar, Ctrl+K, foydalanuvchi menyusi, axe-core.
// Butun ilova (marshrutlovchi + so'rovlar) soxta API ustida — `test/api.ts`.
import { createMemoryHistory, type RouterHistory } from "@tanstack/react-router";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { meQuery } from "../../app/query";
import { presetRange, todayTashkent } from "../../lib/dates";
import {
  json,
  LOGOUT_ROUTE,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  REFRESH_ROUTE,
  SHOP_A,
  SHOP_B,
  SYNC_ROUTE,
  syncStatus,
  type Routes,
} from "../../test/api";
import { isPaletteShortcut, searchItems, type PaletteItem } from "./CommandPalette";
import { effectiveShops, toggleShop } from "./ShopFilter";
import { isActivePath, NAV_ALL, NAV_MORE, NAV_TABS } from "./nav";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

async function renderShell(path = "/", routes: Routes = {}) {
  const api = mockApi(routes);
  const history = createMemoryHistory({ initialEntries: [path] });
  const state = createAppState(history, "uz-Latn");
  render(<App state={state} />);
  await screen.findByRole("navigation", { name: "Asosiy menyu" });
  return { api, history, state };
}

const params = (history: RouterHistory) => new URLSearchParams(history.location.search);
const sidebar = () => within(screen.getByRole("navigation", { name: "Asosiy menyu" }));
const tabbar = () => within(screen.getByRole("navigation", { name: "Pastki menyu" }));
const topbar = () => within(screen.getByRole("banner"));
const open = (name: string | RegExp) => fireEvent.click(topbar().getByRole("button", { name }));
const SERIOUS = ["serious", "critical"];

async function serious(): Promise<string[]> {
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((v) => SERIOUS.includes(v.impact ?? ""))
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("menyu", () => {
  it("sidebar: hamma bo'limlar, faol bo'lim aria-current, bosilsa sahifa ochiladi", async () => {
    const { history } = await renderShell("/");
    expect(sidebar().getAllByRole("link").map((l) => l.textContent)).toEqual([
      "Asosiy",
      "Foyda",
      "Mahsulotlar",
      "Buyurtmalar",
      "Xarajatlar",
      "Xaridlar",
      "Ombor",
      "Pul oqimi",
      "Hisobotlar",
      "Maʼlumotlar holati",
      "Sozlamalar",
    ]);
    expect(sidebar().getByRole("link", { name: "Asosiy" }).getAttribute("aria-current")).toBe("page");
    expect(sidebar().getByRole("link", { name: "Xarajatlar" }).getAttribute("aria-current")).toBeNull();

    fireEvent.click(sidebar().getByRole("link", { name: "Xarajatlar" }));
    expect(await screen.findByRole("heading", { name: "Xarajatlar" })).toBeTruthy();
    expect(screen.getByText("Sahifa qurilmoqda. Hozircha eski dasturdan foydalaning.")).toBeTruthy();
    expect(history.location.pathname).toBe("/expenses");
    expect(sidebar().getByRole("link", { name: "Xarajatlar" }).getAttribute("aria-current")).toBe("page");
    expect(sidebar().getByRole("link", { name: "Asosiy" }).getAttribute("aria-current")).toBeNull();
  });

  it("har bo'lim o'z sahifasiga olib boradi (404 emas)", async () => {
    const { history } = await renderShell("/");
    for (const item of NAV_ALL.filter((n) => n.to !== "/")) {
      const link = sidebar().getAllByRole("link").find((l) => l.getAttribute("href")!.startsWith(item.to))!;
      fireEvent.click(link);
      await waitFor(() => expect(history.location.pathname).toBe(item.to));
      expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
      expect(screen.queryByText("Sahifa topilmadi")).toBeNull();
    }
  });

  it("bitta main landmark; 'o'tkazib yuborish' havolasi kontentga fokus beradi", async () => {
    await renderShell("/status");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const skip = screen.getByRole("link", { name: "Asosiy kontentga oʻtish" });
    fireEvent.click(skip);
    expect(document.activeElement).toBe(screen.getByRole("main"));
  });

  it("davr va do'kon filtrlari bo'limdan bo'limga o'tganda saqlanadi", async () => {
    const search = `from=2026-09-01&to=2026-09-30&cmp=previous&shop=${encodeURIComponent(JSON.stringify([SHOP_A]))}`;
    const { history } = await renderShell(`/?${search}`);
    const href = sidebar().getByRole("link", { name: "Ombor" }).getAttribute("href")!;
    expect(href.startsWith("/inventory?")).toBe(true);
    const link = new URLSearchParams(href.split("?")[1]);
    expect(link.get("from")).toBe("2026-09-01");
    expect(link.get("to")).toBe("2026-09-30");
    expect(link.get("cmp")).toBe("previous");
    expect(JSON.parse(link.get("shop")!)).toEqual([SHOP_A]);

    fireEvent.click(sidebar().getByRole("link", { name: "Ombor" }));
    await screen.findByRole("heading", { name: "Ombor" });
    expect(params(history).get("from")).toBe("2026-09-01");
    expect(params(history).get("cmp")).toBe("previous");
  });
});

describe("nav.ts", () => {
  it("tab bar: Asosiy, Foyda, Ombor, Xaridlar; qolgani 'Yana'da — hech narsa yo'qolmaydi", () => {
    expect(NAV_TABS.map((n) => n.key)).toEqual(["home", "pnl", "inventory", "purchases"]);
    expect([...NAV_TABS, ...NAV_MORE].map((n) => n.key).sort()).toEqual(NAV_ALL.map((n) => n.key).sort());
    expect(new Set(NAV_ALL.map((n) => n.to)).size).toBe(NAV_ALL.length);
  });

  it("isActivePath: '/' faqat aniq, ichki sahifa bo'limni faol qiladi", () => {
    expect(isActivePath("/", "/")).toBe(true);
    expect(isActivePath("/pnl", "/")).toBe(false);
    expect(isActivePath("/products/12", "/products")).toBe(true);
    expect(isActivePath("/products", "/products")).toBe(true);
    expect(isActivePath("/productsx", "/products")).toBe(false);
  });
});

describe("topbar: filtrlar (URL'da)", () => {
  it("tanlanmagan davr — Shu oy", async () => {
    await renderShell("/");
    expect(topbar().getByRole("button", { name: /^Davr: Shu oy/ })).toBeTruthy();
  });

  it("davr: tayyor davr tanlansa URL'da (Toshkent kuni bo'yicha)", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-25T09:00:00Z"));
    const { history } = await renderShell("/");
    open(/^Davr:/);
    fireEvent.click(screen.getByRole("button", { name: "7 kun" }));
    expect(params(history).get("from")).toBe("2026-10-19");
    expect(params(history).get("to")).toBe("2026-10-25");
    expect(await topbar().findByRole("button", { name: /^Davr: 7 kun/ })).toBeTruthy();
  });

  it("'Hammasi' davri tanlangan do'konlarning eng birinchi sotuvidan boshlanadi", async () => {
    const { history } = await renderShell(`/?shop=${encodeURIComponent(JSON.stringify([SHOP_B]))}`);
    await screen.findByRole("button", { name: /Doʻkon: EL-ONE/ });
    open(/^Davr:/);
    fireEvent.click(screen.getByRole("button", { name: "Hammasi" }));
    expect(params(history).get("from")).toBe("2025-09-02");
    expect(params(history).get("to")).toBe(presetRange("all", todayTashkent()).end);
  });

  it("do'kon: ro'yxat (taxallus bilan), bittasini olib tashlash, hammasi qaytsa URL'dan yo'qoladi", async () => {
    const { history } = await renderShell("/");
    open("Doʻkon: Hammasi");
    const durii = await screen.findByRole("checkbox", { name: "Durii" });
    const elone = screen.getByRole("checkbox", { name: "EL-ONE" });
    expect((durii as HTMLInputElement).checked && (elone as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("button", { name: "Hammasi" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(elone);
    await waitFor(() => expect(JSON.parse(params(history).get("shop")!)).toEqual([SHOP_A]));
    expect(topbar().getByRole("button", { name: "Doʻkon: Durii" })).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: "EL-ONE" }) as HTMLInputElement).checked).toBe(false);

    // bittasi doim tanlangan
    fireEvent.click(screen.getByRole("checkbox", { name: "Durii" }));
    expect(JSON.parse(params(history).get("shop")!)).toEqual([SHOP_A]);

    fireEvent.click(screen.getByRole("checkbox", { name: "EL-ONE" }));
    await waitFor(() => expect(params(history).has("shop")).toBe(false));
    expect(topbar().getByRole("button", { name: "Doʻkon: Hammasi" })).toBeTruthy();
  });

  it("do'kon filtri: boshqa filtrlarni buzmaydi; ro'yxat xatosi matn bilan", async () => {
    const { history } = await renderShell("/?from=2026-10-01&to=2026-10-10&cmp=lastYear", {
      [`GET /api/v1/orgs/${ME.orgs[0].id}/shops`]: () => problem(403, "forbidden"),
    });
    open("Doʻkon: Hammasi");
    expect((await screen.findByRole("alert")).textContent).toContain("Doʻkonlar roʻyxati yuklanmadi.");
    expect(params(history).get("cmp")).toBe("lastYear");
  });

  it("solishtirish: tanlansa URL'da, yopiladi, tugma nomi o'zgaradi", async () => {
    const { history } = await renderShell("/");
    open("Solishtirish");
    fireEvent.click(screen.getByRole("radio", { name: "Oldingi davr" }));
    expect(params(history).get("cmp")).toBe("previous");
    expect(screen.queryByRole("radio", { name: "Oldingi davr" })).toBeNull();
    await topbar().findByRole("button", { name: "Solishtirish: Oldingi davr" });
    open("Solishtirish: Oldingi davr");
    fireEvent.click(screen.getByRole("radio", { name: "Oʻtgan yil" }));
    expect(params(history).get("cmp")).toBe("lastYear");
    await topbar().findByRole("button", { name: "Solishtirish: Oʻtgan yil" });
    open("Solishtirish: Oʻtgan yil");
    fireEvent.click(screen.getByRole("radio", { name: "Yoʻq" }));
    expect(params(history).has("cmp")).toBe(false);
  });

  it("noto'g'ri URL qiymatlari sahifani buzmaydi", async () => {
    await renderShell("/?from=kecha&to=bugun&cmp=x&shop=1");
    expect(topbar().getByRole("button", { name: /^Davr: Shu oy/ })).toBeTruthy();
    expect(topbar().getByRole("button", { name: "Doʻkon: Hammasi" })).toBeTruthy();
    expect(topbar().getByRole("button", { name: "Solishtirish" })).toBeTruthy();
  });
});

describe("ShopFilter yordamchilari", () => {
  const shops = [{ id: SHOP_A }, { id: SHOP_B }] as Parameters<typeof effectiveShops>[1];

  it("toggleShop: hammasi tanlangandan bittasini olib tashlash, qaytarish, oxirgisini saqlash", () => {
    expect(toggleShop([], SHOP_B, shops)).toEqual([SHOP_A]);
    expect(toggleShop([SHOP_A], SHOP_B, shops)).toEqual([]);
    expect(toggleShop([SHOP_A], SHOP_A, shops)).toEqual([SHOP_A]);
  });

  it("effectiveShops: begona ID tashlanadi, hammasi — bo'sh", () => {
    expect(effectiveShops([SHOP_A, "zzz"], shops)).toEqual([SHOP_A]);
    expect(effectiveShops([SHOP_A, SHOP_B], shops)).toEqual([]);
    expect(effectiveShops(["zzz"], shops)).toEqual([]);
    expect(effectiveShops([], shops)).toEqual([]);
  });
});

describe("SyncIndicator", () => {
  const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
  const sync = (over: Parameters<typeof syncStatus>[0]): Routes => ({ [SYNC_ROUTE]: () => json(200, syncStatus(over)) });
  const trigger = () => screen.findByRole("button", { name: /^Maʼlumot yangiligi:/ });

  it("yangi ma'lumot: 'Yangilandi: 3 daqiqa oldin'; bosilsa tur bo'yicha holat", async () => {
    await renderShell("/");
    expect((await trigger()).getAttribute("aria-label")).toBe("Maʼlumot yangiligi: Yangilandi: 3 daqiqa oldin");
    fireEvent.click(await trigger());
    const panel = screen.getByRole("group", { name: /^Maʼlumot yangiligi/ });
    const rows = within(panel)
      .getAllByRole("term")
      .map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]);
    expect(rows).toEqual([
      ["Sotuvlar", "3 daqiqa oldin"],
      ["Xarajatlar", "25 daqiqa oldin"],
      ["Mahsulotlar", "40 daqiqa oldin"],
      ["Qaytarishlar", "hali yoʻq"],
    ]);
  });

  it("eskirgan, xato, hali yo'q, uzilish — har biri o'z matni bilan", async () => {
    const cases: Array<[Parameters<typeof syncStatus>[0], string]> = [
      [{ freshness: { orders: ago(125) } }, "Yangilanmagan: 2 soat oldin"],
      [{ healthy: false }, "Sinxronda xato"],
      [{ freshness: { orders: null } }, "Hali yangilanmagan"],
      [{ outage: { active: true, since: ago(30), paused_until: null, recovered_from: null, recovered_at: null } }, "Uzumda uzilish"],
    ];
    for (const [over, text] of cases) {
      cleanup();
      await renderShell("/", sync(over));
      expect((await trigger()).getAttribute("aria-label")).toBe(`Maʼlumot yangiligi: ${text}`);
    }
  });

  it("holat yuklanmasa — 'Holat nomaʼlum' (yangi deb aldamaydi)", async () => {
    await renderShell("/", { [SYNC_ROUTE]: () => problem(403, "forbidden") });
    expect((await trigger()).getAttribute("aria-label")).toBe("Maʼlumot yangiligi: Holat nomaʼlum");
    fireEvent.click(await trigger());
    expect(within(screen.getByRole("group", { name: /^Maʼlumot yangiligi/ })).getByRole("alert").textContent).toContain("ruxsatingiz yoʻq");
  });

  it("uzilishda sariq banner: 'sotuv yo'q' ga ishonmaslik; yangilash o'chiq", async () => {
    await renderShell("/", sync({ outage: { active: true, since: ago(30), paused_until: null, recovered_from: null, recovered_at: null } }));
    expect(await screen.findByText(/Shu paytda sotuv yoʻq deb koʻrinsa, ishonmang/)).toBeTruthy();
    fireEvent.click(await trigger());
    expect((screen.getByRole("button", { name: "Hozir yangilash" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("uzilish yo'q — banner yo'q", async () => {
    await renderShell("/");
    await trigger();
    expect(screen.queryByText("Uzumda uzilish")).toBeNull();
  });

  it("'Hozir yangilash': so'rov, xabar, holat qayta olinadi", async () => {
    const { api } = await renderShell("/");
    fireEvent.click(await trigger());
    fireEvent.click(screen.getByRole("button", { name: "Hozir yangilash" }));
    expect(await screen.findByText("Yangilash boshlandi")).toBeTruthy();
    expect(api.count(REFRESH_ROUTE)).toBe(1);
    await waitFor(() => expect(api.count(SYNC_ROUTE)).toBe(2));
  });

  it("'Hozir yangilash' cheklangan (429): API xabari tushunarli", async () => {
    await renderShell("/", { [REFRESH_ROUTE]: () => problem(429, "sync_refresh_limited") });
    fireEvent.click(await trigger());
    fireEvent.click(screen.getByRole("button", { name: "Hozir yangilash" }));
    expect(await screen.findByText("Yangilash yaqinda boshlangan. Bir daqiqadan soʻng qayta urining.")).toBeTruthy();
  });

  it("'Maʼlumotlar holati' havolasi sahifaga olib boradi", async () => {
    const { history } = await renderShell("/pnl?cmp=previous");
    fireEvent.click(await trigger());
    fireEvent.click(within(screen.getByRole("group", { name: /^Maʼlumot yangiligi/ })).getByRole("link", { name: "Maʼlumotlar holati" }));
    expect(await screen.findByRole("heading", { name: "Maʼlumotlar holati" })).toBeTruthy();
    expect(history.location.pathname).toBe("/status");
    expect(params(history).get("cmp")).toBe("previous");
  });

  it("holat har daqiqa qayta so'raladi", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const { api } = await renderShell("/");
    await trigger();
    const before = api.count(SYNC_ROUTE);
    await act(async () => {
      vi.advanceTimersByTime(61_000);
    });
    await waitFor(() => expect(api.count(SYNC_ROUTE)).toBeGreaterThan(before));
  });
});

describe("Ctrl+K", () => {
  const keyK = (init: KeyboardEventInit = {}) => fireEvent.keyDown(window, { key: "k", code: "KeyK", ctrlKey: true, ...init });
  const palette = () => screen.getByRole("dialog", { name: "Tez oʻtish" });
  const input = () => within(palette()).getByRole("combobox", { name: "Sahifa yoki amalni qidiring" });
  const options = () => within(palette()).getAllByRole("option").map((o) => o.textContent);

  it("klaviatura yorlig'i: Ctrl/⌘ + K, har qanday harf joylashuvida (kirill 'л' ham)", () => {
    const base = { key: "k", code: "KeyK", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false };
    expect(isPaletteShortcut({ ...base, ctrlKey: true })).toBe(true);
    expect(isPaletteShortcut({ ...base, metaKey: true, key: "K" })).toBe(true);
    expect(isPaletteShortcut({ ...base, ctrlKey: true, key: "л" })).toBe(true);
    expect(isPaletteShortcut(base)).toBe(false);
    expect(isPaletteShortcut({ ...base, ctrlKey: true, key: "j", code: "KeyJ" })).toBe(false);
    expect(isPaletteShortcut({ ...base, ctrlKey: true, shiftKey: true })).toBe(false);
    expect(isPaletteShortcut({ ...base, ctrlKey: true, altKey: true })).toBe(false);
  });

  it("ochiladi (fokus qidiruvda), Ctrl+K yana bossa yopiladi, Esc yopib fokusni qaytaradi", async () => {
    await renderShell("/");
    const launcher = topbar().getByRole("button", { name: /^Tez oʻtish/ });
    launcher.focus();
    keyK();
    expect(document.activeElement).toBe(input());
    keyK();
    expect(screen.queryByRole("dialog", { name: "Tez oʻtish" })).toBeNull();

    keyK({ ctrlKey: false, metaKey: true });
    expect(palette()).toBeTruthy();
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Tez oʻtish" })).toBeNull();
    expect(document.activeElement).toBe(launcher);
  });

  it("topbar tugmasi ham ochadi; fon bosilsa yopiladi", async () => {
    await renderShell("/");
    fireEvent.click(topbar().getByRole("button", { name: /^Tez oʻtish/ }));
    expect(palette()).toBeTruthy();
    fireEvent.click(document.querySelector(".palette .ui-layer__backdrop")!);
    expect(screen.queryByRole("dialog", { name: "Tez oʻtish" })).toBeNull();
  });

  it("brauzerning o'z Ctrl+K si bekor qilinadi", async () => {
    await renderShell("/");
    const event = new KeyboardEvent("keydown", { key: "k", code: "KeyK", ctrlKey: true, cancelable: true, bubbles: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it("sahifa qidiruvi: lotin, kirill va apostrofsiz yozuv bir xil; Enter — o'tish, davr saqlanadi", async () => {
    const { history } = await renderShell("/?cmp=previous");
    keyK();
    fireEvent.change(input(), { target: { value: "foy" } });
    expect(options()).toEqual(["Foyda" + "Sahifa"]);
    fireEvent.change(input(), { target: { value: "фойда" } });
    expect(options()).toEqual(["FoydaSahifa"]);
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(screen.queryByRole("dialog", { name: "Tez oʻtish" })).toBeNull();
    await screen.findByRole("heading", { level: 1, name: /^Foyda va zarar/ });
    expect(history.location.pathname).toBe("/pnl");
    expect(params(history).get("cmp")).toBe("previous");
  });

  it("↑ ↓ bilan tanlash, sichqoncha bilan bosish", async () => {
    const { history } = await renderShell("/");
    keyK();
    expect(input().getAttribute("aria-activedescendant")).toBe(within(palette()).getAllByRole("option")[0].id);
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(within(palette()).getAllByRole("option")[2].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    fireEvent.keyDown(input(), { key: "Enter" }); // ikkinchi — Foyda
    await waitFor(() => expect(history.location.pathname).toBe("/pnl"));

    keyK();
    fireEvent.click(within(palette()).getByRole("option", { name: /^Ombor/ }));
    await waitFor(() => expect(history.location.pathname).toBe("/inventory"));
  });

  it("amallar: mavzu va til", async () => {
    await renderShell("/");
    keyK();
    fireEvent.change(input(), { target: { value: "qorongi" } });
    expect(options()).toEqual(["Mavzu: QorongʻiAmal"]);
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    keyK();
    fireEvent.change(input(), { target: { value: "русский" } });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(await within(await screen.findByRole("navigation", { name: "Главное меню" })).findByRole("link", { name: "Прибыль" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("ru");
  });

  it("hech narsa topilmasa — xabar, Enter hech narsa qilmaydi", async () => {
    const { history } = await renderShell("/");
    keyK();
    fireEvent.change(input(), { target: { value: "qqqqqq" } });
    expect(within(palette()).queryAllByRole("option")).toHaveLength(0);
    expect(within(palette()).getByText("Hech narsa topilmadi")).toBeTruthy();
    expect(input().getAttribute("aria-activedescendant")).toBeNull();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(palette()).toBeTruthy();
    expect(history.location.pathname).toBe("/");
  });

  it("qayta ochilganda qidiruv tozalanadi", async () => {
    await renderShell("/");
    keyK();
    fireEvent.change(input(), { target: { value: "foy" } });
    keyK();
    keyK();
    expect((input() as HTMLInputElement).value).toBe("");
  });

  it("searchItems: qo'shimcha so'zlar bo'yicha ham topadi, tartib saqlanadi", () => {
    const run = () => {};
    const items: PaletteItem[] = [
      { id: "1", group: "page", label: "Mahsulotlar", keywords: "sku tovar", run },
      { id: "2", group: "page", label: "Xaridlar", run },
    ];
    expect(searchItems(items, "").map((i) => i.id)).toEqual(["1", "2"]);
    expect(searchItems(items, "tovar").map((i) => i.id)).toEqual(["1"]);
    expect(searchItems(items, "хар").map((i) => i.id)).toEqual(["2"]);
  });
});

describe("foydalanuvchi menyusi", () => {
  const openUser = () => open(/^Hisob:/);
  const account = () => screen.getByRole("group", { name: /^Hisob:/ });

  it("kim kirgan, tashkilot", async () => {
    await renderShell("/");
    expect(topbar().getByRole("button", { name: "Hisob: Temur" })).toBeTruthy();
    openUser();
    expect(within(account()).getByText("Temur")).toBeTruthy();
    expect(within(account()).getByText("+998901234567")).toBeTruthy();
    expect(within(account()).getByText("byDurii")).toBeTruthy();
  });

  it("ismi yo'q bo'lsa — telefon", async () => {
    await renderShell("/", { [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, name: null } }) });
    expect(topbar().getByRole("button", { name: "Hisob: +998901234567" })).toBeTruthy();
  });

  it("mavzu: tanlov data-theme va saqlashga yoziladi", async () => {
    await renderShell("/");
    openUser();
    const select = within(account()).getByLabelText("Mavzu") as HTMLSelectElement;
    expect(select.value).toBe("system");
    fireEvent.change(select, { target: { value: "dark" } });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("up.theme")).toBe("dark");
    fireEvent.change(select, { target: { value: "system" } });
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("til: butun karkas almashadi", async () => {
    await renderShell("/");
    openUser();
    fireEvent.change(within(account()).getByLabelText("Til"), { target: { value: "ru" } });
    expect(await within(await screen.findByRole("navigation", { name: "Главное меню" })).findByRole("link", { name: "Прибыль" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Нижнее меню" })).toBeTruthy();
    expect(topbar().getByRole("button", { name: /^Актуальность данных:/ })).toBeTruthy();
    expect(localStorage.getItem("up.lang")).toBe("ru");
  });

  it("chiqish: sessiya bekor, kesh tozalanadi, /login ga", async () => {
    const { api, history, state } = await renderShell("/pnl");
    openUser();
    fireEvent.click(within(account()).getByRole("button", { name: "Chiqish" }));
    await waitFor(() => expect(history.location.pathname).toBe("/login"));
    expect(api.count(LOGOUT_ROUTE)).toBe(1);
    // Kesh /login ga o'tilgandan KEYIN tozalanadi (useSignOut) — manzil o'zgargan zahoti emas, shuning uchun kutamiz.
    await waitFor(() => expect(state.queryClient.getQueryCache().getAll()).toHaveLength(0));
    expect(state.queryClient.getQueryData(meQuery.queryKey)).toBeUndefined();
  });

  it("chiqish muvaffaqiyatsiz — xabar, foydalanuvchi sahifada qoladi", async () => {
    const { history } = await renderShell("/pnl", { [LOGOUT_ROUTE]: () => problem(500, "internal") });
    openUser();
    fireEvent.click(within(account()).getByRole("button", { name: "Chiqish" }));
    expect(await screen.findByText("Chiqib boʻlmadi. Qayta urinib koʻring.")).toBeTruthy();
    expect(history.location.pathname).toBe("/pnl");
  });
});

describe("sidebar yig'ilishi", () => {
  const appRoot = () => document.querySelector(".app")!;

  it("yig'iladi va eslab qolinadi; yozuv ekran o'quvchi uchun qoladi", async () => {
    await renderShell("/");
    expect(appRoot().hasAttribute("data-collapsed")).toBe(false);
    const toggle = screen.getByRole("button", { name: "Menyuni yigʻish" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(toggle);
    expect(appRoot().hasAttribute("data-collapsed")).toBe(true);
    expect(localStorage.getItem("up.sidebar")).toBe("collapsed");
    expect(screen.getByRole("button", { name: "Menyuni yoyish" }).getAttribute("aria-pressed")).toBe("true");
    expect(sidebar().getByRole("link", { name: "Foyda" })).toBeTruthy();

    cleanup();
    await renderShell("/");
    expect(appRoot().hasAttribute("data-collapsed")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Menyuni yoyish" }));
    expect(appRoot().hasAttribute("data-collapsed")).toBe(false);
    expect(localStorage.getItem("up.sidebar")).toBe("expanded");
  });

  it("brauzer saqlashi yopiq bo'lsa ham ishlaydi", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("SecurityError");
      },
      removeItem: () => {
        throw new Error("SecurityError");
      },
    });
    await renderShell("/");
    fireEvent.click(screen.getByRole("button", { name: "Menyuni yigʻish" }));
    expect(appRoot().hasAttribute("data-collapsed")).toBe(true);
  });
});

describe("mobil tab bar", () => {
  it("Asosiy · Foyda · Ombor · Xaridlar · Yana", async () => {
    await renderShell("/pnl");
    expect(tabbar().getAllByRole("link").map((l) => l.textContent)).toEqual(["Asosiy", "Foyda", "Ombor", "Xaridlar"]);
    expect(tabbar().getByRole("button", { name: "Yana" })).toBeTruthy();
    expect(tabbar().getByRole("link", { name: "Foyda" }).getAttribute("aria-current")).toBe("page");
  });

  it("'Yana': qolgan bo'limlar; bosilsa o'tadi va panel yopiladi; 'Yana' faol bo'ladi", async () => {
    const { history } = await renderShell("/");
    fireEvent.click(tabbar().getByRole("button", { name: "Yana" }));
    const drawer = within(screen.getByRole("dialog", { name: "Yana" }));
    expect(drawer.getAllByRole("link").map((l) => l.textContent)).toEqual([
      "Mahsulotlar",
      "Buyurtmalar",
      "Xarajatlar",
      "Pul oqimi",
      "Hisobotlar",
      "Maʼlumotlar holati",
      "Sozlamalar",
    ]);
    fireEvent.click(drawer.getByRole("link", { name: "Xarajatlar" }));
    await screen.findByRole("heading", { name: "Xarajatlar" });
    expect(history.location.pathname).toBe("/expenses");
    expect(screen.queryByRole("dialog", { name: "Yana" })).toBeNull();
    expect(tabbar().getByRole("button", { name: "Yana" }).className).toContain("is-active");
  });

  it("'Yana' ichida solishtirish, ko'rinish va chiqish bor (topbar'da sig'maganlar)", async () => {
    const { history } = await renderShell("/");
    fireEvent.click(tabbar().getByRole("button", { name: "Yana" }));
    const drawer = within(screen.getByRole("dialog", { name: "Yana" }));
    fireEvent.click(drawer.getByRole("radio", { name: "Oldingi davr" }));
    expect(params(history).get("cmp")).toBe("previous");
    expect(drawer.getByLabelText("Mavzu")).toBeTruthy();
    expect(drawer.getByLabelText("Til")).toBeTruthy();
    expect(drawer.getByRole("button", { name: "Chiqish" })).toBeTruthy();
  });
});

describe("tashkilotsiz foydalanuvchi", () => {
  it("karkas o'rniga onboarding; tashkilotga tegishli so'rov ketmaydi", async () => {
    const api = mockApi({ [ME_ROUTE]: () => json(200, { ...ME, orgs: [] }) });
    const history = createMemoryHistory({ initialEntries: ["/pnl"] });
    render(<App state={createAppState(history, "uz-Latn")} />);
    expect(await screen.findByRole("heading", { name: "Biznesingiz nomi" })).toBeTruthy();
    expect(history.location.pathname).toBe("/onboarding");
    expect(screen.queryByRole("navigation", { name: "Asosiy menyu" })).toBeNull();
    expect(api.calls).toEqual([ME_ROUTE]);
  });
});

describe("kirish imkoniyati (axe-core: jiddiy xato 0)", () => {
  it("karkas, ochiq qatlamlar bilan", async () => {
    const { api } = await renderShell("/");
    await screen.findByRole("button", { name: /^Maʼlumot yangiligi:/ });
    expect(await serious()).toEqual([]);

    for (const name of [/^Doʻkon:/, /^Davr:/, "Solishtirish", /^Maʼlumot yangiligi:/, /^Hisob:/]) {
      open(name);
      expect(await serious(), String(name)).toEqual([]);
      open(name);
    }

    fireEvent.keyDown(window, { key: "k", code: "KeyK", ctrlKey: true });
    expect(await serious()).toEqual([]);
    fireEvent.change(screen.getByRole("combobox", { name: "Sahifa yoki amalni qidiring" }), { target: { value: "qqqq" } });
    expect(await serious()).toEqual([]);
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Sahifa yoki amalni qidiring" }), { key: "Escape" });

    fireEvent.click(tabbar().getByRole("button", { name: "Yana" }));
    expect(await serious()).toEqual([]);
    expect(api.unmocked).toEqual([]);
  }, 60_000);
});
