// Sahifa yordami (B4.11): "?" tugmasi, 3 satr, Esc bilan yopiladi; matnlar hamma tilda to'liq va qisqa (04 §3).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it } from "vitest";

import { createI18n, resources } from "../../lib/i18n";
import { HELP_PAGES, PageHelp } from "./PageHelp";

afterEach(cleanup);

type Tree = { [key: string]: string | Tree };
const pages = (lang: "uz-Latn" | "ru") => ((resources[lang].translation as unknown as { help: { pages: Tree } }).help.pages);

describe("PageHelp", () => {
  it("tugma sahifa nomi bilan ochiladi va 3 satr ko'rsatadi", () => {
    render(
      <I18nextProvider i18n={createI18n("uz-Latn")}>
        <PageHelp page="orders" />
      </I18nextProvider>,
    );
    const button = screen.getByRole("button", { name: "Sahifa haqida: Buyurtmalar" });
    fireEvent.click(button);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Buyurtmalar")).toBeTruthy();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it.each(["uz-Latn", "ru"] as const)("%s: hamma sahifada sarlavha va 3 satr, har satr ≤ 75 belgi", (lang) => {
    const tree = pages(lang);
    expect(Object.keys(tree).sort()).toEqual([...HELP_PAGES].sort());
    for (const page of HELP_PAGES) {
      const entry = tree[page] as Record<string, string>;
      for (const key of ["title", "a", "b", "c"]) expect(entry[key]?.length, `${page}.${key}`).toBeGreaterThan(0);
      for (const key of ["a", "b", "c"]) expect(entry[key]!.length, `${page}.${key}`).toBeLessThanOrEqual(75);
    }
  });
});
