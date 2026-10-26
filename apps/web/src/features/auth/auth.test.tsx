// Kirish (M1): telefon → Telegram kodi → kirish; taklif; til va profil. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { meQuery } from "../../app/query";
import { inviteSearch } from "../../app/router";
import {
  INVITE_ROUTE,
  json,
  LOGIN_ROUTE,
  ME,
  ME_ROUTE,
  mockApi,
  ORG_ID,
  OTP_ROUTE,
  problem,
  PROFILE_ROUTE,
  type Routes,
} from "../../test/api";
import { syncProfileLanguage } from "./language";
import { createI18n } from "../../lib/i18n";

const PHONE = "+998901234567";
const unauthorized: Routes = { [ME_ROUTE]: () => problem(401, "unauthorized") };
const loggedIn = (over: Record<string, unknown> = {}) => json(200, { user: ME.user, orgs: ME.orgs, created: false, ...over });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

async function renderLogin(path = "/login", routes: Routes = {}) {
  const api = mockApi({
    ...unauthorized,
    [OTP_ROUTE]: () => json(202, { phone: PHONE, expires_in: 300 }),
    [LOGIN_ROUTE]: () => loggedIn(),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  const state = createAppState(history, "uz-Latn");
  render(<App state={state} />);
  await screen.findByRole("heading", { name: "Kirish" });
  return { api, history, state };
}

const phoneInput = () => screen.getByLabelText(/^Telefon raqami/);
const codeInput = () => screen.getByLabelText("Telegramʼdagi kod") as HTMLInputElement;
const sendCode = async (text = "+998 90 123 45 67") => {
  fireEvent.change(phoneInput(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Kod yuborish" }));
  await screen.findByRole("heading", { name: "Kodni kiriting" });
};
const serious = async () =>
  (await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } })).violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);

describe("telefon bosqichi", () => {
  it("noto'g'ri raqam — xato matni, so'rov ketmaydi", async () => {
    const { api } = await renderLogin();
    for (const bad of ["", "abc", "+998 90 123", "+7 912 345 67 89"]) {
      fireEvent.change(phoneInput(), { target: { value: bad } });
      fireEvent.click(screen.getByRole("button", { name: "Kod yuborish" }));
      expect((await screen.findByRole("alert")).textContent).toContain("Telefon raqami notoʻgʻri");
    }
    expect(api.count(OTP_ROUTE)).toBe(0);
  });

  it.each(["+998 90 123 45 67", "998901234567", "90 123-45-67", "(90) 1234567"])("'%s' — yagona ko'rinishda yuboriladi", async (text) => {
    const { api } = await renderLogin();
    await sendCode(text);
    expect(api.bodiesOf(OTP_ROUTE)).toEqual([{ phone: PHONE }]);
  });

  it("kod bosqichi: raqam o'qiladigan ko'rinishda, amal qilish muddati, fokus kod maydonida", async () => {
    await renderLogin();
    await sendCode();
    expect(screen.getByText(/\+998 90 123 45 67 raqamiga Telegramʼ orqali 6 xonali kod yuborildi\. Kod 5 daqiqa amal qiladi\./)).toBeTruthy();
    expect(document.activeElement).toBe(codeInput());
    expect(codeInput().getAttribute("autocomplete")).toBe("one-time-code");
    expect(codeInput().getAttribute("inputmode")).toBe("numeric");
  });

  it.each([
    ["telegram_not_found", 404, "Telegramʼda roʻyxatdan oʻtmagan"],
    ["otp_rate_limited", 429, "Kod juda koʻp soʻraldi"],
    ["otp_delivery_failed", 502, "Kod yuborilmadi"],
  ])("kod yuborilmadi (%s) — sabab va nima qilish kerakligi, telefon bosqichida qoladi", async (code, status, text) => {
    await renderLogin("/login", { [OTP_ROUTE]: () => problem(status, code) });
    fireEvent.change(phoneInput(), { target: { value: PHONE } });
    fireEvent.click(screen.getByRole("button", { name: "Kod yuborish" }));
    expect((await screen.findByRole("alert")).textContent).toContain(text);
    expect(screen.queryByRole("heading", { name: "Kodni kiriting" })).toBeNull();
  });
});

describe("kod bosqichi", () => {
  it("6 raqam yozilgach o'zi yuboriladi (harflar tashlanadi); muvaffaqiyatda bosh sahifa", async () => {
    const { api, history, state } = await renderLogin();
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "12ab34" } });
    expect(api.count(LOGIN_ROUTE)).toBe(0); // 4 raqam — hali yetmaydi
    fireEvent.change(codeInput(), { target: { value: "123 456" } });
    expect(await screen.findByRole("heading", { name: "SellerMax" })).toBeTruthy();
    expect(api.bodiesOf(LOGIN_ROUTE)).toEqual([{ phone: PHONE, code: "123456" }]);
    expect(history.location.pathname).toBe("/");
    expect(state.queryClient.getQueryData(meQuery.queryKey)).toEqual({ user: ME.user, orgs: ME.orgs });
    expect(api.count(ME_ROUTE)).toBe(0); // login javobi keshga tushdi — qayta so'ralmaydi
  });

  it("'Kirish' tugmasi 6 raqamgacha faol emas; ikki marta yuborilmaydi", async () => {
    let release!: () => void;
    const pending = new Promise<void>((r) => (release = r));
    const { api } = await renderLogin("/login", { [LOGIN_ROUTE]: async () => (await pending, loggedIn()) });
    await sendCode();
    const submit = screen.getByRole("button", { name: "Kirish" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    await waitFor(() => expect(api.count(LOGIN_ROUTE)).toBe(1));
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    fireEvent.submit(codeInput().closest("form")!);
    expect(api.count(LOGIN_ROUTE)).toBe(1);
    await act(async () => release());
    await screen.findByRole("heading", { name: "SellerMax" });
  });

  it("qaytish manzili (faqat ichki yo'l) hurmat qilinadi", async () => {
    const { history } = await renderLogin("/login?redirect=%2Finventory%3Fcmp%3Dprevious");
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect(await screen.findByRole("heading", { name: "Ombor" })).toBeTruthy();
    expect(history.location.pathname).toBe("/inventory");
    expect(history.location.search).toContain("cmp=previous");
  });

  it("begona manzilga qaytarish yo'q (ochiq qayta yo'naltirish)", async () => {
    const { history } = await renderLogin("/login?redirect=%2F%2Fevil.example");
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect(await screen.findByRole("heading", { name: "SellerMax" })).toBeTruthy();
    expect(history.location.pathname).toBe("/");
  });

  it("tashkilot yo'q — onboarding'ga", async () => {
    const { history } = await renderLogin("/login", { [LOGIN_ROUTE]: () => loggedIn({ orgs: [], created: true }) });
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect(await screen.findByRole("heading", { name: "Biznesingiz nomi" })).toBeTruthy();
    expect(history.location.pathname).toBe("/onboarding");
  });

  it.each([
    ["otp_invalid", "Kod notoʻgʻri"],
    ["otp_expired", "Kod eskirgan"],
    ["otp_blocked", "15 daqiqadan soʻng"],
  ])("%s — xato matni, maydon tozalanadi va qayta fokus oladi", async (code, text) => {
    const { api } = await renderLogin("/login", { [LOGIN_ROUTE]: () => problem(code === "otp_blocked" ? 429 : 422, code) });
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect((await screen.findByRole("alert")).textContent).toContain(text);
    await waitFor(() => expect(codeInput().value).toBe(""));
    expect(document.activeElement).toBe(codeInput());
    expect(api.count(LOGIN_ROUTE)).toBe(1);
    expect(screen.queryByRole("heading", { name: "SellerMax" })).toBeNull();
  });

  it("qayta yuborish 30 soniyadan keyin; 'Raqamni o'zgartirish' telefon bosqichiga qaytaradi", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
    const { api } = await renderLogin();
    await sendCode();
    const resend = () => screen.getByRole("button", { name: /Qayta yuborish|Kodni qayta yuborish/ }) as HTMLButtonElement;
    expect(resend().disabled).toBe(true);
    expect(resend().textContent).toBe("Qayta yuborish: 30 s");
    await act(async () => vi.advanceTimersByTime(12_000));
    expect(resend().textContent).toBe("Qayta yuborish: 18 s");
    await act(async () => vi.advanceTimersByTime(18_000));
    expect(resend().textContent).toBe("Kodni qayta yuborish");
    expect(resend().disabled).toBe(false);
    fireEvent.click(resend());
    await waitFor(() => expect(api.count(OTP_ROUTE)).toBe(2));
    expect(resend().disabled).toBe(true); // yangi kutish boshlandi

    fireEvent.click(screen.getByRole("button", { name: "Raqamni oʻzgartirish" }));
    expect(await screen.findByRole("heading", { name: "Kirish" })).toBeTruthy();
  });
});

describe("til va profil (M1)", () => {
  it("kirishdan oldin til tanlanadi (ruscha)", async () => {
    await renderLogin();
    fireEvent.change(screen.getByLabelText("Til"), { target: { value: "ru" } });
    expect(await screen.findByRole("heading", { name: "Вход" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("ru");
    expect(localStorage.getItem("up.lang")).toBe("ru");
  });

  it("qo'lda tanlangan til kirishda profilga yoziladi", async () => {
    const { api } = await renderLogin();
    fireEvent.change(screen.getByLabelText("Til"), { target: { value: "ru" } });
    await screen.findByRole("heading", { name: "Вход" });
    fireEvent.change(screen.getByLabelText(/^Номер телефона/), { target: { value: PHONE } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить код" }));
    await screen.findByRole("heading", { name: "Введите код" });
    fireEvent.change(screen.getByLabelText("Код из Telegram"), { target: { value: "123456" } });
    await waitFor(() => expect(api.count(PROFILE_ROUTE)).toBe(1));
    expect(api.bodiesOf(PROFILE_ROUTE)).toEqual([{ language: "ru" }]);
  });

  it("til tanlanmagan bo'lsa profil tili qo'llanadi (yangi qurilma)", async () => {
    await renderLogin("/login", {
      [LOGIN_ROUTE]: () => loggedIn({ user: { ...ME.user, language: "ru" } }),
    });
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect(await screen.findByRole("navigation", { name: "Главное меню" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("ru");
  });

  it("allaqachon kirgan foydalanuvchi, yangi qurilma: profil tili sahifa ochilganda qo'llanadi", async () => {
    mockApi({ [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: "uz-Cyrl" } }) });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/pnl"] }), "uz-Latn")} />);
    expect(await screen.findByRole("heading", { name: "Фойда" })).toBeTruthy();
  });

  it("syncProfileLanguage: tanlov yo'q — profil; tanlov bor — profilga yozish faqat push bilan; xato jim", async () => {
    const api = mockApi({ [PROFILE_ROUTE]: () => problem(500, "internal") });
    const i18n = createI18n("uz-Latn");
    await syncProfileLanguage(i18n, "ru", { push: false });
    expect(i18n.language).toBe("ru");
    expect(localStorage.getItem("up.lang")).toBe("ru");
    await syncProfileLanguage(i18n, "uz-Latn", { push: false });
    expect(i18n.language).toBe("ru"); // tanlov bor — tegilmaydi
    expect(api.count(PROFILE_ROUTE)).toBe(0);
    await expect(syncProfileLanguage(i18n, "uz-Latn", { push: true })).resolves.toBeUndefined(); // 500 — jim
    expect(api.bodiesOf(PROFILE_ROUTE)).toEqual([{ language: "ru" }]);
    await syncProfileLanguage(i18n, "noma'lum", { push: false });
    expect(i18n.language).toBe("ru");
  });

  it("foydalanuvchi menyusidan til almashsa profilga yoziladi", async () => {
    const api = mockApi();
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/"] }), "uz-Latn")} />);
    fireEvent.click(await screen.findByRole("button", { name: /^Hisob:/ }));
    fireEvent.change(within(screen.getByRole("group", { name: /^Hisob:/ })).getByLabelText("Til"), { target: { value: "uz-Cyrl" } });
    await waitFor(() => expect(api.bodiesOf(PROFILE_ROUTE)).toEqual([{ language: "uz-Cyrl" }]));
  });
});

describe("taklif (M1)", () => {
  const TOKEN = "abcdEFGH1234-xyz";

  it("havola qidiruvi: faqat to'g'ri belgili token", () => {
    expect(inviteSearch({ token: TOKEN })).toEqual({ token: TOKEN });
    for (const bad of ["", "qisqa", "a b c d e f g h", "<script>alert(1)</script>", "../../etc", 5, null]) {
      expect(inviteSearch({ token: bad })).toEqual({});
    }
  });

  it("kirmagan — avval kirish, keyin taklifga qaytadi", async () => {
    const { history } = await renderLogin(`/invite?token=${TOKEN}`);
    expect(history.location.pathname).toBe("/login");
    expect(new URLSearchParams(history.location.search).get("redirect")).toBe(`/invite?token=${TOKEN}`);
    await sendCode();
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    expect(await screen.findByRole("heading", { name: "Taklif" })).toBeTruthy();
    expect(history.location.pathname).toBe("/invite");
  });

  it("qabul qilish: token yuboriladi, tashkilotlar yangilanadi, bosh sahifaga", async () => {
    const api = mockApi({ [INVITE_ROUTE]: () => json(200, { org_id: ORG_ID }) });
    const history = createMemoryHistory({ initialEntries: [`/invite?token=${TOKEN}`] });
    render(<App state={createAppState(history, "uz-Latn")} />);
    fireEvent.click(await screen.findByRole("button", { name: "Taklifni qabul qilish" }));
    expect(await screen.findByRole("heading", { name: "SellerMax" })).toBeTruthy();
    expect(api.bodiesOf(INVITE_ROUTE)).toEqual([{ token: TOKEN }]);
    expect(api.count(ME_ROUTE)).toBeGreaterThanOrEqual(2); // yangi tashkilot ro'yxatga tushsin
    expect(history.location.pathname).toBe("/");
  });

  it.each([
    ["invite_expired", "Taklif muddati tugagan"],
    ["invite_used", "allaqachon ishlatilgan"],
    ["invite_phone_mismatch", "boshqa telefon raqamiga"],
  ])("%s — tushunarli xabar, sahifada qoladi", async (code, text) => {
    mockApi({ [INVITE_ROUTE]: () => problem(409, code) });
    const history = createMemoryHistory({ initialEntries: [`/invite?token=${TOKEN}`] });
    render(<App state={createAppState(history, "uz-Latn")} />);
    fireEvent.click(await screen.findByRole("button", { name: "Taklifni qabul qilish" }));
    expect((await screen.findByRole("alert")).textContent).toContain(text);
    expect(history.location.pathname).toBe("/invite");
  });

  it("token yo'q yoki noto'g'ri — qabul qilib bo'lmaydi, so'rov ketmaydi", async () => {
    const api = mockApi();
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/invite?token=%3Cscript%3E"] }), "uz-Latn")} />);
    expect(await screen.findByText(/Taklif havolasi notoʻliq/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Taklifni qabul qilish" })).toBeNull();
    expect(api.count(INVITE_ROUTE)).toBe(0);
  });
});

describe("kirish imkoniyati (axe-core: jiddiy xato 0)", () => {
  it("telefon va kod bosqichlari, xato bilan", async () => {
    await renderLogin("/login", { [LOGIN_ROUTE]: () => problem(422, "otp_invalid") });
    expect(await serious()).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Kod yuborish" })); // bo'sh — xato
    await screen.findByRole("alert");
    expect(await serious()).toEqual([]);
    await sendCode();
    expect(await serious()).toEqual([]);
    fireEvent.change(codeInput(), { target: { value: "123456" } });
    await screen.findByRole("alert");
    expect(await serious()).toEqual([]);
  }, 60_000);
});
