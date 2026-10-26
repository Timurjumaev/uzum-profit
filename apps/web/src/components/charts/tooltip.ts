// Tooltip (04 §5.1): HTML satr — do'kon va mahsulot nomlari foydalanuvchi kiritgani, shuning uchun hammasi
// `escapeHtml` dan o'tadi. Rang belgisi yonida, matn hech qachon seriya rangida emas (04 §4.3).
import type { Palette } from "./palette";

export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]!);
}

export type TooltipRow = { name: string; value: string; color?: string; shape?: "bar" | "line" };

export function tooltipHtml(title: string, rows: TooltipRow[]): string {
  const head = `<div style="font-weight:500;margin-bottom:4px">${escapeHtml(title)}</div>`;
  const body = rows
    .map((row) => {
      const swatch = row.color
        ? row.shape === "line"
          ? `<i style="display:inline-block;width:12px;height:2px;background:${row.color};margin-inline-end:6px;vertical-align:middle"></i>`
          : `<i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${row.color};margin-inline-end:6px;vertical-align:middle"></i>`
        : "";
      return `<div style="display:flex;justify-content:space-between;gap:16px"><span>${swatch}${escapeHtml(row.name)}</span><span style="font-variant-numeric:tabular-nums;font-weight:500">${escapeHtml(row.value)}</span></div>`;
    })
    .join("");
  return head + body;
}

/** Hamma grafiklarda bir xil tooltip ko'rinishi (token ranglari bilan). */
export function tooltipBase(palette: Palette) {
  return {
    confine: true,
    renderMode: "html" as const,
    backgroundColor: palette.surface,
    borderColor: palette.hairline,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: palette.ink, fontFamily: palette.font, fontSize: 13 },
    extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgb(18 24 38 / 0.12);",
  };
}
