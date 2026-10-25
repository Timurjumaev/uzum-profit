import { act, render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, THEME_KEY, useTheme } from "./theme";

function setSystemDark(dark: boolean) {
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: dark && query.includes("dark"),
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  }));
  return listeners;
}

beforeEach(() => {
  document.head.innerHTML =
    '<meta name="theme-color" content="#F5F6F8" media="(prefers-color-scheme: light)">' +
    '<meta name="theme-color" content="#0E121A" media="(prefers-color-scheme: dark)">';
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
  setSystemDark(false);
});

afterEach(() => vi.unstubAllGlobals());

const metas = () => [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => m.getAttribute("content"));

describe("mavzu (04 §4.2)", () => {
  it("qo'lda tanlash: data-theme, saqlash, brauzer paneli", () => {
    expect(applyTheme("dark")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(metas()).toEqual(["#0E121A", "#0E121A"]);

    expect(applyTheme("system")).toBe("light");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(metas()).toEqual(["#F5F6F8", "#0E121A"]);
  });

  it("tizim qorong'i bo'lsa — system → dark", () => {
    setSystemDark(true);
    expect(applyTheme("system")).toBe("dark");
  });

  it("localStorage yopiq bo'lsa ham ishlaydi", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("SecurityError");
      },
      removeItem: () => {
        throw new Error("SecurityError");
      },
    });
    expect(applyTheme("light")).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("useTheme: tanlov va tizim o'zgarishiga ergashadi", () => {
    const listeners = setSystemDark(false);
    let api: ReturnType<typeof useTheme> | undefined;
    function Probe() {
      api = useTheme();
      return <span>{`${api.choice}/${api.theme}`}</span>;
    }
    const { container } = render(<Probe />);
    expect(container.textContent).toBe("system/light");
    act(() => api!.setTheme("dark"));
    expect(container.textContent).toBe("dark/dark");
    act(() => api!.setTheme("system"));
    setSystemDark(true);
    act(() => listeners.forEach((fn) => fn()));
    expect(container.textContent).toBe("system/dark");
  });

  it("public/theme-init.js — React'dan oldin saqlangan tanlov", () => {
    const script = readFileSync(join(import.meta.dirname, "../../public/theme-init.js"), "utf8");
    localStorage.setItem(THEME_KEY, "dark");
    new Function(script)();
    expect(document.documentElement.dataset.theme).toBe("dark");
    document.documentElement.removeAttribute("data-theme");
    localStorage.setItem(THEME_KEY, "pushti");
    new Function(script)();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
