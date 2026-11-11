// Sozlamalar (M16, B4.8): tannarx usuli (tasdiq bilan), soliq profili (sana bo'yicha, rejimga mos maydonlar), Uzum
// to'lov jadvali, muddatlar va qamrov, do'konlar (faqat egasi); Uzum bonuslari bo'limi yo'q (ADR-035);
// ruxsatlar: buxgalter faqat ko'radi, omborchi — ruxsat yo'q. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { todayTashkent } from "../../lib/dates";
import { formatterFor } from "../../lib/format";
import {
  ALERT_SETTINGS_ROUTE,
  COST_METHOD_ROUTE,
  INVENTORY_SETTINGS_ROUTE,
  json,
  ME,
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
  type Routes,
} from "../../test/api";
import { PAY_1, settingsData, TAX_1, TAX_2 } from "../../test/settings";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderSettings(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
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
    for (const title of ["Tannarx usuli", "Soliq profili", "Uzum toʻlov jadvali", "Muddatlar va qamrov", "Ogohlantirish chegaralari", "Doʻkonlar"]) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeTruthy();
    }
    expect(screen.queryByRole("heading", { level: 2, name: "Uzum bonuslari" })).toBeNull();
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
  const openCreate = async () => {
    fireEvent.click(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" }));
    return screen.findByRole("dialog", { name: "Yangi soliq profili" });
  };
  const pickTemplate = (dialog: HTMLElement, value: string) => fireEvent.change(within(dialog).getByLabelText("Tayyor shablon"), { target: { value } });

  it("qo'shish: aylanma — qator kiritilmaguncha saqlab bo'lmaydi; YaTT shabloni (1% + 1 BHM) bir bosishda; tana to'g'ri; ro'yxat javobdan yangilanadi", async () => {
    const created = settingsData();
    created.tax_profiles = [{ id: "73333333-3333-4333-8333-333333333333", valid_from: "2026-10-31", regime: "turnover", rate_pct: "0.000", base: "revenue", vat_pct: "0.000", profit_pct: "0.000", lines: [] }, ...created.tax_profiles];
    const { api } = await renderSettings({ [TAX_CREATE_ROUTE]: () => json(201, created) });
    await ready();
    const dialog = await openCreate();
    const save = within(dialog).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(dialog.textContent).toContain("Qator yo‘q".replace("‘", "ʻ"));
    pickTemplate(dialog, "yatt");
    const percent = within(dialog).getByRole("group", { name: "Soliq qatori 1" });
    const social = within(dialog).getByRole("group", { name: "Soliq qatori 2" });
    expect((within(percent).getByLabelText("Nomi") as HTMLInputElement).value).toBe("Aylanmadan soliq");
    expect((within(percent).getByLabelText(/^Stavka/) as HTMLInputElement).value).toBe("1"); // maʼlumotnomadan
    expect((within(social).getByLabelText("Nomi") as HTMLInputElement).value).toBe("Ijtimoiy soliq");
    expect((within(social).getByLabelText("BHM soni") as HTMLInputElement).value).toBe("1");
    expect(norm(social.textContent!)).toContain(`1 BHM = ${norm(f.money("440000.00"))}`); // BHM maʼlumotnomadan ko'rsatiladi
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, TAX_CREATE_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, TAX_CREATE_ROUTE)[0]).toEqual({
      valid_from: todayTashkent(),
      regime: "turnover",
      rate_pct: "0",
      base: "revenue",
      vat_pct: "0",
      profit_pct: "0",
      lines: [
        { name: "Aylanmadan soliq", kind: "percent", rate_pct: "1", base: "revenue", period: "month" },
        { name: "Ijtimoiy soliq", kind: "fixed", rate_pct: "0", base: "revenue", period: "month", bhm_count: "1" },
      ],
    });
    await waitFor(() => expect(rowsOf("Soliq profili")).toHaveLength(3));
  });

  it("qatorlarni qo'lda boshqarish: qo'shish, turi (foizli ↔ qat'iy), so'm yoki BHM, davr, o'chirish, 10 tadan oshmaydi", async () => {
    const { api } = await renderSettings({ [TAX_CREATE_ROUTE]: () => json(201, settingsData()) });
    await ready();
    const dialog = await openCreate();
    const save = within(dialog).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Qator qoʻshish" }));
    const line = within(dialog).getByRole("group", { name: "Soliq qatori 1" });
    expect(norm(line.textContent!)).toContain("Toʻldirilmagan yoki notoʻgʻri");
    expect(save.disabled).toBe(true);
    fireEvent.change(within(line).getByLabelText("Nomi"), { target: { value: "Ijtimoiy soliq" } });
    fireEvent.change(within(line).getByLabelText("Turi"), { target: { value: "fixed" } });
    expect(within(line).queryByLabelText(/^Stavka/)).toBeNull();
    fireEvent.change(within(line).getByLabelText("Qanday kiritiladi"), { target: { value: "sum" } });
    fireEvent.change(within(line).getByLabelText("Summa"), { target: { value: "310000" } });
    fireEvent.change(within(line).getByLabelText("Davr"), { target: { value: "quarter" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, TAX_CREATE_ROUTE)).toHaveLength(1));
    expect((bodiesOf(api, TAX_CREATE_ROUTE)[0] as { lines: unknown }).lines).toEqual([
      { name: "Ijtimoiy soliq", kind: "fixed", rate_pct: "0", base: "revenue", period: "quarter", amount: "310000" },
    ]);
  });

  it("takror nom saqlashga yo'l qo'ymaydi; qatorni o'chirish; 10 ta qatordan keyin 'Qator qo'shish' o'chadi", async () => {
    await renderSettings();
    await ready();
    const dialog = await openCreate();
    const save = within(dialog).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    const add = within(dialog).getByRole("button", { name: "Qator qoʻshish" }) as HTMLButtonElement;
    fireEvent.click(add);
    fireEvent.click(add);
    for (const n of [1, 2]) {
      const line = within(dialog).getByRole("group", { name: `Soliq qatori ${n}` });
      fireEvent.change(within(line).getByLabelText("Nomi"), { target: { value: n === 1 ? "Soliq" : "SOLIQ" } });
      fireEvent.change(within(line).getByLabelText(/^Stavka/), { target: { value: "1" } });
    }
    expect(save.disabled).toBe(true); // nomlar takrorlandi (katta-kichik harfsiz)
    fireEvent.click(within(within(dialog).getByRole("group", { name: "Soliq qatori 2" })).getByRole("button", { name: "Qatorni oʻchirish" }));
    expect(within(dialog).queryByRole("group", { name: "Soliq qatori 2" })).toBeNull();
    expect(save.disabled).toBe(false);
    for (let i = 0; i < 9; i += 1) fireEvent.click(add);
    expect(within(dialog).getAllByRole("group", { name: /^Soliq qatori \d+$/ })).toHaveLength(10);
    expect(add.disabled).toBe(true);
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
    const line = within(dialog).getByRole("group", { name: "Soliq qatori 1" }); // qatorsiz eski profil — bitta foizli qator
    expect((within(line).getByLabelText(/^Stavka/) as HTMLInputElement).value).toBe("4");
    fireEvent.change(within(line).getByLabelText(/^Stavka/), { target: { value: "5" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(bodiesOf(api, taxRoute("PATCH", TAX_2))).toHaveLength(1));
    expect(bodiesOf(api, taxRoute("PATCH", TAX_2))[0]).toMatchObject({
      regime: "turnover",
      rate_pct: "0",
      valid_from: "2026-07-01",
      lines: [{ name: "Aylanmadan soliq", kind: "percent", rate_pct: "5", base: "payout", period: "month" }],
    });
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
    pickTemplate(dialog, "ecommerce");
    fireEvent.click(within(dialog).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(document.querySelector(".ui-toasts .ui-tone--negative")).not.toBeNull());
    expect(screen.getByRole("dialog", { name: "Yangi soliq profili" })).toBeTruthy();
  });
});

describe("soliq profili jadvali: qatorlar tavsifi", () => {
  it("qatorli profil — qatorlar yig'indisi matni; qatorsiz eski aylanma — stavka va baza", async () => {
    const data = settingsData();
    data.tax_profiles = [
      {
        ...data.tax_profiles[0]!,
        rate_pct: "0.000",
        lines: [
          { id: "L1", name: "Aylanmadan soliq", kind: "percent", rate_pct: "1.0000", base: "revenue", amount: null, bhm_count: null, period: "month" },
          { id: "L2", name: "Ijtimoiy soliq", kind: "fixed", rate_pct: "0.0000", base: "revenue", amount: null, bhm_count: "1.00", period: "month" },
          { id: "L3", name: "Qat'iy", kind: "fixed", rate_pct: "0.0000", base: "revenue", amount: "310000.00", bhm_count: null, period: "quarter" },
        ],
      },
      data.tax_profiles[1]!,
    ];
    await renderSettings({ [SETTINGS_ROUTE]: () => json(200, data) });
    await ready();
    const text = norm(rowsOf("Soliq profili")[0]!.textContent!);
    expect(text).toContain("Aylanmadan soliq 1% (Tushum) · Ijtimoiy soliq 1 × BHM oyiga · Qat'iy");
    expect(text).toContain("chorakka");
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

describe("ogohlantirish chegaralari (ADR-043)", () => {
  it("foizda kiritiladi, ulush bo'lib yuboriladi; bo'sh — o'chirish; 100% dan katta — saqlab bo'lmaydi", async () => {
    const saved = settingsData({ alerts: { cancel_share: "0.300000", return_share: null } });
    const { api } = await renderSettings({ [ALERT_SETTINGS_ROUTE]: () => json(200, saved) });
    await ready();
    const box = section("Ogohlantirish chegaralari");
    const save = within(box).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    const cancel = within(box).getByLabelText(/^Bekor boʻlish ulushi/) as HTMLInputElement;
    expect(cancel.value).toBe("");
    fireEvent.change(cancel, { target: { value: "120" } });
    expect(save.disabled).toBe(true);
    expect(within(box).getByText("Chegara 0 dan katta va 100% dan oshmasligi kerak.")).toBeTruthy();
    fireEvent.change(cancel, { target: { value: "30" } });
    fireEvent.change(within(box).getByLabelText(/^Qaytarilish ulushi/), { target: { value: "7,5" } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, ALERT_SETTINGS_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, ALERT_SETTINGS_ROUTE)[0]).toEqual({ cancel_share: "0.3", return_share: "0.075" });
  });

  it("saqlangan chegara foizda ko'rinadi; buxgalter faqat ko'radi", async () => {
    await renderSettings({ [SETTINGS_ROUTE]: () => json(200, settingsData({ alerts: { cancel_share: "0.250000", return_share: "0.050000" } })) }, "accountant");
    await ready();
    const box = section("Ogohlantirish chegaralari");
    expect((within(box).getByLabelText(/^Bekor boʻlish ulushi/) as HTMLInputElement).value).toBe("25");
    expect((within(box).getByLabelText(/^Qaytarilish ulushi/) as HTMLInputElement).value).toBe("5");
    expect(within(box).queryByRole("button", { name: "Saqlash" })).toBeNull();
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

describe("rollar", () => {
  it("buxgalter faqat ko'radi: o'zgartirish tugmalari yo'q, izoh bor", async () => {
    await renderSettings({}, "accountant");
    await ready();
    await waitFor(() => expect(within(section("Doʻkonlar")).getAllByRole("row").length).toBeGreaterThan(1));
    expect(screen.getByText("Sozlamalarni faqat koʻrasiz")).toBeTruthy();
    for (const name of ["Profil qoʻshish", "Jadval qoʻshish", "Tahrirlash", "Oʻchirish", "Saqlash", "Standartga qaytarish"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
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
  await waitFor(() => expect(within(section("Doʻkonlar")).getAllByRole("row").length).toBeGreaterThan(1));
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

it("a11y: soliq profili formasi (qatorlar bilan) — jiddiy buzilish yo'q", async () => {
  await renderSettings();
  await ready();
  fireEvent.click(within(section("Soliq profili")).getByRole("button", { name: "Profil qoʻshish" }));
  const dialog = await screen.findByRole("dialog", { name: "Yangi soliq profili" });
  fireEvent.change(within(dialog).getByLabelText("Tayyor shablon"), { target: { value: "yatt" } });
  await within(dialog).findByRole("group", { name: "Soliq qatori 2" });
  const result = await axe.run(dialog, { rules: { "color-contrast": { enabled: false }, region: { enabled: false } } });
  expect(result.violations.filter((v) => v.impact === "critical" || v.impact === "serious").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});
