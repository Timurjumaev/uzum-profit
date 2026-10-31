// Excel eksport tugmasi (B4.10): URL yig'ish, fayl nomi, yuklab olish va xato toast'i.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createI18n } from "../../lib/i18n";
import { ExportButton, exportUrl, fileName } from "./ExportButton";
import { ToastProvider } from "./Toast";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function mount(props: Partial<Parameters<typeof ExportButton>[0]> = {}) {
  return render(
    <I18nextProvider i18n={createI18n("uz-Latn")}>
      <ToastProvider>
        <ExportButton orgId="org-1" table="sales" {...props} />
      </ToastProvider>
    </I18nextProvider>,
  );
}

describe("exportUrl", () => {
  it("bo'sh qiymatlar tushiriladi, massiv takrorlanadi", () => {
    expect(exportUrl("o", "sales", { start: "2026-10-01", shop: ["a", "b"], group: undefined, q: "", label: null })).toBe(
      "/api/v1/orgs/o/exports/sales.xlsx?start=2026-10-01&shop=a&shop=b",
    );
    expect(exportUrl("o", "purchases")).toBe("/api/v1/orgs/o/exports/purchases.xlsx");
  });
  it("maxsus belgilar kodlanadi", () => {
    expect(exportUrl("o", "skus", { q: "a&b c" })).toContain("q=a%26b+c");
  });
});

describe("fileName", () => {
  it("Content-Disposition'dan oladi, bo'lmasa zaxira nom", () => {
    expect(fileName('attachment; filename="sotuvlar-20261001.xlsx"', "x.xlsx")).toBe("sotuvlar-20261001.xlsx");
    expect(fileName(null, "x.xlsx")).toBe("x.xlsx");
    expect(fileName("attachment", "x.xlsx")).toBe("x.xlsx");
  });
});

describe("ExportButton", () => {
  it("bosilganda filtrlar bilan so'rov yuboradi va faylni yuklaydi", async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () => new Response("xlsx", { status: 200, headers: { "Content-Disposition": 'attachment; filename="sotuvlar.xlsx"' } }));
    vi.stubGlobal("fetch", fetchMock);
    const create = vi.fn(() => "blob:1");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }));
    const names: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download);
    });
    mount({ query: { start: "2026-10-01", shop: ["a"] } });
    fireEvent.click(screen.getByRole("button", { name: "Excel yuklab olish" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:1"));
    const request = fetchMock.mock.calls[0]![0];
    expect(new URL(request.url).pathname + new URL(request.url).search).toBe("/api/v1/orgs/org-1/exports/sales.xlsx?start=2026-10-01&shop=a");
    expect(request.credentials).toBe("include");
    expect(names).toEqual(["sotuvlar.xlsx"]);
    expect((screen.getByRole("button", { name: "Excel yuklab olish" }) as HTMLButtonElement).disabled).toBe(false); // tugma qayta bo'shaydi
  });

  it("xatoda fayl yuklanmaydi, toast chiqadi", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Excel yuklab olish" }));
    expect(await screen.findByText("Faylni yuklab boʻlmadi. Qayta urinib koʻring.")).toBeTruthy();
    expect(click).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Excel yuklab olish" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("disabled bo'lsa so'rov yuborilmaydi", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    mount({ disabled: true });
    fireEvent.click(screen.getByRole("button", { name: "Excel yuklab olish" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
