// /ui-kit: hamma komponentlar bir sahifada render bo'ladi va axe-core'da jiddiy (serious/critical) xato yo'q
// (04 §11, B3 chiqish mezoni). Kontrast jsdom'da o'lchanmaydi — u `styles/tokens.test.ts` da tokenlar bo'yicha.
import { createMemoryHistory } from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App, createAppState } from "../App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function serious(root: Element = document.body): Promise<string[]> {
  const result = await axe.run(root, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function renderKit(lang: "uz-Latn" | "ru" = "uz-Latn") {
  vi.stubGlobal("fetch", vi.fn()); // ui-kit API'ga murojaat qilmaydi
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  render(<App state={createAppState(createMemoryHistory({ initialEntries: ["/ui-kit"] }), lang)} />);
  await screen.findByRole("heading", { name: "UI-kit" });
  expect(fetch).not.toHaveBeenCalled();
}

// axe butun sahifani bir necha marta tekshiradi — jsdom'da sekin, CI'da yuklama ostida 5 s yetmaydi.
const AXE_MS = 30_000;

describe("/ui-kit", () => {
  it("hamma bo'limlar, kirishsiz", async () => {
    await renderKit();
    const sections = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(sections).toEqual(
      expect.arrayContaining([
        "Button",
        "Input, NumberInput, MoneyInput",
        "Select, Combobox",
        "DateRangePicker, CompareToggle",
        "KPI, FormulaPopover",
        "LedgerTable (Hisob varagʻi)",
        "DataTable",
        "Badge, StatusPill",
        "Banner",
        "Dialog, Drawer, Popover, Tooltip, Toast",
        "Stepper, Timeline (Partiya yoʻli)",
        "EmptyState, Skeleton, ProgressBar",
        "ProductThumb, FileDrop",
      ]),
    );
  });

  it("axe: jiddiy xato 0 (yopiq va ochiq qatlamlar bilan)", async () => {
    await renderKit();
    expect(await serious()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: /Davr:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Qanday hisoblanadi: Sof foyda" }));
    fireEvent.focus(screen.getByRole("combobox", { name: "Mahsulot" }));
    expect(await serious()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Dialog" }));
    expect(screen.getByRole("dialog", { name: "Xaridni oʻchirish" })).toBeTruthy();
    expect(await serious()).toEqual([]);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    fireEvent.click(screen.getByRole("button", { name: "Uzum toʻlovi" })); // hisob varag'i qatori → drawer
    expect(screen.getByRole("dialog", { name: "Uzum toʻlovi" })).toBeTruthy();
    expect(await serious()).toEqual([]);
  }, AXE_MS);

  it("ruscha ham", async () => {
    await renderKit("ru");
    expect(document.documentElement.lang).toBe("ru");
    expect(await serious()).toEqual([]);
  }, AXE_MS);
});
