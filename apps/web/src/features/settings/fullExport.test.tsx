// To'liq eksport bo'limi (B7.5): faqat egasiga ko'rinadi; tayyor eksport — havola so'raladi va yuklash boshlanadi.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { FULL_EXPORTS_ROUTE, json, ME, ME_ROUTE, mockApi, ORG_ID, SETTINGS_ROUTE } from "../../test/api";
import { settingsData } from "../../test/settings";
import { megabytes } from "./FullExport";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ready = {
  id: "50000000-0000-4000-8000-000000000001",
  status: "ready",
  created_at: "2026-11-21T04:00:00Z",
  expires_at: "2026-11-22T04:00:00Z",
  size_bytes: 3 * 1024 * 1024,
  tables: { items: 4 },
  error: null,
  downloaded: false,
};

async function open(role: string, list: unknown[] = []) {
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, orgs: [{ ...ME.orgs[0]!, role }] }),
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [FULL_EXPORTS_ROUTE]: () => json(200, list),
    [`POST /api/v1/orgs/${ORG_ID}/exports/full`]: () => json(202, { ...ready, status: "pending", size_bytes: null, expires_at: null }),
    [`POST /api/v1/orgs/${ORG_ID}/exports/full/${ready.id}/link`]: () => json(200, { url: `/api/v1/orgs/${ORG_ID}/exports/full/${ready.id}/download?token=abc`, expires_at: ready.expires_at }),
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 1, name: "Sozlamalar" });
  return api;
}

describe("toʻliq eksport", () => {
  it("megabayt formati", () => expect(megabytes(1572864)).toBe("1.5 MB"));

  it("menejerga koʻrinmaydi", async () => {
    await open("manager");
    await screen.findByRole("heading", { level: 2, name: "Bildirishnomalar" }).catch(() => undefined);
    expect(screen.queryByRole("heading", { level: 2, name: /Toʻliq eksport/ })).toBeNull();
  });

  it("egasi: boshlash POST yuboradi", async () => {
    const api = await open("owner");
    fireEvent.click(await screen.findByRole("button", { name: "Eksportni boshlash" }));
    await waitFor(() => expect(api.calls).toContain(`POST /api/v1/orgs/${ORG_ID}/exports/full`));
  });

  it("tayyor eksport: yuklab olish havola soʻraydi", async () => {
    const api = await open("owner", [ready]);
    fireEvent.click(await screen.findByRole("button", { name: "Yuklab olish" }));
    await waitFor(() => expect(api.calls).toContain(`POST /api/v1/orgs/${ORG_ID}/exports/full/${ready.id}/link`));
  });
});
