import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { chartSlots, colors, typeScale, type Theme } from "./tokens";

const css = readFileSync(join(import.meta.dirname, "tokens.css"), "utf8");
const fonts = readFileSync(join(import.meta.dirname, "fonts.css"), "utf8");

/** Selektor blokidagi `--nom: qiymat;` lar. */
function vars(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start, selector).toBeGreaterThanOrEqual(0);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}

const blocks: Array<[string, Theme]> = [
  [":root", "light"],
  [':root:not([data-theme="light"])', "dark"],
  [':root[data-theme="dark"]', "dark"],
];

describe("tokenlar: tokens.css = tokens.ts (04 §4)", () => {
  it.each(blocks)("%s", (selector, theme) => {
    const declared = vars(selector);
    for (const [name, value] of Object.entries(colors[theme])) {
      expect(declared[name]?.toUpperCase(), `${selector} --${name}`).toBe(value);
    }
    chartSlots[theme].forEach((value, i) => expect(declared[`chart-${i + 1}`], `chart-${i + 1}`).toBe(value));
  });

  it("tipografik shkala (04 §2.1)", () => {
    const root = vars(":root");
    for (const [name, [size, line, weight, tracking]] of Object.entries(typeScale)) {
      expect(root[`type-${name}`]).toBe(`${weight} ${size}px/${line}px var(--font-sans)`);
      expect(root[`tracking-${name}`]).toBe(`${tracking}em`);
    }
  });
});

// WCAG 2.x nisbiy yorqinlik va kontrast.
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("kontrast (WCAG 2.2 AA, 04 §4.4, §11)", () => {
  it.each(["light", "dark"] as Theme[])("%s", (theme) => {
    const c = colors[theme];
    for (const bg of [c["bg-surface"], c["bg-page"], c["bg-raised"]]) {
      expect(contrast(c["text-primary"], bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c["text-secondary"], bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c["accent-text"], bg)).toBeGreaterThanOrEqual(4.5);
      // muted — faqat ≥ 14 px yoki ikkinchi darajali (04 §4.2): 3:1.
      expect(contrast(c["text-muted"], bg)).toBeGreaterThanOrEqual(3);
      // Input chegarasi va fokus — UI komponenti: 3:1.
      expect(contrast(c["border-input"], bg)).toBeGreaterThanOrEqual(3);
      expect(contrast(c["focus-ring"], bg)).toBeGreaterThanOrEqual(3);
    }
    expect(contrast(c["on-accent"], c.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c["on-accent"], c["accent-hover"])).toBeGreaterThanOrEqual(3);
    expect(contrast(c["positive-text"], c["bg-surface"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c["negative-text"], c["bg-surface"])).toBeGreaterThanOrEqual(4.5);
    for (const kind of ["positive", "negative", "warning", "info"] as const) {
      expect(contrast(c[`${kind}-text`], c[`${kind}-bg`]), kind).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("hujjatdagi qiymatlar bilan mos (siyoh 17,3; havola 5,4)", () => {
    expect(contrast(colors.light["text-primary"], colors.light["bg-surface"])).toBeCloseTo(17.3, 0);
    expect(contrast(colors.light["accent-text"], colors.light["bg-surface"])).toBeCloseTo(5.4, 0);
  });
});

describe("shrift (04 §2)", () => {
  const ranges = [...fonts.matchAll(/unicode-range:([^;]+);/g)].flatMap((m) =>
    m[1].split(",").map((r) => {
      const [a, b] = r.trim().replace(/^U\+/, "").split("-");
      return [parseInt(a, 16), parseInt(b ?? a, 16)] as const;
    }),
  );
  const covered = (cp: number) => ranges.some(([a, b]) => cp >= a && cp <= b);

  it("o'zimizda, 4 subset, swap", () => {
    expect(fonts.match(/@font-face/g)).toHaveLength(4);
    expect(fonts).not.toMatch(/https?:/);
    expect(fonts.match(/font-display: swap/g)).toHaveLength(4);
  });

  // ▲/▼ (formatChange) Inter subsetlarida yo'q — zaxira shriftda chiqadi (geometrik belgi, farq sezilmaydi).
  it("kerakli belgilar qamrovda: ʻ ʼ NBSP U+202F − № Ў Қ Ғ Ҳ", () => {
    const required = "ʻʼ  −№ЎўҚқҒғҲҳ…–";
    for (const ch of required) expect(covered(ch.codePointAt(0)!), `U+${ch.codePointAt(0)!.toString(16)}`).toBe(true);
  });
});
