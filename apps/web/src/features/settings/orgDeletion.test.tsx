// Tashkilotni o'chirish (B8.13): faqat egasiga; so'rov tasdiqdan keyin; so'ralgan bo'lsa — sana va "bekor qilish".
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, ME, ME_ROUTE, mockApi, ORG_DELETION_ROUTE, ORG_ID, SETTINGS_ROUTE } from "../../test/api";
import { settingsData } from "../../test/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const none = { requested_at: null, delete_on: null, days_left: null };
const pending = { requested_at: "2026-11-21T08:00:00Z", delete_on: "2026-12-21T08:00:00Z", days_left: 30 };
const POST = `POST /api/v1/orgs/${ORG_ID}/deletion`;
const DELETE = `DELETE /api/v1/orgs/${ORG_ID}/deletion`;

async function open(role: string, status: unknown = none) {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [ORG_DELETION_ROUTE]: () => json(200, status),
    [POST]: () => json(202, pending),
    [DELETE]: () => json(200, none),
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Sozlamalar" });
  return api;
}

describe("tashkilotni oʻchirish", () => {
  it("menejerga koʻrinmaydi", async () => {
    await open("manager");
    expect(screen.queryByRole("heading", { level: 2, name: /Tashkilotni oʻchirish/ })).toBeNull();
  });

  it("egasi: soʻrov tasdiqdan keyin POST yuboradi", async () => {
    const api = await open("owner");
    fireEvent.click(await screen.findByRole("button", { name: "Oʻchirishni boshlash" }));
    expect(api.calls).not.toContain(POST);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Oʻchirishni boshlash" }));
    await waitFor(() => expect(api.calls).toContain(POST));
  });

  it("soʻralgan: sana koʻrinadi, bekor qilish DELETE yuboradi", async () => {
    const api = await open("owner", pending);
    expect(await screen.findByText(/21\.12\.2026 da oʻchiriladi \(30 kun qoldi\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Oʻchirishni bekor qilish" }));
    await waitFor(() => expect(api.calls).toContain(DELETE));
  });
});
