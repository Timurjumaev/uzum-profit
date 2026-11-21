// Bildirishnomalar markazi (B6.3): qo'ng'iroq belgisi, ro'yxat, o'qilgan qilish va "Batafsil" sahifasiga o'tish. Soxta API ustida.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, ME, ME_ROUTE, mockApi, NOTIFICATIONS_READ_ROUTE, NOTIFICATIONS_ROUTE } from "../../test/api";
import { EVENT_PATH } from "./NotificationBell";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const item = (over: Record<string, unknown>) => ({
  id: "n1",
  event: "stock_critical",
  status: "sent",
  critical: false,
  payload: { count: 2 },
  due_at: "2026-11-20T09:00:00Z",
  sent_at: "2026-11-20T09:00:05Z",
  read_at: null,
  created_at: "2026-11-20T09:00:00Z",
  ...over,
});

async function renderApp(list: { items: unknown[]; unread: number }) {
  const read = { items: list.items.map((x) => ({ ...(x as object), read_at: "2026-11-20T10:00:00Z" })), unread: 0 };
  const api = mockApi({
    [ME_ROUTE]: () => json(200, { ...ME, user: { ...ME.user, language: "uz-Latn" } }),
    [NOTIFICATIONS_ROUTE]: () => json(200, list),
    [NOTIFICATIONS_READ_ROUTE]: () => json(200, read),
  });
  const history = createMemoryHistory({ initialEntries: ["/"] });
  render(<App state={createAppState(history, "uz-Latn")} />);
  return { api, history };
}

describe("bildirishnomalar markazi", () => {
  it("qo'ng'iroqda o'qilmaganlar soni; ro'yxatda hodisa va yetkazish holati", async () => {
    await renderApp({ items: [item({}), item({ id: "n2", event: "goal_behind", status: "pending", read_at: "2026-11-19T10:00:00Z" })], unread: 1 });
    const count = await screen.findByTestId("bell-count");
    expect(count.textContent).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: "Bildirishnomalar: 1 ta oʻqilmagan" }));
    const panel = await screen.findByRole("region", { name: "Bildirishnomalar" });
    expect(within(panel).getByText(/Qoldiq kritik/)).toBeTruthy();
    expect(within(panel).getByText("Telegramga yuborildi")).toBeTruthy();
    expect(within(panel).getByText("Yuborilmagan")).toBeTruthy(); // Telegram ulanmagan — yetkazish holati o'qilganlikdan alohida
  });

  it("qatorni bosish — o'qilgan va tegishli sahifa; 'hammasini o'qilgan qilish'", async () => {
    const { api, history } = await renderApp({ items: [item({ event: "goal_behind" })], unread: 1 });
    fireEvent.click(await screen.findByRole("button", { name: /Bildirishnomalar: 1/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Reja orqada/ }));
    await waitFor(() => expect(history.location.pathname).toBe("/goals"));
    expect(api.bodies.find((b) => b.key === NOTIFICATIONS_READ_ROUTE)?.body).toEqual({ ids: ["n1"] });
    await waitFor(() => expect(screen.queryByTestId("bell-count")).toBeNull());
  });

  it("bo'sh holat; hamma hodisa sahifasi marshrutda bor", async () => {
    await renderApp({ items: [], unread: 0 });
    fireEvent.click(await screen.findByRole("button", { name: "Bildirishnomalar" }));
    expect(await screen.findByText(/Hozircha bildirishnoma yoʻq/)).toBeTruthy();
    expect(Object.keys(EVENT_PATH).length).toBeGreaterThanOrEqual(17);
  });
});
