// Onboarding (M2): tashkilot → Uzum kaliti → do'konlar → tarix. Holat serverdan, istalgan joyda davom etish mumkin.
import { createMemoryHistory } from "@tanstack/react-router";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { onboardingSearch } from "../../app/search";
import type { components } from "../../lib/api/schema";
import {
  CONNECT_ROUTE,
  json,
  LOGOUT_ROUTE,
  ME,
  ME_ROUTE,
  mockApi,
  ORG_ID,
  ORGS_ROUTE,
  problem,
  SHOP_A,
  SHOP_B,
  SHOPS,
  SHOPS_ROUTE,
  shopRoute,
  SYNC_ROUTE,
  syncStatus,
  type Routes,
} from "../../test/api";
import { defaultColor, SHOP_COLORS } from "./ColorPicker";
import { allowedStep } from "./Onboarding";
import { shopChanges } from "./ShopsStep";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const NO_ORG = () => json(200, { ...ME, orgs: [] });
const AS_MANAGER = () => json(200, { ...ME, orgs: [{ ...ME.orgs[0], role: "manager" }] });
const EMPTY_SHOPS = () => json(200, []);

async function renderOnboarding(path: string, routes: Routes = {}, ready: string | RegExp = /./) {
  const api = mockApi(routes);
  const history = createMemoryHistory({ initialEntries: [path] });
  const state = createAppState(history, "uz-Latn");
  render(<App state={state} />);
  await screen.findByRole("heading", { level: 2, name: ready });
  return { api, history, state };
}

const search = (history: ReturnType<typeof createMemoryHistory>) => new URLSearchParams(history.location.search);
const serious = async () =>
  (await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } })).violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);

describe("qadamlarni tanlash", () => {
  const s = (hasOrg: boolean, hasShops: boolean) => ({ hasOrg, hasShops });

  it("allowedStep: har qadam oldingisining natijasiga tayanadi", () => {
    expect(allowedStep(undefined, s(false, false))).toBe("org");
    expect(allowedStep("history", s(false, false))).toBe("org");
    expect(allowedStep("key", s(false, false))).toBe("org");
    expect(allowedStep(undefined, s(true, false))).toBe("key");
    expect(allowedStep("shops", s(true, false))).toBe("key");
    expect(allowedStep("history", s(true, false))).toBe("key");
    expect(allowedStep(undefined, s(true, true))).toBe("shops"); // to'xtab, keyin davom etish
    expect(allowedStep("history", s(true, true))).toBe("history");
    expect(allowedStep("key", s(true, true))).toBe("key");
    expect(allowedStep("org", s(true, true))).toBe("org");
  });

  it("onboardingSearch: faqat ma'lum qadamlar", () => {
    expect(onboardingSearch({ step: "shops" })).toEqual({ step: "shops" });
    for (const bad of ["x", "", 3, null, undefined]) expect(onboardingSearch({ step: bad })).toEqual({});
  });

  it("URL'dagi noto'g'ri qadam e'tiborga olinmaydi (xom qidiruv ham)", async () => {
    await renderOnboarding("/onboarding?step=%3Cscript%3E", { [ME_ROUTE]: NO_ORG }, "Biznesingiz nomi");
  });

  it("tashkilot yo'q — 0-qadam; tashkilot bor, do'kon yo'q — kalit; do'kon bor — do'konlar (davom etish)", async () => {
    await renderOnboarding("/onboarding", { [ME_ROUTE]: NO_ORG }, "Biznesingiz nomi");
    cleanup();
    await renderOnboarding("/onboarding", { [SHOPS_ROUTE]: EMPTY_SHOPS }, "Uzum API kaliti");
    cleanup();
    await renderOnboarding("/onboarding", {}, "Doʻkonlarni tanlang");
  });

  it("qadamlar ro'yxati: bajarilgan / joriy / kelgusi; mobil progress", async () => {
    await renderOnboarding("/onboarding?step=key", { [SHOPS_ROUTE]: EMPTY_SHOPS }, "Uzum API kaliti");
    const steps = within(screen.getByRole("list", { name: "Qadamlar" })).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Biznes"),
      expect.stringContaining("Uzum kaliti"),
      expect.stringContaining("Doʻkonlar"),
      expect.stringContaining("Tarix"),
    ]);
    expect(steps.map((li) => li.className)).toEqual(["is-done", "is-current", "is-upcoming", "is-upcoming"]);
    expect(steps[1].getAttribute("aria-current")).toBe("step");
    const progress = screen.getByRole("progressbar", { name: "Qadam 2 / 4" });
    expect(progress.getAttribute("aria-valuenow")).toBe("2");
  });

  it("chiqish tugmasi bor (ish yarmida chiqib ketish mumkin)", async () => {
    const { api, history } = await renderOnboarding("/onboarding", { [ME_ROUTE]: NO_ORG }, "Biznesingiz nomi");
    fireEvent.click(screen.getByRole("button", { name: "Chiqish" }));
    await waitFor(() => expect(history.location.pathname).toBe("/login"));
    expect(api.count(LOGOUT_ROUTE)).toBe(1);
  });
});

describe("0-qadam: tashkilot", () => {
  it("nom majburiy, STIR — 9 raqam; tekshiruvdan o'tmasa so'rov ketmaydi", async () => {
    const { api } = await renderOnboarding("/onboarding", { [ME_ROUTE]: NO_ORG, [ORGS_ROUTE]: () => json(201, {}) }, "Biznesingiz nomi");
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect((await screen.findByText("Tashkilot nomini kiriting.")).getAttribute("role")).toBe("alert");
    fireEvent.change(screen.getByLabelText(/^Tashkilot nomi/), { target: { value: "Yangi biznes" } });
    fireEvent.change(screen.getByLabelText(/^STIR/), { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect(await screen.findByText("STIR 9 ta raqamdan iborat boʻlishi kerak.")).toBeTruthy();
    expect(api.count(ORGS_ROUTE)).toBe(0);
  });

  it("STIR faqat raqam qabul qiladi (9 tagacha)", async () => {
    await renderOnboarding("/onboarding", { [ME_ROUTE]: NO_ORG }, "Biznesingiz nomi");
    const inn = screen.getByLabelText(/^STIR/) as HTMLInputElement;
    fireEvent.change(inn, { target: { value: "12a3-45 678 9012" } });
    expect(inn.value).toBe("123456789");
  });

  it("saqlash: nom tozalanib yuboriladi, keyin tashkilot ro'yxatga tushadi va kalit qadamiga o'tadi", async () => {
    const { api, history } = await renderOnboarding(
      "/onboarding",
      {
        [ME_ROUTE]: [NO_ORG, () => json(200, ME)],
        [ORGS_ROUTE]: () => json(201, { id: ORG_ID, name: "Yangi biznes" }),
        [SHOPS_ROUTE]: EMPTY_SHOPS,
      },
      "Biznesingiz nomi",
    );
    fireEvent.change(screen.getByLabelText(/^Tashkilot nomi/), { target: { value: "  Yangi biznes  " } });
    fireEvent.change(screen.getByLabelText(/^STIR/), { target: { value: "123456789" } });
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Uzum API kaliti" })).toBeTruthy();
    expect(api.bodiesOf(ORGS_ROUTE)).toEqual([{ name: "Yangi biznes", inn: "123456789" }]);
    expect(search(history).get("step")).toBe("key");
  });

  it("STIR bo'sh — null; server xatosi ko'rsatiladi", async () => {
    const { api } = await renderOnboarding(
      "/onboarding",
      { [ME_ROUTE]: NO_ORG, [ORGS_ROUTE]: () => problem(403, "forbidden") },
      "Biznesingiz nomi",
    );
    fireEvent.change(screen.getByLabelText(/^Tashkilot nomi/), { target: { value: "X" } });
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect((await screen.findByRole("alert")).textContent).toContain("ruxsatingiz yoʻq");
    expect(api.bodiesOf(ORGS_ROUTE)).toEqual([{ name: "X", inn: null }]);
  });
});

describe("1-qadam: Uzum kaliti", () => {
  const KEY = "uzum-secret-key-1234567890";
  const account = { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", provider: "uzum", status: "active", key_hint: "…7890", checked_at: null, quota_remaining: null, created_at: "2026-10-26T00:00:00Z", shops: SHOPS };

  it("yo'riqnoma, xavfsizlik matni; kalit maydoni parol turida, avtoto'ldirishsiz", async () => {
    await renderOnboarding("/onboarding", { [SHOPS_ROUTE]: EMPTY_SHOPS }, "Uzum API kaliti");
    expect(screen.getByText(/shifrlab saqlanadi, parolingiz soʻralmaydi/)).toBeTruthy();
    expect(screen.getAllByRole("listitem").filter((li) => li.textContent?.includes("seller.uzum.uz"))).toHaveLength(1);
    const input = screen.getByLabelText(/^API kalit/) as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(input.getAttribute("autocomplete")).toBe("off");
    expect(input.getAttribute("spellcheck")).toBe("false");
  });

  it("bo'sh kalit — xato, so'rov ketmaydi", async () => {
    const { api } = await renderOnboarding("/onboarding", { [SHOPS_ROUTE]: EMPTY_SHOPS }, "Uzum API kaliti");
    fireEvent.click(screen.getByRole("button", { name: "Kalitni tekshirish va ulash" }));
    expect(await screen.findByText("Kalitni kiriting.")).toBeTruthy();
    expect(api.count(CONNECT_ROUTE)).toBe(0);
  });

  it("ulash: kalit tanada yuboriladi, URL'ga va ekranga tushmaydi; keyin do'konlar qadami", async () => {
    const { api, history } = await renderOnboarding(
      "/onboarding",
      { [SHOPS_ROUTE]: [EMPTY_SHOPS, () => json(200, SHOPS)], [CONNECT_ROUTE]: () => json(201, account) },
      "Uzum API kaliti",
    );
    fireEvent.change(screen.getByLabelText(/^API kalit/), { target: { value: KEY } });
    fireEvent.click(screen.getByRole("button", { name: "Kalitni tekshirish va ulash" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Doʻkonlarni tanlang" })).toBeTruthy();
    expect(api.bodiesOf(CONNECT_ROUTE)).toEqual([{ token: KEY }]);
    expect(history.location.href).not.toContain(KEY);
    expect(document.body.textContent).not.toContain(KEY);
    expect(search(history).get("step")).toBe("shops");
  });

  it.each([
    ["mp_token_invalid", 422, "Uzum kalitni rad etdi"],
    ["mp_shops_already_connected", 409, "boshqa tashkilotga ulangan"],
    ["mp_waf_blocked", 503, "Uzum soʻrovni vaqtincha toʻsdi"],
    ["mp_unavailable", 502, "Uzum javob bermayapti"],
  ])("%s — sabab va nima qilish kerakligi; kalit maydonda qoladi (xatoni tuzatish uchun)", async (code, status, text) => {
    await renderOnboarding("/onboarding", { [SHOPS_ROUTE]: EMPTY_SHOPS, [CONNECT_ROUTE]: () => problem(status, code) }, "Uzum API kaliti");
    const input = screen.getByLabelText(/^API kalit/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: KEY } });
    fireEvent.click(screen.getByRole("button", { name: "Kalitni tekshirish va ulash" }));
    expect((await screen.findByRole("alert")).textContent).toContain(text);
    expect(input.value).toBe(KEY);
    expect(document.body.textContent).not.toContain(KEY); // matnda emas, faqat maydon qiymatida
  });

  it("egasi bo'lmagan a'zo kalit ulay olmaydi: izoh va o'chirilgan maydon", async () => {
    const { api } = await renderOnboarding("/onboarding", { [ME_ROUTE]: AS_MANAGER, [SHOPS_ROUTE]: EMPTY_SHOPS }, "Uzum API kaliti");
    expect(screen.getByText(/faqat tashkilot egasi ulaydi/)).toBeTruthy();
    expect((screen.getByLabelText(/^API kalit/) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Kalitni tekshirish va ulash" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.count(CONNECT_ROUTE)).toBe(0);
  });
});

describe("2-qadam: do'konlar", () => {
  const patchRoutes = (): Routes => ({
    [shopRoute(SHOP_A)]: () => json(200, SHOPS[0]),
    [shopRoute(SHOP_B)]: () => json(200, SHOPS[1]),
  });
  const row = (name: string) => screen.getByRole("checkbox", { name: new RegExp(name) }).closest("li")!;

  it("shopChanges: faqat farq; bo'sh nom va rangning katta-kichik harfi o'zgarish emas", () => {
    const shop = SHOPS[0] as components["schemas"]["ShopOut"]; // alias "Durii", color "#2a78d6"
    expect(shopChanges(shop, { active: true, alias: "Durii", color: "#2A78D6" })).toEqual({});
    expect(shopChanges(shop, { active: true, alias: "  ", color: null })).toEqual({});
    expect(shopChanges(shop, { active: false, alias: " Yangi ", color: "#E34948" })).toEqual({ active: false, alias: "Yangi", color: "#E34948" });
  });

  it("defaultColor: 1-do'kon — 1-rang; 8 tadan keyin rangsiz (aylanib takrorlanmaydi)", () => {
    expect(defaultColor(0)).toBe(SHOP_COLORS[0]);
    expect(defaultColor(7)).toBe(SHOP_COLORS[7]);
    expect(defaultColor(8)).toBeNull();
  });

  it("hammasi belgilangan; faol do'kon uchun qisqa nom va rang maydonlari; standart rang tartib bo'yicha", async () => {
    await renderOnboarding("/onboarding", {}, "Doʻkonlarni tanlang");
    expect((screen.getByRole("checkbox", { name: /byDurii/ }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: /EL-ONE/ }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/Uzum ID: 135204/)).toBeTruthy();
    // 2-do'konda rang yo'q edi — 2-slot (to'q sariq) taklif qilinadi
    const checked = within(row("EL-ONE")).getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked);
    expect(checked).toHaveLength(1);
    expect((checked[0] as HTMLInputElement).value).toBe(SHOP_COLORS[1]);
    expect(within(row("EL-ONE")).getByLabelText(/^Qisqa nom/).getAttribute("placeholder")).toBe("EL-ONE");
    // rang nomlari matnda (rang yolg'iz emas)
    expect(within(row("EL-ONE")).getAllByRole("radio").map((r) => (r as HTMLInputElement).labels?.[0].textContent)).toEqual([
      "Koʻk", "Toʻq sariq", "Zangori-yashil", "Sariq", "Pushti", "Yashil", "Binafsha", "Qizil",
    ]);
  });

  it("saqlash: faqat o'zgargan do'konlar PATCH qilinadi; keyin tarix qadami", async () => {
    const { api, history } = await renderOnboarding("/onboarding", patchRoutes(), "Doʻkonlarni tanlang");
    fireEvent.change(within(row("EL-ONE")).getByLabelText(/^Qisqa nom/), { target: { value: "Elone" } });
    fireEvent.click(within(row("EL-ONE")).getByRole("radio", { name: "Qizil" }));
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Tarix yuklanmoqda" })).toBeTruthy();
    expect(api.count(shopRoute(SHOP_A))).toBe(0); // o'zgarmagan
    expect(api.bodiesOf(shopRoute(SHOP_B))).toEqual([{ alias: "Elone", color: SHOP_COLORS[7] }]);
    expect(search(history).get("step")).toBe("history");
  });

  it("do'konni o'chirish: faol=false yuboriladi, maydonlari yashiriladi", async () => {
    const { api } = await renderOnboarding("/onboarding", patchRoutes(), "Doʻkonlarni tanlang");
    fireEvent.click(screen.getByRole("checkbox", { name: /byDurii/ }));
    expect(within(row("byDurii")).queryByLabelText(/^Qisqa nom/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    await screen.findByRole("heading", { level: 2, name: "Tarix yuklanmoqda" });
    expect(api.bodiesOf(shopRoute(SHOP_A))).toEqual([{ active: false }]);
  });

  it("hammasini o'chirib bo'lmaydi: xato, so'rov ketmaydi", async () => {
    const { api } = await renderOnboarding("/onboarding", patchRoutes(), "Doʻkonlarni tanlang");
    fireEvent.click(screen.getByRole("checkbox", { name: /byDurii/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /EL-ONE/ }));
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Kamida bitta doʻkonni belgilang.");
    expect(api.calls.filter((c) => c.startsWith("PATCH"))).toEqual([]);
  });

  it("saqlash xatosi ko'rsatiladi, qadam o'zgarmaydi", async () => {
    const { history } = await renderOnboarding("/onboarding", { [shopRoute(SHOP_B)]: () => problem(403, "forbidden") }, "Doʻkonlarni tanlang");
    fireEvent.click(screen.getByRole("button", { name: "Davom etish" }));
    expect((await screen.findByRole("alert")).textContent).toContain("ruxsatingiz yoʻq");
    expect(search(history).get("step")).toBeNull();
  });
});

describe("3-qadam: tarix yuklanmoqda", () => {
  const kind = (over: Partial<components["schemas"]["KindStatus"]> & { kind: string }): components["schemas"]["KindStatus"] => ({
    last_success_at: null,
    last_attempt_at: null,
    status: "ok",
    mode: "history",
    started_at: null,
    finished_at: null,
    fetched: null,
    written: null,
    total: null,
    error: null,
    http_status: null,
    ...over,
  });
  const withKinds = (kinds: components["schemas"]["KindStatus"][], history_status: string | null = null) => {
    const base = syncStatus();
    return json(200, { ...base, shops: base.shops.map((s) => (s.id === SHOP_A ? { ...s, history_status, kinds } : { ...s, active: false })) });
  };
  const LOADING = [
    kind({ kind: "orders", status: "running", fetched: 1900, written: 1830, total: 2465 }),
    kind({ kind: "expenses", status: "ok", fetched: 203, written: 203, total: 203 }),
    kind({ kind: "products", status: "running", fetched: 40 }),
    kind({ kind: "invoices", status: "error", error: "Uzum 502" }),
  ];

  it("progress: har tur bo'yicha yozilgan/jami; jami yo'q bo'lsa — olingan soni; xato matni; faol emas do'kon ko'rinmaydi", async () => {
    await renderOnboarding("/onboarding?step=history", { [SYNC_ROUTE]: () => withKinds(LOADING) }, "Tarix yuklanmoqda");
    const orders = await screen.findByRole("progressbar", { name: "Sotuvlar" });
    expect(orders.getAttribute("aria-valuenow")).toBe("1830");
    expect(orders.getAttribute("aria-valuemax")).toBe("2465");
    expect(screen.getByRole("progressbar", { name: "Xarajatlar" }).getAttribute("aria-valuenow")).toBe("203");
    expect(screen.getByText("40 yozuv olindi")).toBeTruthy(); // jami noma'lum — yolg'on to'liq chiziq yo'q
    expect(screen.queryByRole("progressbar", { name: "Mahsulotlar" })).toBeNull();
    expect(screen.getByText("Uzum 502")).toBeTruthy();
    expect(screen.getByText("Yuklashda xato bor")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["byDurii"]); // EL-ONE faol emas
  });

  it("tugamagan: kutmasdan o'tish mumkin (ikkilamchi tugma), bosh sahifaga", async () => {
    const { history } = await renderOnboarding("/onboarding?step=history", { [SYNC_ROUTE]: () => withKinds(LOADING) }, "Tarix yuklanmoqda");
    expect(screen.queryByText("Tarix yuklandi")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Kutmasdan bosh sahifaga oʻtish" }));
    expect(await screen.findByRole("heading", { name: "SellerMax" })).toBeTruthy();
    expect(history.location.pathname).toBe("/");
  });

  it("tugagan (tarix yozilgan, hech narsa davom etmayapti): 'Tarix yuklandi' va asosiy tugma", async () => {
    await renderOnboarding(
      "/onboarding?step=history",
      { [SYNC_ROUTE]: () => withKinds([kind({ kind: "orders", fetched: 10, written: 10, total: 10 }), kind({ kind: "expenses", fetched: 5 })], "2020-01-01") },
      "Tarix yuklanmoqda",
    );
    expect(await screen.findByText("Tarix yuklandi")).toBeTruthy();
    const finish = screen.getByRole("button", { name: "Bosh sahifaga oʻtish" });
    expect(finish.className).toContain("ui-btn--primary");
    expect(screen.queryByText("Yuklashda xato bor")).toBeNull();
  });

  it("holat har 5 soniyada yangilanadi: progress o'sadi", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let written = 100;
    await renderOnboarding(
      "/onboarding?step=history",
      { [SYNC_ROUTE]: () => withKinds([kind({ kind: "orders", status: "running", written: (written += 700), total: 2465 })]) },
      "Tarix yuklanmoqda",
    );
    expect((await screen.findByRole("progressbar", { name: "Sotuvlar" })).getAttribute("aria-valuenow")).toBe("800");
    await act(async () => vi.advanceTimersByTime(5100));
    await waitFor(() => expect(screen.getByRole("progressbar", { name: "Sotuvlar" }).getAttribute("aria-valuenow")).toBe("1500"));
  });

  it("holat yuklanmasa — xato matni (sahifa buzilmaydi)", async () => {
    await renderOnboarding("/onboarding?step=history", { [SYNC_ROUTE]: () => problem(403, "forbidden") }, "Tarix yuklanmoqda");
    expect((await screen.findByRole("alert")).textContent).toContain("ruxsatingiz yoʻq");
  });
});

describe("kirish imkoniyati (axe-core: jiddiy xato 0)", () => {
  it("har qadam", async () => {
    await renderOnboarding("/onboarding", { [ME_ROUTE]: NO_ORG }, "Biznesingiz nomi");
    expect(await serious()).toEqual([]);
    cleanup();
    await renderOnboarding("/onboarding", { [SHOPS_ROUTE]: EMPTY_SHOPS, [CONNECT_ROUTE]: () => problem(422, "mp_token_invalid") }, "Uzum API kaliti");
    fireEvent.change(screen.getByLabelText(/^API kalit/), { target: { value: "abcdefghijk" } });
    fireEvent.click(screen.getByRole("button", { name: "Kalitni tekshirish va ulash" }));
    await screen.findByRole("alert");
    expect(await serious()).toEqual([]);
    cleanup();
    await renderOnboarding("/onboarding", {}, "Doʻkonlarni tanlang");
    expect(await serious()).toEqual([]);
    cleanup();
    await renderOnboarding("/onboarding?step=history", {}, "Tarix yuklanmoqda");
    await screen.findAllByRole("heading", { level: 3 });
    expect(await serious()).toEqual([]);
  }, 60_000);
});
