// Sozlamalar sahifasi va Uzum bonuslari bo'limi testlari (M16, B4.8; ADR-031):
// bonus davrlari ro'yxati (tartib: yangisi tepada), ruxsatlar (ega/menejer vs buxgalter),
// qo'shish (POST), tahrirlash (PATCH to'g'ri tana), o'chirish (tasdiqlash bilan DELETE),
// bo'sh holat, accessibility (axe). Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { formatterFor } from "../../lib/format";
import {
  json,
  ME,
  ME_ROUTE,
  mockApi,
  SHOP_A,
  SHOP_B,
  SHOPS_ROUTE,
  WAIVER_CREATE_ROUTE,
  waiverDeleteRoute,
  waiverPatchRoute,
  WAIVERS_ROUTE,
  type Routes,
} from "../../test/api";
import { waiver } from "../../test/pnl";

const f = formatterFor("uz-Latn");
const norm = (text: string) => text.replace(/[\u00A0\u202F]/g, " ");
const KINDS = ["sale_logistics", "advertising", "storage", "return_storage"];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

const sampleWaiver1 = waiver({
  id: "w-old",
  start_on: "2026-10-01",
  end_on: "2026-10-10",
  shop_id: null,
  kinds: ["sale_logistics"],
  reason: "Eski bonus",
  source: "manual",
  dismissed: false,
  created_at: "2026-10-01T10:00:00Z",
});

const sampleWaiver2 = waiver({
  id: "w-new",
  start_on: "2026-10-15",
  end_on: "2026-10-25",
  shop_id: SHOP_B,
  kinds: ["sale_logistics", "storage"],
  reason: "Yangi nosozlik",
  source: "detected",
  dismissed: false,
  created_at: "2026-10-15T10:00:00Z",
});

const sampleDismissed = waiver({
  id: "w-dismissed",
  start_on: "2026-10-28",
  end_on: "2026-10-29",
  shop_id: SHOP_A,
  kinds: ["storage"],
  reason: "",
  source: "detected",
  dismissed: true,
  created_at: "2026-10-28T10:00:00Z",
});

async function renderSettings(routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [WAIVERS_ROUTE]: () => json(200, { items: [sampleWaiver1, sampleWaiver2, sampleDismissed], kinds: KINDS }),
    ...routes,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Sozlamalar" });
  return api;
}

describe("Sozlamalar sahifasi: Uzum bonuslari", () => {
  it("ro'yxat chiqadi (faol va rad etilgan), tartib to'g'ri (boshlanish sanasi bo'yicha yangisi tepada)", async () => {
    await renderSettings();
    expect(screen.getByText("Bonus haqiqiy foyda va xarajatlarni oʻzgartirmaydi — faqat shu davrdagi buyurtmalarni “Bonus davri” deb belgilaydi.")).toBeTruthy();
    const table = await screen.findByRole("table", { name: "Uzum bonus davrlari" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);

    // 1-qator: eng yangisi w-dismissed (2026-10-28)
    expect(norm(rows[0]!.textContent!)).toContain(norm(f.period("2026-10-28", "2026-10-29")));
    expect(rows[0]!.textContent).toContain("Rad etilgan");
    expect(rows[0]!.textContent).toContain("Tizim taklifi tasdiqlangan");

    // 2-qator: w-new (2026-10-15)
    expect(norm(rows[1]!.textContent!)).toContain(norm(f.period("2026-10-15", "2026-10-25")));
    expect(rows[1]!.textContent).toContain("EL-ONE");
    expect(rows[1]!.textContent).toContain("Yangi nosozlik");

    // 3-qator: w-old (2026-10-01)
    expect(norm(rows[2]!.textContent!)).toContain(norm(f.period("2026-10-01", "2026-10-10")));
    expect(rows[2]!.textContent).toContain("hamma doʻkon");
    expect(rows[2]!.textContent).toContain("Qoʻlda");
  });

  it("egasi uchun 'Qo'shish', 'Tahrirlash', 'O'chirish' ko'rinadi; rad etilgan qatorda 'Tahrirlash' yo'q", async () => {
    await renderSettings();
    expect(screen.getByRole("button", { name: "Bonus qoʻshish" })).toBeTruthy();

    const table = screen.getByRole("table", { name: "Uzum bonus davrlari" });
    const rows = within(table).getAllByRole("row").slice(1);

    // Rad etilgan qatorda Tahrirlash tugmasi yo'q, lekin O'chirish bor
    expect(within(rows[0]!).queryByRole("button", { name: /^Tahrirlash/ })).toBeNull();
    expect(within(rows[0]!).getByRole("button", { name: /^Oʻchirish/ })).toBeTruthy();

    // Faol qatorda Tahrirlash ham, O'chirish ham bor
    expect(within(rows[1]!).getByRole("button", { name: /^Tahrirlash/ })).toBeTruthy();
    expect(within(rows[1]!).getByRole("button", { name: /^Oʻchirish/ })).toBeTruthy();
  });

  it("buxgalter uchun tugmalar umuman chiqmaydi (faqat ko'radi)", async () => {
    await renderSettings({}, "accountant");
    await screen.findByRole("table", { name: "Uzum bonus davrlari" });
    expect(screen.queryByRole("button", { name: "Bonus qoʻshish" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Tahrirlash/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Oʻchirish/ })).toBeNull();
  });

  it("qo'shish: shakl to'ldirilib saqlansa POST so'rovi yuboriladi", async () => {
    const api = await renderSettings({
      [WAIVER_CREATE_ROUTE]: () => json(201, waiver({ id: "w-created" })),
    });

    fireEvent.click(screen.getByRole("button", { name: "Bonus qoʻshish" }));
    const dlg = await screen.findByRole("dialog", { name: "Uzum bonusi" });

    fireEvent.change(within(dlg).getByLabelText("Doʻkon"), { target: { value: SHOP_A } });
    fireEvent.change(within(dlg).getByLabelText("Boshlanish"), { target: { value: "2026-11-01" } });
    fireEvent.change(within(dlg).getByLabelText("Tugash"), { target: { value: "2026-11-10" } });
    fireEvent.change(within(dlg).getByLabelText(/^Sabab/), { target: { value: "Noyabr aksiyasi" } });

    fireEvent.click(within(dlg).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(api.bodiesOf(WAIVER_CREATE_ROUTE)).toEqual([
      {
        shop_id: SHOP_A,
        start_on: "2026-11-01",
        end_on: "2026-11-10",
        kinds: ["sale_logistics"],
        reason: "Noyabr aksiyasi",
        source: "manual",
        dismissed: false,
      },
    ]);
    expect(await screen.findByText("Bonus davri saqlandi")).toBeTruthy();
  });

  it("tahrirlash: PATCH so'rovi faqat kerakli maydonlar bilan yuboriladi (source va dismissed yo'q)", async () => {
    const api = await renderSettings({
      [waiverPatchRoute("w-new")]: () => json(200, sampleWaiver2),
    });

    const table = await screen.findByRole("table", { name: "Uzum bonus davrlari" });
    const rows = within(table).getAllByRole("row").slice(1);
    const editBtn = within(rows[1]!).getByRole("button", { name: /^Tahrirlash/ });
    fireEvent.click(editBtn);

    const dlg = await screen.findByRole("dialog", { name: "Uzum bonusi" });
    expect((within(dlg).getByLabelText("Doʻkon") as HTMLSelectElement).value).toBe(SHOP_B);
    expect((within(dlg).getByLabelText("Boshlanish") as HTMLInputElement).value).toBe("2026-10-15");
    expect((within(dlg).getByLabelText("Tugash") as HTMLInputElement).value).toBe("2026-10-25");
    expect((within(dlg).getByLabelText(/^Sabab/) as HTMLInputElement).value).toBe("Yangi nosozlik");

    // Hamma do'kon qilib o'zgartiramiz va sababni yangilaymiz
    fireEvent.change(within(dlg).getByLabelText("Doʻkon"), { target: { value: "" } });
    fireEvent.change(within(dlg).getByLabelText(/^Sabab/), { target: { value: "Tuzatilgan sabab" } });

    fireEvent.click(within(dlg).getByRole("button", { name: "Bonusni saqlash" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(api.bodiesOf(waiverPatchRoute("w-new"))).toEqual([
      {
        shop_id: null,
        start_on: "2026-10-15",
        end_on: "2026-10-25",
        kinds: ["sale_logistics", "storage"],
        reason: "Tuzatilgan sabab",
      },
    ]);
    expect(await screen.findByText("Bonus davri saqlandi")).toBeTruthy();
  });

  it("o'chirish: tasdiqlash dialogi chiqadi, tasdiqlanganda DELETE so'rovi yuboriladi", async () => {
    const api = await renderSettings({
      [waiverDeleteRoute("w-old")]: () => new Response(null, { status: 204 }),
    });

    const table = await screen.findByRole("table", { name: "Uzum bonus davrlari" });
    const rows = within(table).getAllByRole("row").slice(1);
    const deleteBtn = within(rows[2]!).getByRole("button", { name: /^Oʻchirish/ });
    fireEvent.click(deleteBtn);

    const confirmDlg = await screen.findByRole("dialog", { name: "Bonus davrini oʻchirish" });
    expect(confirmDlg.textContent).toContain("Haqiqatan ham bu bonus davrini oʻchirmoqchimisiz?");
    expect(confirmDlg.textContent).toContain("Buyurtmalardan “Bonus davri” belgisi olib tashlanadi, haqiqiy hisob-kitoblar oʻzgarmaydi.");

    // Bekor qilish bosilsa so'rov yuborilmaydi
    fireEvent.click(within(confirmDlg).getByRole("button", { name: "Bekor qilish" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.count(waiverDeleteRoute("w-old"))).toBe(0);

    // Qaytadan ochib tasdiqlaymiz
    fireEvent.click(deleteBtn);
    const confirmDlgAgain = await screen.findByRole("dialog", { name: "Bonus davrini oʻchirish" });
    fireEvent.click(within(confirmDlgAgain).getByRole("button", { name: "Oʻchirish" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    expect(api.count(waiverDeleteRoute("w-old"))).toBe(1);
    expect(await screen.findByText("Bonus davri oʻchirildi")).toBeTruthy();
  });

  it("bo'sh holat: bonuslar yo'q bo'lsa EmptyState va qo'shish tugmasi chiqadi", async () => {
    await renderSettings({
      [WAIVERS_ROUTE]: () => json(200, { items: [], kinds: KINDS }),
    });

    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Bonus davrlari yoʻq")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Bonus qoʻshish" })).toBeTruthy();
  });

  it("accessibility (axe): jiddiy yoki kritik xatolar 0", async () => {
    await renderSettings();
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  }, 30_000);
});
