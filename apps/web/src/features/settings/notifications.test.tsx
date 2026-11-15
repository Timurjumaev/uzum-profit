// Bildirishnomalar sozlamasi (B6.1): hodisalar (kritik, "tez orada"), chegaralar, tinch soatlar — PUT tanasi; noto'g'ri
// chegara — saqlab bo'lmaydi. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, ME, mockApi, notificationSettings, type Routes } from "../../test/api";
import { paramValid } from "./NotificationSettings";

const ORG = ME.orgs[0]!.id;
const PUT = `PUT /api/v1/orgs/${ORG}/notifications/settings`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(routes: Routes = {}) {
  const api = mockApi({ [PUT]: () => json(200, notificationSettings()), ...routes });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  const list = await screen.findByRole("list", { name: "Hodisalar" });
  return { api, list, box: () => screen.getByRole("region", { name: "Bildirishnomalar" }) };
}

describe("bildirishnomalar sozlamasi", () => {
  it("hodisalar: kritik belgisi, tez orada — o'chiq, rolga tegishli bo'lmagani yo'q", async () => {
    const { list } = await renderAt();
    const sync = within(list).getByRole("checkbox", { name: /Sinxron toʻxtadi/ });
    expect(sync.closest("label")!.textContent).toContain("Kritik");
    const payout = within(list).getByRole("checkbox", { name: /Uzum toʻlovi kechikmoqda/ }) as HTMLInputElement;
    expect(payout.disabled).toBe(true);
    expect(payout.closest("label")!.textContent).toContain("Tez orada (B5.7)");
    expect(within(list).queryByRole("checkbox", { name: /Qaytish keskin oshdi/ })).toBeNull();
    expect((within(list).getByLabelText("Vaqti: Kunlik xulosa (kechagi buyurtma, tushum, sof foyda, bekorlar)") as HTMLInputElement).value).toBe("09:00");
  });

  it("saqlash: o'zgargan chegara, o'chirilgan hodisa, tinch soatlar", async () => {
    const { api, list, box } = await renderAt();
    fireEvent.change(within(list).getByLabelText(/^Vaqti: Kunlik xulosa/), { target: { value: "07:30" } });
    fireEvent.click(within(list).getByRole("checkbox", { name: /Yangi jarima/ }));
    fireEvent.change(within(list).getByLabelText(/^Ketma-ket sotuvlar/), { target: { value: "50" } });
    expect(within(box()).getByText(/Vaqtni SS:DD/)).toBeTruthy();
    expect((within(box()).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(list).getByLabelText(/^Ketma-ket sotuvlar/), { target: { value: "4" } });
    fireEvent.change(within(box()).getByLabelText("Boshlanishi"), { target: { value: "23:00" } });
    fireEvent.click(within(box()).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    const body = api.bodiesOf(PUT)[0] as { rules: Array<{ event: string; enabled: boolean; params: Record<string, unknown> }>; quiet_from: string; quiet_to: string };
    const rules = Object.fromEntries(body.rules.map((r) => [r.event, r]));
    expect(rules.daily_summary).toEqual({ event: "daily_summary", enabled: true, params: { at: "07:30" } });
    expect(rules.new_fine).toEqual({ event: "new_fine", enabled: false, params: {} });
    expect(rules.loss_sales!.params).toEqual({ streak: 4 });
    expect(rules.payout_late).toBeUndefined();
    expect([body.quiet_from, body.quiet_to]).toEqual(["23:00", "08:00"]);
    expect(await screen.findByText("Bildirishnoma sozlamalari saqlandi")).toBeTruthy();
  });

  it("tinch soatni o'chirish — ikkalasi null", async () => {
    const { api, box } = await renderAt();
    fireEvent.click(within(box()).getByRole("checkbox", { name: /Tinch soatlarda xabar yubormaslik/ }));
    expect(within(box()).queryByLabelText("Boshlanishi")).toBeNull();
    fireEvent.click(within(box()).getByRole("button", { name: "Saqlash" }));
    await waitFor(() => expect(api.bodiesOf(PUT)).toHaveLength(1));
    expect(api.bodiesOf(PUT)[0]).toMatchObject({ quiet_from: null, quiet_to: null });
  });

  it("Telegram: havola ochiladi; ulangan bo'lsa — belgi va uzish", async () => {
    const open = vi.fn();
    vi.stubGlobal("open", open);
    const LINK = `POST /api/v1/orgs/${ORG}/notifications/telegram`;
    const url = "https://t.me/sellermax_bot?start=abc";
    const { api, box } = await renderAt({ [LINK]: () => json(200, { url, expires_at: "2026-11-15T10:15:00Z" }) });
    fireEvent.click(within(box()).getByRole("button", { name: "Telegramʼni ulash" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(url, "_blank", "noopener"));
    expect(api.count(LINK)).toBe(1);
    expect(within(box()).getByRole("link", { name: "Botni qayta ochish" }).getAttribute("href")).toBe(url);
    cleanup();
    const DEL = `DELETE /api/v1/orgs/${ORG}/notifications/telegram`;
    const linked = await renderAt({ [`GET /api/v1/orgs/${ORG}/notifications/settings`]: () => json(200, notificationSettings({ telegram_linked: true })), [DEL]: () => new Response(null, { status: 204 }) });
    expect(within(linked.box()).getByText("Telegram ulangan")).toBeTruthy();
    fireEvent.click(within(linked.box()).getByRole("button", { name: "Uzish" }));
    await waitFor(() => expect(linked.api.count(DEL)).toBe(1));
    expect(await screen.findByText("Telegram uzildi")).toBeTruthy();
  });

  it("chegara tekshiruvi", () => {
    expect(paramValid("at", "23:59")).toBe(true);
    expect(paramValid("at", "24:00")).toBe(false);
    expect(paramValid("streak", "1")).toBe(false);
    expect(paramValid("hours", "24")).toBe(true);
    expect(paramValid("days", "31")).toBe(false);
    expect(paramValid("hours", null)).toBe(false);
  });
});
