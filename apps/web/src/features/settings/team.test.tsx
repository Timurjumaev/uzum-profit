// "Jamoa" (B8.0b): aʼzolar ro'yxati, rol almashtirish, chiqarish (tasdiq bilan), taklif yaratish va havolani ko'rsatish.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../../App";
import { json, mockApi, ME, ORG_ID, SETTINGS_ROUTE } from "../../test/api";
import { settingsData } from "../../test/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BASE = `/api/v1/orgs/${ORG_ID}`;
const OTHER = "70000000-0000-4000-8000-000000000002";
const members = [
  { user_id: ME.user.id, phone: "+998901234567", name: "Temur", role: "owner", joined_at: "2026-10-01T08:00:00Z" },
  { user_id: OTHER, phone: "+998909876543", name: null, role: "manager", joined_at: "2026-11-10T08:00:00Z" },
];
const pending = { id: "80000000-0000-4000-8000-000000000001", phone: "+998931112233", role: "accountant", expires_at: "2026-12-01T08:00:00Z" };

async function open(extra: Record<string, () => Response> = {}, list: unknown[] = members, invites: unknown[] = [pending]) {
  const api = mockApi({
    [SETTINGS_ROUTE]: () => json(200, settingsData()),
    [`GET ${BASE}/members`]: () => json(200, list),
    [`GET ${BASE}/invites`]: () => json(200, invites),
    ...extra,
  });
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
  const heading = await screen.findByRole("heading", { level: 2, name: /Jamoa/ });
  return { api, box: heading.closest("section") as HTMLElement };
}

describe("jamoa", () => {
  it("aʼzolar va kutilayotgan taklif ko'rinadi, o'zi belgilanadi", async () => {
    const { box } = await open();
    expect(await within(box).findByText("Siz")).toBeTruthy();
    expect(within(box).getByText("Ismsiz")).toBeTruthy();
    expect(within(box).getByText("+998 93 111 22 33")).toBeTruthy();
  });

  it("rolni almashtirish PATCH yuboradi", async () => {
    const { api, box } = await open({ [`PATCH ${BASE}/members/${OTHER}`]: () => json(200, { ...members[1], role: "warehouse" }) });
    await within(box).findByText("Ismsiz");
    const selects = within(box).getAllByLabelText("Rol");
    fireEvent.change(selects[1]!, { target: { value: "warehouse" } });
    await waitFor(() => expect(api.bodies).toContainEqual({ key: `PATCH ${BASE}/members/${OTHER}`, body: { role: "warehouse" } }));
  });

  it("chiqarish tasdiqdan keyin DELETE yuboradi", async () => {
    const { api, box } = await open({ [`DELETE ${BASE}/members/${OTHER}`]: () => new Response(null, { status: 204 }) });
    fireEvent.click(await within(box).findByRole("button", { name: /Chiqarish: \+998 90 987 65 43/ }));
    expect(api.calls).not.toContain(`DELETE ${BASE}/members/${OTHER}`);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Chiqarish" }));
    await waitFor(() => expect(api.calls).toContain(`DELETE ${BASE}/members/${OTHER}`));
  });

  it("taklifni bekor qilish DELETE yuboradi", async () => {
    const { api, box } = await open({ [`DELETE ${BASE}/invites/${pending.id}`]: () => new Response(null, { status: 204 }) });
    fireEvent.click(await within(box).findByRole("button", { name: "Bekor qilish" }));
    await waitFor(() => expect(api.calls).toContain(`DELETE ${BASE}/invites/${pending.id}`));
  });

  it("noto'g'ri raqam yuborilmaydi, to'g'ri raqam havola beradi", async () => {
    const { api, box } = await open({
      [`POST ${BASE}/invites`]: () => json(201, { id: "x", phone: "+998941112233", role: "manager", expires_at: "2026-12-01T08:00:00Z", url: "https://sellermax.test/invite/abc" }),
    });
    const phone = await within(box).findByLabelText("Telefon raqami");
    fireEvent.change(phone, { target: { value: "123" } });
    fireEvent.click(within(box).getByRole("button", { name: "Havola yaratish" }));
    expect(api.calls).not.toContain(`POST ${BASE}/invites`);
    fireEvent.change(phone, { target: { value: "94 111 22 33" } });
    fireEvent.click(within(box).getByRole("button", { name: "Havola yaratish" }));
    await waitFor(() => expect(api.bodies).toContainEqual({ key: `POST ${BASE}/invites`, body: { phone: "+998941112233", role: "manager" } }));
    expect((await screen.findByTestId("invite-url")).textContent).toBe("https://sellermax.test/invite/abc");
  });

  it("egasi bo'lmagan foydalanuvchiga ko'rinmaydi", async () => {
    mockApi({
      "GET /api/v1/auth/me": () => json(200, { ...ME, orgs: [{ ...ME.orgs[0], role: "manager" }] }),
      [SETTINGS_ROUTE]: () => json(200, settingsData()),
    });
    render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/settings"] }), "uz-Latn")} />);
    await screen.findByRole("heading", { level: 2, name: /Qurilmalarim/ });
    expect(screen.queryByRole("heading", { level: 2, name: /Jamoa/ })).toBeNull();
  });
});
