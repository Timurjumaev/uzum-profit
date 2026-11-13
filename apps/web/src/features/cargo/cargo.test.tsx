// Kargo puli jadvali (TM3, ADR-061 §3): trekli summalar bitta saqlashda, kodli quti (dona bo'yicha ulushlar serverdan,
// qo'lda o'zgartirilgani yuboriladi, qoldiq), omborchi — summasiz; xarajat oynasida o'z turi (§4); kargo sahifasida
// quti ulushlarini tahrirlash. Butun ilova soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import {
  CARGO_BOX_ROUTE,
  CARGO_POOL_ROUTE,
  CARGO_SHARES_ROUTE,
  CARGO_TRACKED_ROUTE,
  COST_TYPE_CREATE_ROUTE,
  COST_TYPES_ROUTE,
  json,
  ME,
  ME_ROUTE,
  mockApi,
  problem,
  purchaseRoute,
  purchaseSubRoute,
  type Routes,
} from "../../test/api";
import { component, PURCHASE_1, PURCHASE_2, purchaseDetail } from "../../test/purchases";
import { SHIPMENT_1, SHIPMENT_COMP, shipmentDetail } from "../../test/shipments";
import { shipmentRoute } from "../../test/api";
import { boxRest } from "./CargoPool";

const PURCHASE_3 = "93333333-3333-4333-8333-333333333333";
const row = (id: string, title: string, units: number, track: string | null = null) => ({ purchase_id: id, title, track_no: track, supplier_name: "Yiwu Toys", ordered_on: "2026-10-02", state: "in_transit" as const, items: ["Mashina"], units });
const POOL = { items: [row(PURCHASE_1, "Trekli A", 30, "YT-1"), row(PURCHASE_2, "Quti B", 60), row(PURCHASE_3, "Quti C", 10)], amounts: true };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderAt(path: string, routes: Routes = {}, role = "owner") {
  const api = mockApi({
    [CARGO_POOL_ROUTE]: () => json(200, POOL),
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    ...routes,
  });
  const history = createMemoryHistory({ initialEntries: [path] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

const bodiesOf = (api: ReturnType<typeof mockApi>, key: string) => api.bodiesOf(key) as Array<Record<string, unknown>>;

describe("kargo puli jadvali", () => {
  it("boxRest: qoldiq ikki xonagacha, summa yo'q — null", () => {
    expect(boxRest("100", ["30", "60", null])).toBe(10);
    expect(boxRest("100.10", ["50.05", "50.05"])).toBe(0);
    expect(boxRest(null, ["1"])).toBeNull();
  });

  it("trekli: summa yozilgan kartochkalar bitta so'rovda (USD, Markaziy bank), kg ixtiyoriy", async () => {
    const { api } = await renderAt("/cargo-pool", { [CARGO_TRACKED_ROUTE]: () => json(201, { created: 2 }) });
    const list = await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(list.textContent).toContain("trek YT-1");
    const save = screen.getByRole("button", { name: "Kargo pulini saqlash (0)" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Kargo puli: Trekli A"), { target: { value: "45,5" } });
    fireEvent.change(screen.getByLabelText("Vazn, kg: Trekli A"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Kargo puli: Quti C"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Kargo pulini saqlash (2)" }));
    await waitFor(() => expect(bodiesOf(api, CARGO_TRACKED_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, CARGO_TRACKED_ROUTE)[0]).toMatchObject({
      currency: "USD",
      rate_mode: "cbu",
      rows: [
        { purchase_id: PURCHASE_1, amount: "45.5", weight_kg: "3" },
        { purchase_id: PURCHASE_3, amount: "12" },
      ],
    });
    expect(await screen.findByText("Kargo puli saqlandi: 2 ta xarid")).toBeTruthy();
  });

  it("qo'lda kurs: kurs kiritilmaguncha saqlab bo'lmaydi", async () => {
    await renderAt("/cargo-pool");
    await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    fireEvent.click(screen.getByRole("radio", { name: "Oʻzim kiritaman" }));
    fireEvent.change(screen.getByLabelText("Kargo puli: Trekli A"), { target: { value: "10" } });
    expect((screen.getByRole("button", { name: "Kargo pulini saqlash (1)" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/^1 USD/), { target: { value: "12700" } });
    expect((screen.getByRole("button", { name: "Kargo pulini saqlash (1)" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("kodli quti: ulushlar serverdan (dona bo'yicha), qo'lda o'zgartirilgani yuboriladi; qoldiq bo'lsa saqlanmaydi", async () => {
    const { api, history } = await renderAt("/cargo-pool", {
      [CARGO_SHARES_ROUTE]: async (r) => {
        const body = (await r.json()) as { fixed: Record<string, string> };
        const fixed = body.fixed[PURCHASE_2];
        return json(200, { shares: fixed ? { [PURCHASE_2]: fixed, [PURCHASE_3]: String(100 - Number(fixed)) } : { [PURCHASE_2]: "85.71", [PURCHASE_3]: "14.29" }, units: { [PURCHASE_2]: 60, [PURCHASE_3]: 10 } });
      },
      [CARGO_BOX_ROUTE]: () => json(201, { shipment_id: SHIPMENT_1 }),
      [shipmentRoute(SHIPMENT_1)]: () => json(200, shipmentDetail()),
    });
    await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Qutiga qoʻshish: Quti B" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Qutiga qoʻshish: Quti C" }));
    const panel = screen.getByRole("region", { name: "Bitta qutiga birlashtirish" });
    expect(panel.textContent).toContain("2 ta xarid belgilandi");
    const save = within(panel).getByRole("button", { name: "Qutini saqlash" }) as HTMLButtonElement;
    fireEvent.change(within(panel).getByLabelText(/^Kod yoki quti nomi/), { target: { value: "KOD-77" } });
    fireEvent.change(within(panel).getByLabelText(/^Umumiy summa/), { target: { value: "100" } });
    await waitFor(() => expect((screen.getByLabelText("Qutidagi ulush: Quti B") as HTMLInputElement).value).toBe("85,71"));
    expect(save.disabled).toBe(false);
    // Qo'lda ulush: server qolganini qayta bo'ladi.
    fireEvent.change(screen.getByLabelText("Qutidagi ulush: Quti B"), { target: { value: "70" } });
    await waitFor(() => expect((screen.getByLabelText("Qutidagi ulush: Quti C") as HTMLInputElement).value).toBe("30,00"));
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, CARGO_BOX_ROUTE)).toHaveLength(1));
    expect(bodiesOf(api, CARGO_BOX_ROUTE)[0]).toMatchObject({ title: "KOD-77", amount: "100", currency: "USD", purchase_ids: [PURCHASE_2, PURCHASE_3], fixed: { [PURCHASE_2]: "70" } });
    await waitFor(() => expect(history.location.pathname).toBe(`/shipments/${SHIPMENT_1}`));
  });

  it("kodli quti: hammasi qo'lda va yig'indi teng emas — qoldiq ko'rinadi, saqlab bo'lmaydi; server xatosi ko'rinadi", async () => {
    await renderAt("/cargo-pool", {
      [CARGO_SHARES_ROUTE]: async (r) => {
        const body = (await r.json()) as { fixed: Record<string, string> };
        if (Object.keys(body.fixed).length === 2) return problem(422, "bad_shares");
        return json(200, { shares: { [PURCHASE_2]: "50", [PURCHASE_3]: "50" }, units: {} });
      },
    });
    await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Qutiga qoʻshish: Quti B" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Qutiga qoʻshish: Quti C" }));
    const panel = screen.getByRole("region", { name: "Bitta qutiga birlashtirish" });
    fireEvent.change(within(panel).getByLabelText(/^Kod yoki quti nomi/), { target: { value: "K" } });
    fireEvent.change(within(panel).getByLabelText(/^Umumiy summa/), { target: { value: "100" } });
    await waitFor(() => expect((screen.getByLabelText("Qutidagi ulush: Quti B") as HTMLInputElement).value).toBe("50,00"));
    fireEvent.change(screen.getByLabelText("Qutidagi ulush: Quti B"), { target: { value: "40" } });
    fireEvent.change(screen.getByLabelText("Qutidagi ulush: Quti C"), { target: { value: "50" } });
    expect(await screen.findByText(/Ulushlar yigʻindisi umumiy summaga teng emas/)).toBeTruthy();
    expect((within(panel).getByRole("button", { name: "Qutini saqlash" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(panel).getByRole("button", { name: "Hammasini dona boʻyicha" }));
    await waitFor(() => expect((within(panel).getByRole("button", { name: "Qutini saqlash" }) as HTMLButtonElement).disabled).toBe(false));
  });

  it("omborchi: ro'yxat bor, summa inputlari va belgilash yo'q; bo'sh holat", async () => {
    await renderAt("/cargo-pool", { [CARGO_POOL_ROUTE]: () => json(200, { ...POOL, amounts: false }) }, "warehouse");
    await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    expect(screen.queryByLabelText("Kargo puli: Trekli A")).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /Qutiga/ })).toBeNull();
    expect(screen.getByText("Summalar sizga koʻrinmaydi")).toBeTruthy();
    cleanup();
    const { api } = await renderAt("/cargo-pool", { [CARGO_POOL_ROUTE]: () => json(200, { items: [], amounts: true }) });
    expect(await screen.findByText("Kargo puli kutilayotgan xarid yoʻq")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: /Sanalgan xaridlar ham/ }));
    await waitFor(() => expect(api.fetch.mock.calls.some(([r]) => new URL((r as Request).url).searchParams.get("counted") === "true")).toBe(true));
  });

  it("a11y: jiddiy buzilish yo'q", async () => {
    await renderAt("/cargo-pool");
    await screen.findByRole("list", { name: "Kargo puli kutilayotgan xaridlar" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Qutiga qoʻshish: Quti B" }));
    const results = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.filter((v) => v.impact === "critical" || v.impact === "serious")).toEqual([]);
  });
});

describe("xarajat turlari lug'ati (ADR-061 §4)", () => {
  it("o'z turi tanlanadi yoki «Yangi tur…» bilan yaratiladi — kind other + cost_type_id", async () => {
    const post = purchaseSubRoute("POST", PURCHASE_1, "components");
    const { api } = await renderAt(`/purchases/${PURCHASE_1}`, {
      [purchaseRoute("GET", PURCHASE_1)]: () => json(200, purchaseDetail({ components: [component({ id: "c9", kind: "other", cost_type_id: "t1", type_name: "Ombor ijarasi" })] })),
      [COST_TYPES_ROUTE]: () => json(200, [{ id: "t1", name: "Ombor ijarasi" }]),
      [COST_TYPE_CREATE_ROUTE]: () => json(201, { id: "t2", name: "Yuk tushirish" }),
      [post]: () => json(201, purchaseDetail()),
      ...{ [`GET /api/v1/orgs/${ME.orgs[0]!.id}/sku-picker`]: () => json(200, { rows: [], truncated: false }) },
    });
    const comps = await screen.findByRole("table", { name: "Xarajat komponentlari" });
    expect(within(comps).getByText("Ombor ijarasi")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Xarajat qoʻshish" }));
    const dialog = await screen.findByRole("dialog", { name: "Yangi xarajat" });
    await within(dialog).findByRole("option", { name: "Ombor ijarasi" });
    // Yangi yozuvda vazn / hajm / qiymat asoslari yo'q.
    expect(within(dialog).queryByRole("option", { name: "Vazn boʻyicha" })).toBeNull();
    fireEvent.change(within(dialog).getByLabelText("Turi"), { target: { value: "__new_type" } });
    const save = within(dialog).getByRole("button", { name: "Xarajatni saqlash" }) as HTMLButtonElement;
    fireEvent.change(within(dialog).getByLabelText(/^Summa/), { target: { value: "5000" } });
    fireEvent.change(within(dialog).getByLabelText("Valyuta"), { target: { value: "UZS" } });
    expect(save.disabled).toBe(true); // nom yo'q
    fireEvent.change(within(dialog).getByLabelText(/^Yangi tur nomi/), { target: { value: " Yuk tushirish " } });
    fireEvent.click(save);
    await waitFor(() => expect(bodiesOf(api, post)).toHaveLength(1));
    expect(bodiesOf(api, COST_TYPE_CREATE_ROUTE)[0]).toEqual({ name: "Yuk tushirish" });
    expect(bodiesOf(api, post)[0]).toMatchObject({ kind: "other", cost_type_id: "t2", amount: "5000", currency: "UZS" });
  });
});

describe("kargo sahifasida quti ulushlari", () => {
  it("ulushlar oynasi: dona bo'yicha tayyor, o'zgartirilgani PUT bilan saqlanadi", async () => {
    const put = `PUT /api/v1/orgs/${ME.orgs[0]!.id}/shipments/${SHIPMENT_1}/components/${SHIPMENT_COMP}/purchase-shares`;
    const box = shipmentDetail();
    box.components = box.components.map((c) => ({ ...c, allocation: "units", lines: null }));
    const { api } = await renderAt(`/shipments/${SHIPMENT_1}`, {
      [shipmentRoute(SHIPMENT_1)]: () => json(200, box),
      [CARGO_SHARES_ROUTE]: async (r) => {
        const body = (await r.json()) as { fixed: Record<string, string> };
        const a = body.fixed[PURCHASE_1] ?? "1000000";
        return json(200, { shares: { [PURCHASE_1]: a, [PURCHASE_2]: String(2430000 - Number(a)) }, units: { [PURCHASE_1]: 140, [PURCHASE_2]: 200 } });
      },
      [put]: () => json(200, { shares: {}, units: {} }),
    });
    fireEvent.click(await screen.findByRole("button", { name: /^Xaridlar ulushi: Kargo/ }));
    const dialog = await screen.findByRole("dialog", { name: "Qutidagi xaridlar ulushi" });
    const first = within(dialog).getByLabelText(/^A yetkazib beruvchi · 140 dona/) as HTMLInputElement;
    await waitFor(() => expect(first.value).not.toBe(""));
    fireEvent.change(first, { target: { value: "1500000" } });
    await waitFor(() => expect((within(dialog).getByLabelText(/^B yetkazib beruvchi/) as HTMLInputElement).value).toContain("930"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Ulushlarni saqlash" }));
    await waitFor(() => expect(bodiesOf(api, put)).toHaveLength(1));
    expect(bodiesOf(api, put)[0]).toEqual({ fixed: { [PURCHASE_1]: "1500000" } });
    expect(await screen.findByText("Ulushlar saqlandi")).toBeTruthy();
  });
});
