// Grafik kontekst: palitra (joriy mavzu), formatlovchi (joriy til), harakat (prefers-reduced-motion).
import { useMemo } from "react";

import { useFormat } from "../../lib/i18n";
import { useTheme } from "../../lib/theme";
import type { Ctx } from "./options";
import { chartPalette } from "./palette";

export const prefersReducedMotion = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export function useChartCtx(): Ctx {
  const f = useFormat();
  const { theme } = useTheme();
  const palette = useMemo(() => chartPalette(theme), [theme]);
  return useMemo(() => ({ f, palette, motion: !prefersReducedMotion() }), [f, palette]);
}
