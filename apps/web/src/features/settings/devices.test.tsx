// "Qurilmalarim" (B8.0a): ro'yxat, joriy qurilma belgisi, bittasini tugatish va boshqa hammasidan chiqish (tasdiq bilan).
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, mockApi, SETTINGS_ROUTE } from "../../test/api";
import { settingsData } from "../../test/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const mine = { id: "60000000-0000-4000-8000-000000000001", device: "Safari · macOS", created_at: "2026-11-20T08:00:00Z", rotated_at: "2026-11-20T08:00:00Z", expires_at: "2026-12-20T08:00:00Z", current: true };
const other = { ...mine, id: "60000000-0000-4000-8000-000000000002", device: "Chrome · Android", current: false };
const LIST = "GET /api/v1/auth/sessions";

async function open(list: unknown[]) {
  const api = mockApi({
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [LIST]: () => json(200, list),
    [`DELETE /api/v1/auth/sessions/${other.id}`]: () => new Response(null, { status: 204 }),
    "POST /api/v1/auth/sessions/revoke-others": () => json(200, { revoked: 1 }),
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  await screen.findByRole("heading", { level: 2, name: /Qurilmalarim/ });
  return api;
}

describe("qurilmalarim", () => {
  it("joriy qurilma belgilanadi va tugatilmaydi", async () => {
    await open([mine, other]);
    const box = screen.getByRole("heading", { level: 2, name: /Qurilmalarim/ }).closest("section") as HTMLElement;
    expect(await within(box).findByText("Shu qurilma")).toBeTruthy();
    expect(within(box).getAllByRole("button", { name: "Tugatish" })).toHaveLength(1);
  });

  it("bittasini tugatish DELETE yuboradi", async () => {
    const api = await open([mine, other]);
    fireEvent.click(await screen.findByRole("button", { name: "Tugatish" }));
    await waitFor(() => expect(api.calls).toContain(`DELETE /api/v1/auth/sessions/${other.id}`));
  });

  it("boshqa hammasidan chiqish tasdiqdan keyin", async () => {
    const api = await open([mine, other]);
    fireEvent.click(await screen.findByRole("button", { name: "Boshqa hamma qurilmalardan chiqish" }));
    expect(api.calls).not.toContain("POST /api/v1/auth/sessions/revoke-others");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Boshqa hamma qurilmalardan chiqish" }));
    await waitFor(() => expect(api.calls).toContain("POST /api/v1/auth/sessions/revoke-others"));
  });

  it("boshqa qurilma yo'q — tugma yo'q", async () => {
    await open([mine]);
    await screen.findByText("Shu qurilma");
    expect(screen.queryByRole("button", { name: "Boshqa hamma qurilmalardan chiqish" })).toBeNull();
  });
});
