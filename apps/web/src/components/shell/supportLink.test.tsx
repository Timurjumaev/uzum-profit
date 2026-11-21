// "Yordam" havolasi (B8.14): havola berilgan bo'lsa — tashqi, xavfsiz; berilmagan bo'lsa — hech narsa.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createI18n } from "../../lib/i18n";
import { json, mockApi, PUBLIC_CONFIG_ROUTE } from "../../test/api";
import { SupportLink } from "./SupportLink";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function show() {
  render(
    <I18nextProvider i18n={createI18n("uz-Latn")}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SupportLink />
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("SupportLink", () => {
  it("havola bor — yangi oynada, noopener", async () => {
    mockApi({ [PUBLIC_CONFIG_ROUTE]: () => json(200, { support_url: "https://t.me/sellermax_help" }) });
    show();
    const link = await screen.findByRole("link", { name: /Yordam/ });
    expect(link.getAttribute("href")).toBe("https://t.me/sellermax_help");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("havola yo'q — hech narsa ko'rinmaydi", async () => {
    const api = mockApi({ [PUBLIC_CONFIG_ROUTE]: () => json(200, { support_url: null }) });
    show();
    await vi.waitFor(() => expect(api.calls).toContain(PUBLIC_CONFIG_ROUTE));
    expect(screen.queryByRole("link")).toBeNull();
  });
});
