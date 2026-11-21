// Uzum kaliti muddati (B8.16): faqat egasiga; muddat PATCH bilan saqlanadi; qolgan kun ko'rsatiladi.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { ACCOUNTS_ROUTE, json, ME, ME_ROUTE, mockApi, ORG_ID, SETTINGS_ROUTE } from "../../test/api";
import { settingsData } from "../../test/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ACCOUNT_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const account = (over: Record<string, unknown> = {}) => ({
  id: ACCOUNT_ID, provider: "uzum", status: "active", key_hint: "…abcd", key_expires_on: "2026-11-24", key_days_left: 3,
  checked_at: null, quota_remaining: null, created_at: "2026-11-01T00:00:00Z", shops: [], ...over,
});
const PATCH = `PATCH /api/v1/orgs/${ORG_ID}/accounts/${ACCOUNT_ID}`;

async function open(role: string, list: unknown[]) {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [ACCOUNTS_ROUTE]: () => json(200, list),
    [PATCH]: () => json(200, account({ key_expires_on: "2027-01-10", key_days_left: 50 })),
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Sozlamalar" });
  return api;
}

describe("kalit muddati", () => {
  it("menejerga koʻrinmaydi", async () => {
    await open("manager", [account()]);
    expect(screen.queryByRole("heading", { level: 2, name: "Uzum kaliti muddati" })).toBeNull();
  });

  it("egasi: qolgan kun koʻrinadi, muddat PATCH bilan saqlanadi", async () => {
    const api = await open("owner", [account()]);
    const box = (await screen.findByRole("heading", { level: 2, name: /Uzum kaliti muddati/ })).closest("section") as HTMLElement;
    expect(within(box).getByText("Qolgan kun: 3")).toBeTruthy();
    const save = within(box).getByRole("button", { name: "Saqlash" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // oʻzgarmaguncha
    fireEvent.change(within(box).getByLabelText("Amal qilish muddati"), { target: { value: "2027-01-10" } });
    fireEvent.click(save);
    await waitFor(() => expect(api.calls).toContain(PATCH));
    expect(api.bodiesOf(PATCH)).toEqual([{ expires_on: "2027-01-10" }]);
  });

  it("uzilgan akkaunt (kalit yoʻq) — boʻlim koʻrinmaydi", async () => {
    await open("owner", [account({ key_hint: null })]);
    expect(screen.queryByRole("heading", { level: 2, name: /Uzum kaliti muddati/ })).toBeNull();
  });
});
