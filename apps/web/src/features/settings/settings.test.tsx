// Sozlamalar (M16, B4.8): tannarx usuli (tasdiq bilan), soliq profili (sana bo'yicha, rejimga mos maydonlar), Uzum
// to'lov jadvali, muddatlar va qamrov, do'konlar (faqat egasi), Uzum bonuslari ro'yxati (qo'shish, tahrirlash, o'chirish);
// ruxsatlar: buxgalter faqat ko'radi, omborchi — ruxsat yo'q. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { todayTashkent } from "../../lib/dates";
import {
  COST_METHOD_ROUTE,
  INVENTORY_SETTINGS_ROUTE,
  json,
  ME,
  ORG_ID,
  ME_ROUTE,
  mockApi,
  PAYOUT_CREATE_ROUTE,
  payoutDeleteRoute,
  problem,
  SETTINGS_ROUTE,
  SHOP_A,
  SHOPS,
  SHOPS_ROUTE,
  shopRoute,
  TAX_CREATE_ROUTE,
  taxRoute,
  waiverDeleteRoute,
  waiverPatchRoute,
  WAIVER_CREATE_ROUTE,
  WAIVERS_ROUTE,
  type Routes,
} from "../../test/api";
import { waiver } from "../../test/pnl";
import { legacyReport, PAY_1, settingsData, TAX_1, TAX_2 } from "../../test/settings";

const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const KINDS = ["sale_logistics", "advertising", "storage", "return_storage"];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderSettings(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [WAIVERS_ROUTE]: () =>
      json(200, {
        items: [
          waiver({ id: "w-old", start_on: "2026-08-10", end_on: "2026-08-12", reason: "Avgust" }),
          waiver({ id: "w-new", start_on: "2026-10-10", end_on: "2026-10-31", reason: "Oktabr kompensatsiyasi", source: "detected" }),
          waiver({ id: "w-dis", start_on: "2026-09-05", end_on: "2026-09-06", reason: "", dismissed: true }),
        ],
        kinds: KINDS,
      }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: ["/settings"] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;
const section = (name: string) => screen.getByRole("heading", { level: 2, name }).closest("section") as HTMLElement;
const rowsOf = (name: string) => within(within(section(name)).getByRole("table", { name })).getAllByRole("row").slice(1);

async function ready() {
  await screen.findByRole("heading", { level: 1, name: "Sozlamalar" });
  await screen.findByRole("table", { name: "Soliq profili" });
}

describe("sahifa", () => {
  it("hamma bo'lim; 'Qurilmoqda' yo'q; soliq profilida amaldagisi belgilanadi", async () => {
    await renderSettings();
    await ready();
    expect(screen.queryByText(/Sahifa qurilmoqda/)).toBeNull();
    for (const title of ["Tannarx usuli", "Soliq profili", "Uzum toʻlov jadvali", "Muddatlar va qamrov", "Doʻkonlar", "Uzum bonuslari"]) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeTruthy();
    }
    const [first, second] = rowsOf("Soliq profili");
    expect(norm(first!.textContent!)).toContain("Aylanmadan foiz");
    expect(norm(first!.textContent!)).toContain("Amalda");
    expect(norm(first!.textContent!)).toContain("baza: Uzum toʻlovi");
    expect(norm(second!.textContent!)).toContain("Soliq yoʻq");
    expect(norm(second!.textContent!)).not.toContain("Amalda");
  });

  it("to'lov jadvali: do'kon nomi, jadval turi va shartlar", async () => {
    await renderSettings();
    await ready();
    const [row] = rowsOf("Uzum toʻlov jadvali");
    const text = norm(row!.textContent!);
    expect(text).toContain("Durii");
    expect(text).toContain("Haftalik");
    expect(text).toContain("Oy kunlari: 7, 14, 21, 28");
  });

  it("xato (ruxsat yo'q) — xato bannerida sabab", async () => {
    await renderSettings({ [SETTINGS_ROUTE]: () => problem(403, "forbidden") }, "warehouse");
    expect(await screen.findByRole("button", { name: "Qayta urinish" })).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 2, name: "Soliq profili" })).toBeNull();
  });
});

describe("tannarx usuli", () => {
  it("o'zgartirmaguncha saqlab bo'lmaydi; almashtirish tasdiqdan keyin PUT yuboradi", async () => {
    const { api } = await renderSettings({ [COST_METHOD_ROUTE]: () => json(200, settingsData({ cost_method: "average" })) });
    await ready();
    const box = section("Tannarx usuli");
    const save = within(box).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(within(box).getByLabelText("Usul"), { target: { value: "average" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    const dialog = await screen.findByRole("dialog", { name: "Tannarx usulini almashtirish" });
    expect(dialog.textContent).toContain("Oʻrtacha (harakatlanuvchi)");
    expect(api.count(COST_METHOD_ROUTE)).toBe(0); // tasdiqsiz yuborilmaydi
    fireEvent.click(within(dialog).getByRole("button", { name: "Almashtirish" }));
    await waitFor(() => expect(bodiesOf(api, COST_METHOD_ROUTE)).toEqual([{ cost_method: "average" }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("soliq profili", () => {
  it("qo'shish: aylanma — stavka kiritilmaguncha saqlab bo'lmaydi; tana to'g'ri; ro'yxat javobdan yangilanadi", async () => {
    const created = settingsData();
    created.tax_profiles = [{ id: "73333333-3333-4333-8333-333333333333", valid_from: "2026-10-31", regime: "turnover", rate_pct: "1.000", base: "revenue", vat_pct: "0.000", profit_pct: "0.000" }, ...created.tax_profiles];
    const { api } = await renderSettings({ [TAX_CREATE_ROUTE]: () => json(201, created) });
    await ready();
    fireEvent.click(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi soliq profili" });
    const save = within(dialog).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(dialog.textContent).toContain("Maʼlumotnomada: 4%"); // tavsiya
    fireEvent.change(within(dialog).getByLabelText(/^Stavka/), { target: { value: "1" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, TAX_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, TAX_CREATE_ROUTE)[0]).toEqual({ valid_from: todayTashkent(), regime: "turnover", rate_pct: "1", base: "revenue", vat_pct: "0", profit_pct: "0" });
    await waitFor(() => expect(rowsOf("Soliq profili")).toHaveLength(3));
  });

  it("rejimga mos maydonlar: QQS + foyda — ikki stavka; agent — stavkasiz", async () => {
    const { api } = await renderSettings({ [TAX_CREATE_ROUTE]: () => json(201, settingsData()) });
    await ready();
    fireEvent.click(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi soliq profili" });
    fireEvent.change(within(dialog).getByLabelText("Rejim"), { target: { value: "vat_profit" } });
    expect(within(dialog).queryByLabelText(/^Stavka/)).toBeNull();
    fireEvent.change(within(dialog).getByLabelText(/^QQS stavkasi/), { target: { value: "12" } });
    fireEvent.change(within(dialog).getByLabelText(/^Foyda soligʻi stavkasi/), { target: { value: "15" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, TAX_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, TAX_CREATE_ROUTE)[0]).toMatchObject({ regime: "vat_profit", vat_pct: "12", profit_pct: "15", rate_pct: "0" });
  });

  it("tahrirlash PATCH yuboradi; o'chirish — tasdiqdan keyin DELETE", async () => {
    const { api } = await renderSettings({
      [taxRoute("PATCH", TAX_2)]: () => json(200, settingsData()),
      [taxRoute("DELETE", TAX_1)]: () => json(200, settingsData({ tax_profiles: [settingsData().tax_profiles[0]!] })),
    });
    await ready();
    const [first, second] = rowsOf("Soliq profili");
    fireEvent.click(within(first!).getByRole("button", { name: "Tahrirlash" }));
    const dialog = await screen.findByRole("dialog", { name: "Soliq profilini tahrirlash" });
    expect((within(dialog).getByLabelText(/^Stavka/) as HTMLInputElement).value).toBe("4");
    fireEvent.change(within(dialog).getByLabelText(/^Stavka/), { target: { value: "5" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, taxRoute("PATCH", TAX_2))).toHaveLength(1));
    expect(bodiesOf(api, taxRoute("PATCH", TAX_2))[0]).toMatchObject({ regime: "turnover", rate_pct: "5", base: "payout", valid_from: "2026-07-01" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(within(second!).getByRole("button", { name: "O‘chirish".replace("‘", "ʻ") }));
    const confirm = await screen.findByRole("dialog", { name: "Soliq profilini oʻchirish" });
    expect(api.count(taxRoute("DELETE", TAX_1))).toBe(0);
    fireEvent.click(within(confirm).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.count(taxRoute("DELETE", TAX_1))).toBe(1));
    await waitFor(() => expect(rowsOf("Soliq profili")).toHaveLength(1));
  });

  it("server xatosi (sana band) — bildirishnoma, forma ochiq qoladi", async () => {
    await renderSettings({ [TAX_CREATE_ROUTE]: () => problem(409, "tax_profile_exists") });
    await ready();
    fireEvent.click(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi soliq profili" });
    fireEvent.change(within(dialog).getByLabelText(/^Stavka/), { target: { value: "4" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(document.querySelector(".ui-toasts .ui-tone--negative")).not.toBeNull());
    expect(screen.getByRole("dialog", { name: "Yangi soliq profili" })).toBeTruthy();
  });
});

describe("to'lov jadvali", () => {
  it("qo'shish: do'kon, jadval, sana — POST; o'chirish tasdiq bilan", async () => {
    const { api } = await renderSettings({
      [PAYOUT_CREATE_ROUTE]: () => json(201, settingsData()),
      [payoutDeleteRoute(PAY_1)]: () => json(200, settingsData({ payout_schedules: [] })),
    });
    await ready();
    fireEvent.click(within(section("Uzum toʻlov jadvali")).getByRole("button", { name: "Jadval qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi toʻlov jadvali" });
    await within(dialog).findByRole("option", { name: "Durii" });
    fireEvent.change(within(dialog).getByLabelText("Jadval"), { target: { value: "monthly" } });
    fireEvent.change(within(dialog).getByLabelText("Qaysi sanadan"), { target: { value: "2026-11-01" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, PAYOUT_CREATE_ROUTE)).toEqual([{ shop_id: SHOP_A, kind: "monthly", valid_from: "2026-11-01" }]));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(within(rowsOf("Uzum toʻlov jadvali")[0]!).getByRole("button", { name: "Oʻchirish" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "Toʻlov jadvalini oʻchirish" })).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.count(payoutDeleteRoute(PAY_1))).toBe(1));
    expect(await screen.findByText("Toʻlov jadvali kiritilmagan")).toBeTruthy();
  });
});

describe("muddatlar va qamrov", () => {
  it("qisman to'ldirish — ogohlantirish va saqlab bo'lmaydi; to'liq — PUT; standartga qaytarish — bo'sh tana", async () => {
    const saved = settingsData();
    saved.inventory = { ...saved.inventory, lead_days: { prep: 8, china: 2, cargo: 13, receive: 7, handover: 2 }, cover_days: { A: 45, B: 30, C: 14 } };
    const { api } = await renderSettings({ [INVENTORY_SETTINGS_ROUTE]: [() => json(200, saved), () => json(200, settingsData())] });
    await ready();
    const box = section("Muddatlar va qamrov");
    const save = within(box).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false); // hammasi bo'sh — sozlanmagan, qamrov standart: to'g'ri
    fireEvent.change(within(box).getByLabelText(/^Tayyorlash/), { target: { value: "8" } });
    expect(save.disabled).toBe(true);
    expect(within(box).getByText("Muddatlarni hammasini kiriting yoki hammasini boʻsh qoldiring.")).toBeTruthy();
    for (const [label, value] of [["Xitoy ichida", "2"], ["Kargo yoʻli", "13"], ["Qabul va yorliq", "7"], ["Uzumga topshirish", "2"]] as const) {
      fireEvent.change(within(box).getByLabelText(new RegExp(`^${label}`)), { target: { value } });
    }
    fireEvent.change(within(box).getByLabelText("A sinfi"), { target: { value: "45" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, INVENTORY_SETTINGS_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, INVENTORY_SETTINGS_ROUTE)[0]).toEqual({ lead_days: { prep: 8, china: 2, cargo: 13, receive: 7, handover: 2 }, cover_days: { A: 45, B: 30, C: 14 } });

    fireEvent.click(within(box).getByRole("button", { name: "Standartga qaytarish" }));
    await waitFor(() => expect(bodiesOf(api, INVENTORY_SETTINGS_ROUTE)).toHaveLength(2));
    expect(bodiesOf(api, INVENTORY_SETTINGS_ROUTE)[1]).toEqual({});
    await waitFor(() => expect((within(box).getByLabelText("A sinfi") as HTMLInputElement).value).toBe("60"));
    expect((within(box).getByLabelText(/^Tayyorlash/) as HTMLInputElement).value).toBe("");
  });
});

describe("do'konlar", () => {
  it("egasi nom, rang va holatni o'zgartiradi (faqat o'zgarganlari yuboriladi)", async () => {
    const { api } = await renderSettings({ [shopRoute(SHOP_A)]: () => json(200, { ...SHOPS[0]!, alias: "Asosiy" }) });
    await ready();
    const box = section("Doʻkonlar");
    expect(norm(box.textContent!)).toContain("Durii");
    expect(norm(box.textContent!)).toContain("EL-ONE");
    fireEvent.click(within(box).getAllByRole("button", { name: "Tahrirlash" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Doʻkon: byDurii" });
    const save = within(dialog).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Qisqa nom/), { target: { value: "Asosiy" } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, shopRoute(SHOP_A))).toEqual([{ alias: "Asosiy" }]));
  });

  it("oxirgi faol do'konni o'chirib bo'lmaydi", async () => {
    await renderSettings({ [SHOPS_ROUTE]: () => json(200, [SHOPS[0]!, { ...SHOPS[1]!, active: false }]) });
    await ready();
    fireEvent.click(within(section("Doʻkonlar")).getAllByRole("button", { name: "Tahrirlash" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "Doʻkon: byDurii" });
    expect((within(dialog).getByLabelText(/Hisobga olinsin/) as HTMLInputElement).disabled).toBe(true);
    expect(dialog.textContent).toContain("Kamida bitta doʻkon faol boʻlishi kerak.");
  });
});

describe("Uzum bonuslari", () => {
  it("ro'yxat: yangisi tepada, rad etilgan belgisi, rad etilganda 'Tahrirlash' yo'q", async () => {
    await renderSettings();
    await ready();
    await waitFor(() => expect(rowsOf("Uzum bonuslari")).toHaveLength(3));
    const rows = rowsOf("Uzum bonuslari").map((r) => norm(r.textContent!));
    expect(rows[0]).toContain("Oktabr kompensatsiyasi");
    expect(rows[0]).toContain("Tizim taklifi (tasdiqlangan)");
    expect(rows[1]).toContain("Rad etilgan");
    expect(rows[2]).toContain("Avgust");
    expect(rows[2]).toContain("Qoʻlda");
    expect(within(rowsOf("Uzum bonuslari")[1]!).queryByRole("button", { name: "Tahrirlash" })).toBeNull();
    expect(within(rowsOf("Uzum bonuslari")[1]!).getByRole("button", { name: "Oʻchirish" })).toBeTruthy();
  });

  it("qo'shish POST, tahrirlash PATCH (to'g'ri tana), o'chirish — tasdiqdan keyin DELETE", async () => {
    const { api } = await renderSettings({
      [WAIVER_CREATE_ROUTE]: () => json(201, waiver()),
      [waiverPatchRoute("w-new")]: () => json(200, waiver({ id: "w-new" })),
      [waiverDeleteRoute("w-old")]: () => new Response(null, { status: 204 }),
    });
    await ready();
    await waitFor(() => expect(rowsOf("Uzum bonuslari")).toHaveLength(3));
    const box = section("Uzum bonuslari");
    fireEvent.click(within(box).getAllByRole("button", { name: "Bonus qoʻshish" })[0]!);
    const add = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    fireEvent.change(within(add).getByLabelText(/^Sabab/), { target: { value: "Yangi" } });
    fireEvent.click(within(add).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, WAIVER_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, WAIVER_CREATE_ROUTE)[0]).toMatchObject({ shop_id: null, kinds: ["sale_logistics"], reason: "Yangi", source: "manual", dismissed: false });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(within(rowsOf("Uzum bonuslari")[0]!).getByRole("button", { name: "Tahrirlash" }));
    const edit = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    expect((within(edit).getByLabelText(/^Sabab/) as HTMLInputElement).value).toBe("Oktabr kompensatsiyasi");
    fireEvent.change(within(edit).getByLabelText(/^Sabab/), { target: { value: "Tuzatildi" } });
    fireEvent.click(within(edit).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, waiverPatchRoute("w-new"))).toHaveLength(1));
    expect(bodiesOf(api, waiverPatchRoute("w-new"))[0]).toEqual({ shop_id: null, start_on: "2026-10-10", end_on: "2026-10-31", kinds: ["sale_logistics", "storage"], reason: "Tuzatildi" });
    expect(api.count(WAIVER_CREATE_ROUTE)).toBe(1); // tahrirlash yangi yozuv yaratmaydi
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(within(rowsOf("Uzum bonuslari")[2]!).getByRole("button", { name: "Oʻchirish" }));
    const confirm = await screen.findByRole("dialog", { name: "Bonus davrini oʻchirish" });
    expect(api.count(waiverDeleteRoute("w-old"))).toBe(0);
    fireEvent.click(within(confirm).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(api.count(waiverDeleteRoute("w-old"))).toBe(1));
  });

  it("bo'sh holat: taklif va qo'shish tugmasi", async () => {
    await renderSettings({ [WAIVERS_ROUTE]: () => json(200, { items: [], kinds: KINDS }) });
    expect(await screen.findByText("Bonus davrlari yoʻq")).toBeTruthy();
    expect(within(section("Uzum bonuslari")).getAllByRole("button", { name: "Bonus qoʻshish" })).toHaveLength(2);
  });
});

describe("Legacy import", () => {
  const ROUTE = `POST /api/v1/orgs/${ORG_ID}/imports/legacy`;
  const pick = (name = "uzum.db") => {
    const input = section("Eski dasturdan koʻchirish").querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["SQLite format 3"], name, { type: "application/octet-stream" })] } });
  };
  const legacyRows = () => within(within(section("Eski dasturdan koʻchirish")).getByRole("table", { name: "Eski dastur partiyalari" })).getAllByRole("row").slice(1);
  const urls = (api: ReturnType<typeof mockApi>) =>
    api.fetch.mock.calls.map(([r]) => new URL((r as Request).url)).filter((u) => u.pathname.endsWith("/imports/legacy"));

  it("fayl tanlansa ko'rib chiqish (dry run), keyin import; hisobot jadvali va eslatmalar", async () => {
    const { api } = await renderSettings({
      [ROUTE]: [
        () => json(200, legacyReport()),
        () => json(200, legacyReport({ dry_run: false, batches: [legacyReport().batches[0]!, legacyReport().batches[1]!].map((b, i) => (i === 0 ? { ...b, purchase_id: "94444444-4444-4444-8444-444444444444" } : b)) })),
      ],
    });
    await ready();
    pick();
    await waitFor(() => expect(api.calls.filter((c) => c === ROUTE)).toHaveLength(1));
    const rows = await waitFor(() => legacyRows());
    expect(rows).toHaveLength(2);
    const first = norm(rows[0]!.textContent ?? "");
    expect(first).toContain("Iyul partiyasi");
    expect(first).toContain("#1");
    expect(first).toContain("Yangi");
    expect(first).toContain("Bir xil");
    expect(norm(rows[1]!.textContent ?? "")).toContain("Farq bor");
    expect(within(rows[1]!).getByRole("link", { name: "Legacy #2" })).toBeTruthy();
    const sec = section("Eski dasturdan koʻchirish");
    expect(within(sec).getByText(/Koʻrib chiqish: uzum.db/)).toBeTruthy();
    expect(within(sec).getByText(/Ulanmagan doʻkon: EL-ONE \(135204\)/)).toBeTruthy();
    expect(within(sec).getByText(/#1: SKU topilmadi — «yangi tovar» boʻlib qoldi: Yoʻq-SKU/)).toBeTruthy();
    expect(within(sec).getByText(/#1: 1 ta SKU tovarga bogʻlanmagan edi/)).toBeTruthy();
    expect(urls(api).map((u) => u.searchParams.get("dry_run"))).toEqual(["true"]);
    const req = api.fetch.mock.calls.map(([r]) => r as Request).find((r) => r.url.includes("/imports/legacy"))!;
    expect(req.headers.get("Content-Type")).toBe("application/octet-stream");
    expect(req.headers.get("X-Requested-With")).toBe("web");

    fireEvent.click(within(sec).getByRole("button", { name: "Import qilish (1)" }));
    await waitFor(() => expect(within(section("Eski dasturdan koʻchirish")).getAllByText("1 ta xarid yaratildi").length).toBeGreaterThan(0));
    expect(urls(api).map((u) => u.searchParams.get("dry_run"))).toEqual(["true", "false"]);
    expect(within(section("Eski dasturdan koʻchirish")).getByRole("link", { name: "Xaridlarga oʻtish" })).toBeTruthy();
    expect(within(legacyRows()[0]!).getByRole("link", { name: "Iyul partiyasi" })).toBeTruthy();
  });

  it("yangi partiya yo'q — import tugmasi o'chiq; noto'g'ri fayl — xato xabari", async () => {
    await renderSettings({
      [ROUTE]: [() => json(200, legacyReport({ created: 0, mismatched: 0, batches: [] })), () => problem(422, "bad_legacy_file")],
    });
    await ready();
    pick();
    expect(await screen.findByText("Faylda partiya yoʻq")).toBeTruthy();
    expect((within(section("Eski dasturdan koʻchirish")).getByRole("button", { name: "Import qilish (0)" }) as HTMLButtonElement).disabled).toBe(true);
    pick("rasm.png");
    expect(await screen.findByText(/Fayl eski dastur bazasi emas yoki buzilgan/)).toBeTruthy();
  });
});

describe("rollar", () => {
  it("buxgalter faqat ko'radi: o'zgartirish tugmalari yo'q, izoh bor", async () => {
    await renderSettings({}, "accountant");
    await ready();
    await waitFor(() => expect(rowsOf("Uzum bonuslari")).toHaveLength(3));
    expect(screen.getByText("Sozlamalarni faqat koʻrasiz")).toBeTruthy();
    for (const name of ["Profil qoʻshish", "Jadval qoʻshish", "Bonus qoʻshish", "Tahrirlash", "Oʻchirish", "Saqlash", "Standartga qaytarish"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("heading", { level: 2, name: "Eski dasturdan koʻchirish" })).toBeNull();
  });

  it("menejer sozlaydi, lekin do'kon tahrirlash — faqat egasi", async () => {
    await renderSettings({}, "manager");
    await ready();
    expect(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" })).toBeTruthy();
    expect(within(section("Doʻkonlar")).queryByRole("button", { name: "Tahrirlash" })).toBeNull();
  });
});

it("a11y: jiddiy buzilish yo'q", async () => {
  await renderSettings();
  await ready();
  await waitFor(() => expect(rowsOf("Uzum bonuslari")).toHaveLength(3));
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
