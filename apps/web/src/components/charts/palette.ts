// Grafik ranglari (04 §4.3) — `styles/tokens.ts` dan; qiymatlar bu yerda qotirilmaydi. Qorong'i rejimda ketma-ket
// shkala teskari: eng ko'p qiymat — eng yorqin (qorong'i fonda "ko'p" = yorug'), chunki 04 qorong'i shkalani
// belgilamagan va `#0D366B` `bg-surface` bilan deyarli bir xil.
import { chartDivergingMid, chartRoles, chartSequential, chartSlots, colors, fontSans, type Theme } from "../../styles/tokens";
import type { ColorKey } from "./types";

export type Palette = ReturnType<typeof chartPalette>;

export function chartPalette(theme: Theme) {
  const c = colors[theme];
  return {
    theme,
    slots: chartSlots[theme],
    ink: c["text-primary"],
    textSecondary: c["text-secondary"],
    muted: c["text-muted"],
    surface: c["bg-surface"],
    raised: c["bg-raised"],
    hairline: c["border-hairline"],
    other: c["border-input"],
    /** Sharshara: qo'shiluvchi — slot 1, ayriluvchi — slot 8, yakuniy — siyoh (04 §4.3). */
    add: chartSlots[theme][chartRoles.revenue - 1],
    subtract: chartSlots[theme][chartRoles.other - 1],
    diverging: { mid: chartDivergingMid[theme] },
    sequential: theme === "light" ? [...chartSequential] : [chartSequential[1], chartSequential[0]],
    font: fontSans,
  };
}

export function colorOf(palette: Palette, key: ColorKey): string {
  if (key === "ink") return palette.ink;
  if (key === "other") return palette.other;
  const color = palette.slots[key - 1];
  if (!color) throw new RangeError(`Grafik rangi: slot ${key} yo'q (1–8)`);
  return color;
}

/** Legenda belgisi uchun CSS (mavzu o'zgarsa o'zi yangilanadi). */
export function cssColor(key: ColorKey): string {
  return key === "ink" ? "var(--text-primary)" : key === "other" ? "var(--border-input)" : `var(--chart-${key})`;
}
